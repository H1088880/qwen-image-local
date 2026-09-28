# -*- coding: utf-8 -*-
"""
Qwen-Image 本地生图 —— 桌面启动器
==================================
双击 exe 即弹出原生窗口加载本地 WebUI；关闭窗口会自动停掉后台 Flask 服务。
若系统缺少 WebView2 运行时，会自动回退为用默认浏览器打开。

配置优先级：命令行参数 > launcher_config.json（与 exe 同目录）> 下方 DEFAULTS。
"""
import os
import sys
import json
import time
import socket
import subprocess
import threading
import urllib.request
import webbrowser

# ---------- 默认配置（可被 launcher_config.json / 命令行覆盖） ----------
DEFAULTS = {
    "webui_dir": r"G:\qwen-image-2.1\webui",   # WebUI 目录（含 venv/ 与 app.py）
    "host": "127.0.0.1",
    "port": 7860,
    "title": "Qwen-Image 本地生图",
    "width": 1180,
    "height": 920,
    "boot_timeout": 120,        # 等待 Flask 就绪的最长秒数（首次冷启动生图环境可达 1~2 分钟）
    "log_file": "desktop_launcher.log",
}

LOADING_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:#0f1115;color:#e6e6e6;
    font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:18px}
  .spin{width:42px;height:42px;border:4px solid #2a2f3a;border-top-color:#6ea8fe;border-radius:50%;
    animation:r 1s linear infinite}
  @keyframes r{to{transform:rotate(360deg)}}
  .t{font-size:15px;opacity:.85}.s{font-size:12px;opacity:.5}
</style></head><body>
  <div class="spin"></div>
  <div class="t">正在启动本地生图服务…</div>
  <div class="s">首次启动需加载模型，请稍候（约 1~2 分钟）</div>
