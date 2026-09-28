# 桌面应用启动器（可选）

把 WebUI 包装成一个**双击即用**的桌面程序：自动后台拉起 Flask → 服务就绪后弹出原生窗口 → **关窗自动停掉服务**，不留后台进程。

不用先开终端，也不用手动开浏览器。

## 它做了什么

1. 检测 `127.0.0.1:7860` 是否已有服务在跑（有则只接管窗口，关窗**不杀**它）；
2. 没有就以**隐藏控制台**的方式后台拉起 `webui/venv/Scripts/python.exe app.py`；
3. 轮询服务就绪后，窗口加载 `http://127.0.0.1:7860/`（期间显示加载动画）；
4. 关窗时清理**它自己拉起**的子进程。

> 窗口用 [pywebview](https://pywebview.flowrl.com/)（Windows 上复用系统 Edge/WebView2），不需要打包浏览器内核，产物约 32MB。

## 前提

1. 已按仓库根 `README.md` 完成部署，`webui/` 目录里有 `venv/` 与 `app.py`；
2. 建议把本目录放在项目内，这样**无需任何配置**：

```
qwen-image-2.1/
├── vulkan/          # sd-cli.exe 及 DLL
├── models/          # 三件套模型
├── webui/           # 本仓库 webui 目录
└── desktop-app/     # ← 本目录放这里
```

## 打包

```bash
pip install pywebview pyinstaller

cd desktop-app
pyinstaller --noconfirm --clean --onedir --windowed --name QwenImageLocal \
  --collect-all webview --collect-all clr_loader --collect-all pythonnet \
  launcher.py

# 把配置放到 exe 同目录（否则读不到，会退回内置默认值）
cp launcher_config.json dist/QwenImageLocal/
```

双击 `dist/QwenImageLocal/QwenImageLocal.exe` 即可。

> 用 `--onedir` 而不是 `--onefile`：onefile 运行时 `sys.executable` 在临时解压目录里，会导致同目录的 `launcher_config.json` 读不到。

## 配置（launcher_config.json，与 exe 同目录）

| 字段 | 说明 | 默认 |
|---|---|---|
| `webui_dir` | WebUI 目录（须含 `venv\` 与 `app.py`）。**留空自动探测** exe 上级目录里的 `webui` | `""` |
| `port` | 服务端口，须与 app.py 一致 | `7860` |
| `title` | 窗口标题 | `Qwen-Image 本地生图` |
| `width` / `height` | 初始窗口尺寸 | `1180` / `920` |
| `boot_timeout` | 等待服务就绪秒数 | `120` |
| `allow_downloads` | 是否放行 WebView2 下载。pywebview 默认 `False`，会让页面里的「保存图片」**静默失败**（点了没反应、没文件、没提示），故启动器默认置 `True` | `true` |

改完保存即可，**不用重新打包**。

> 即便把 `allow_downloads` 设为 `false`，界面上的「保存图片」依然可用——它走的是服务端直存（WebUI 的 `POST /save`，直接写进本机下载目录），不依赖 WebView2 的下载链路。

## 命令行（可选）

```bat
QwenImageLocal.exe --check                       :: 自检：拉起/探测是否正常，不弹窗
QwenImageLocal.exe --webui-dir "D:\path\webui"   :: 临时指定 WebUI 目录
QwenImageLocal.exe --port 7861                   :: 临时指定端口
```

优先级：命令行参数 > `launcher_config.json` > 内置默认值。

## 降级策略

- 原生窗口依赖 **WebView2（Edge 运行时）**，Windows 10/11 一般自带；
- 若不可用，自动降级为 **Edge/Chrome `--app=` 独立窗口**（无标签栏，观感接近应用）；
- 都不行，最后退回系统默认浏览器。

## 已知坑

- **`--windowed` 打包后 stdout 是 GBK**，`print` 非 ASCII 字符（如 ✅）会抛 `UnicodeEncodeError` 直接崩溃。本脚本已用 `log()` 兜底，输出一律 ASCII。二次开发时留意。
- `app.py` 硬编码 `127.0.0.1:7860`，无命令行参数；改端口要同时改 `app.py` 与这里的 `port`。
- 本启动器**不含模型**（模型约 9GB，不随程序分发）。