</body></html>"""

ERROR_HTML = """<!doctype html><html><head><meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;background:#1a1010;color:#f0d6d6;
    font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:24px;text-align:center}
  .t{font-size:16px;font-weight:600}.s{font-size:13px;opacity:.7;line-height:1.6}
  code{background:#000;padding:2px 6px;border-radius:4px}
</style></head><body>
  <div class="t">⚠ 本地生图服务未能启动</div>
  <div class="s">
    可能原因：<br>
    1. WebUI 目录路径不对（默认 <code>G:\\qwen-image-2.1\\webui</code>）<br>
    2. 该目录下的 venv / app.py 缺失<br>
    3. 端口 7860 被其它程序占用<br><br>
    请检查目录后重试；或用浏览器手动打开 <code>http://127.0.0.1:7860/</code>
  </div>
</body></html>"""


def log(msg=""):
    """--windowed 打包后 stdout 可能是 GBK，非 ASCII 字符会抛 UnicodeEncodeError，这里兜底。"""
    try:
        print(msg)
    except Exception:
        try:
            print(str(msg).encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


def app_dir():
    """onedir 打包后返回 exe 所在目录；源码运行返回脚本目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def load_config():
    cfg = dict(DEFAULTS)
    p = os.path.join(app_dir(), "launcher_config.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            log("读取配置失败，使用默认：%s" % e)
    return cfg


def venv_python(webui_dir):
    return os.path.join(webui_dir, "venv", "Scripts", "python.exe")


def resolve_webui_dir(cfg):
    """确定 WebUI 目录：优先用配置值；配置为空或无效时，沿 exe 上级目录自动找 webui。
    这样开源用户把 desktop-app 放在项目里（如 qwen-image-2.1/desktop-app）即可免配置。"""
    d = cfg.get("webui_dir") or ""
    if d and os.path.exists(os.path.join(d, "app.py")):
        return d
    here = app_dir()
    for up in range(1, 4):
        base = os.path.normpath(os.path.join(here, *([".."] * up)))
        cand = os.path.join(base, "webui")
        if os.path.exists(os.path.join(cand, "app.py")):
            return cand
    return d  # 都没找到，返回配置值，交给后续报错提示


def port_open(host, port, timeout=1.0):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def url_ready(url, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def spawn_server(webui_dir, log_path):
    py = venv_python(webui_dir)
    if not os.path.exists(py):
        return None, ("找不到 venv Python：%s\n"
                      "请确认 launcher_config.json 里的 webui_dir 指向正确的 WebUI 目录；"
                      "留空则会自动在 exe 的上级目录中查找 webui 目录。" % py)
    app_py = os.path.join(webui_dir, "app.py")
    if not os.path.exists(app_py):
        return None, "找不到 app.py：%s" % app_py
    flags = 0
    if sys.platform.startswith("win"):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    logf = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        [py, app_py],
        cwd=webui_dir,
        stdout=logf,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    return proc, None


def open_app_window(url, width, height):
    """用 Edge/Chrome 的 --app 模式开一个无标签栏的独立窗口（观感接近原生应用）。
    找不到就退回系统默认浏览器。"""
    candidates = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for exe in candidates:
        if os.path.exists(exe):
            try:
                subprocess.Popen([exe, "--app=" + url,
                                  "--window-size=%d,%d" % (width, height)])
                return True
            except Exception:
                pass
    webbrowser.open(url)
    return False


def kill_proc(proc):
    if proc is None:
        return
    if proc.poll() is None:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def run_gui(cfg):
    webui_dir = resolve_webui_dir(cfg)
    host, port = cfg["host"], cfg["port"]
    url = "http://%s:%s/" % (host, port)
    log_path = os.path.join(app_dir(), cfg["log_file"])

    attached = port_open(host, port)
    proc = None
    err = None
    if not attached:
        proc, err = spawn_server(webui_dir, log_path)
    if err:
        # 起不来：至少把浏览器窗口开出来，让用户能看到报错/自己排查
        open_app_window(url, cfg["width"], cfg["height"])
        return

    def boot(window):
        ok = url_ready(url, cfg["boot_timeout"])
        if ok:
            window.load_url(url)
        else:
            window.load_html(ERROR_HTML)

    try:
        import webview  # 延迟导入，便于无界面环境做逻辑测试
        window = webview.create_window(
            cfg["title"], html=LOADING_HTML,
            width=cfg["width"], height=cfg["height"],
        )
        threading.Thread(target=boot, args=(window,), daemon=True).start()
        webview.start()
        kill_proc(proc)
    except Exception as e:
        # WebView2/.NET 不可用等：降级为 Edge/Chrome 独立窗口
        log("原生窗口不可用，降级为浏览器 app 模式：%s" % e)
        url_ready(url, cfg["boot_timeout"])
        open_app_window(url, cfg["width"], cfg["height"])
        # 该模式下无法感知关闭，不自动关停（避免误杀用户手动开的页面）


def run_check(cfg):
    """无界面自检：验证「拉起/探测」逻辑，不弹窗；检查完即停掉本次拉起的服务。"""
    webui_dir = resolve_webui_dir(cfg)
    host, port = cfg["host"], cfg["port"]
    url = "http://%s:%s/" % (host, port)
    log_path = os.path.join(app_dir(), cfg["log_file"])

    attached = port_open(host, port)
    proc = None
    if attached:
        log("[CHECK] 端口 %s 已被占用（已有服务），直接判定就绪。" % port)
    else:
        proc, err = spawn_server(webui_dir, log_path)
        if err:
            log("[CHECK] 启动失败：%s" % err)
            return False
        log("[CHECK] 已拉起 Flask，等待 %s 就绪（最多 %ss）..." % (url, cfg["boot_timeout"]))
    ok = url_ready(url, cfg["boot_timeout"])
    log("[CHECK] 服务就绪 [OK] " + url if ok else "[CHECK] 等待超时 [FAIL] " + url)
    if proc is not None:
        kill_proc(proc)  # 检查模式不遗留进程
    return ok


def main():
    cfg = load_config()
    # 命令行覆盖
    if "--webui-dir" in sys.argv:
        i = sys.argv.index("--webui-dir")
        if i + 1 < len(sys.argv):
            cfg["webui_dir"] = sys.argv[i + 1]
    if "--port" in sys.argv:
        i = sys.argv.index("--port")
        if i + 1 < len(sys.argv):
            try:
                cfg["port"] = int(sys.argv[i + 1])
            except ValueError:
                pass
    if "--check" in sys.argv:
        ok = run_check(cfg)
        sys.exit(0 if ok else 1)
    run_gui(cfg)


if __name__ == "__main__":
    main()
