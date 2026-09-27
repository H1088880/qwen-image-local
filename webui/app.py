# -*- coding: utf-8 -*-
"""Qwen-Image-2.1 本地生图 Web GUI 后端（支持文生图 + 历史图/上传图二次编辑）"""
import os
import re
import subprocess
import threading
import time
from datetime import datetime

from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # G:\qwen-image-2.1
SDCLI_DIR = os.path.join(BASE, "vulkan")
SDCLI = os.path.join(SDCLI_DIR, "sd-cli.exe")
MODELS = os.path.join(BASE, "models")
OUTPUT_DIR = os.path.join(BASE, "webui", "history")
UPLOAD_DIR = os.path.join(BASE, "webui", "uploads")

MODEL_DIFFUSION = os.path.join(MODELS, "qwen-image-2.1-Q4_K_M.gguf")
MODEL_VAE = os.path.join(MODELS, "qwen_image_2.1_vae_bf16.safetensors")
MODEL_LLM = os.path.join(MODELS, "Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

tasks = {}
tasks_lock = threading.Lock()
generating = threading.Event()  # 同一时间只允许一个生成任务（显存受限）

# 允许作为参考图 / 可对外访问的目录白名单（防目录穿越）
KIND_DIRS = {"history": OUTPUT_DIR, "uploads": UPLOAD_DIR}
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


# ---------- 工具 ----------
def _resolve(kind, name):
    """把 (kind, name) 解析为白名单目录内的真实路径，非法返回 None"""
    base = KIND_DIRS.get(kind)
    if not base or not name:
        return None
    if os.path.basename(name) != name or name.startswith((".", "/", "\\")):
        return None
    base_r = os.path.normcase(os.path.realpath(base))
    p = os.path.normcase(os.path.realpath(os.path.join(base, name)))
    if not p.startswith(base_r + os.sep):
        return None
    return p if os.path.isfile(p) else None


def _img_size(path):
    """不依赖第三方库读取 PNG/JPEG/WEBP 宽高，失败返回 (None, None)"""
    try:
        with open(path, "rb") as f:
            head = f.read(64)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(head[16:20], "big")
            h = int.from_bytes(head[20:24], "big")
            return w, h
        if head[:2] == b"\xff\xd8":  # JPEG
            with open(path, "rb") as f:
                data = f.read()
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    i += 1
                    continue
                m = data[i + 1]
                if m in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h = int.from_bytes(data[i + 5:i + 7], "big")
                    w = int.from_bytes(data[i + 7:i + 9], "big")
                    return w, h
                if m in (0xD8, 0xD9) or 0xD0 <= m <= 0xD7:
                    i += 2
                    continue
                seg = int.from_bytes(data[i + 2:i + 4], "big")
                i += 2 + seg
            return None, None
        if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
            fmt = head[12:16]
            if fmt == b"VP8X":
                w = 1 + int.from_bytes(head[24:27], "little")
                h = 1 + int.from_bytes(head[27:30], "little")
                return w, h
            if fmt == b"VP8 ":
                w = int.from_bytes(head[26:28], "little") & 0x3FFF
                h = int.from_bytes(head[28:30], "little") & 0x3FFF
                return w, h
    except OSError:
        pass
    return None, None


def _align64(v, default=512):
    """把尺寸向下对齐到 64 的倍数（sd-cli 要求），并限制范围"""
    try:
        v = int(v)
    except (TypeError, ValueError):
        return default
    v = (max(64, v) // 64) * 64
    return max(64, min(v, 1024))


# ---------- 页面 ----------
@app.route("/")
def index():
    return render_template("index.html")


# ---------- 生成（文生图 / 图编辑二合一） ----------
@app.route("/generate", methods=["POST"])
def generate():
    if generating.is_set():
        return jsonify({"ok": False, "error": "已有任务在生成中，请等它完成"}), 409

    data = request.get_json(silent=True) or {}
    prompt = (data.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"ok": False, "error": "提示词不能为空"}), 400

    width = int(data.get("width") or 512)
    height = int(data.get("height") or 512)
    steps = int(data.get("steps") or 20)
    cfg = float(data.get("cfg") or 6.0)
    seed = data.get("seed")

    # 参考图（二次编辑）
    init_kind = data.get("init_kind") or ""
    init_name = data.get("init_name") or ""
    init_path = _resolve(init_kind, init_name) if init_kind else None
    if init_kind and not init_path:
        return jsonify({"ok": False, "error": "参考图不存在或路径非法"}), 400

    edit = init_path is not None
    strength = float(data.get("strength") or 0.65)
    strength = max(0.05, min(strength, 1.0))

    # 沿用参考图尺寸
    if edit and data.get("size_from_init"):
        w0, h0 = _img_size(init_path)
        if w0 and h0:
            width, height = _align64(w0, width), _align64(h0, height)

    task_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    prefix = "edit" if edit else "gen"
    out_name = f"{prefix}_{task_id}.png"
    out_path = os.path.join(OUTPUT_DIR, out_name)

    cmd = [
        SDCLI,
        "--diffusion-model", MODEL_DIFFUSION,
        "--vae", MODEL_VAE,
        "--llm", MODEL_LLM,
        "-p", prompt,
        "--steps", str(steps),
        "--cfg-scale", str(cfg),
        "--sampling-method", "euler",
        "-W", str(width), "-H", str(height),
        "--diffusion-fa",
        "--backend", "diffusion=vulkan0,te=cpu,vae=cpu",
        "--max-vram", "6",
    ]
    if edit:
        # Qwen-Image 2.1 图编辑：init-img + strength
        cmd += ["-i", init_path, "--strength", f"{strength:.2f}"]
    cmd += ["-o", out_path]
    if seed is not None and str(seed).strip() != "":
        cmd += ["-s", str(seed)]

    with tasks_lock:
        tasks[task_id] = {
            "status": "running", "out": out_name, "path": out_path,
            "prompt": prompt, "width": width, "height": height,
            "edit": edit, "init": (init_name if edit else None),
            "strength": (strength if edit else None),
            "error": None, "started": datetime.now().isoformat(),
        }

    generating.set()
    threading.Thread(target=_run, args=(task_id, cmd, out_path), daemon=True).start()
    return jsonify({"ok": True, "task_id": task_id, "edit": edit})


def _run(task_id, cmd, out_path):
    try:
        log_path = os.path.join(OUTPUT_DIR, f"{task_id}.log")
        with open(log_path, "w", encoding="utf-8") as logf:
            proc = subprocess.run(cmd, cwd=SDCLI_DIR, stdout=logf, stderr=subprocess.STDOUT)
        if proc.returncode == 0 and os.path.exists(out_path):
            with tasks_lock:
                tasks[task_id]["status"] = "done"
        else:
            tail = ""
            try:
                with open(log_path, encoding="utf-8", errors="ignore") as f:
                    tail = f.read()[-600:]
            except OSError:
                pass
            with tasks_lock:
                tasks[task_id]["status"] = "error"
                tasks[task_id]["error"] = tail or f"退出码 {proc.returncode}"
    except Exception as e:  # noqa: BLE001
        with tasks_lock:
            tasks[task_id]["status"] = "error"
            tasks[task_id]["error"] = str(e)
    finally:
        generating.clear()


@app.route("/status/<task_id>")
def status(task_id):
    with tasks_lock:
        t = tasks.get(task_id)
    if not t:
        return jsonify({"ok": False, "error": "任务不存在"}), 404
    return jsonify({"ok": True, **t})


# ---------- 上传参考图 ----------
@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"ok": False, "error": "没有选择文件"}), 400
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in IMG_EXT:
        return jsonify({"ok": False, "error": "仅支持 PNG / JPG / WEBP / BMP"}), 400
    name = f"up_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secure_filename(f.filename)}"
    name = re.sub(r"[^\w.\-]", "_", name)
    path = os.path.join(UPLOAD_DIR, name)
    f.save(path)
    w, h = _img_size(path)
    return jsonify({"ok": True, "kind": "uploads", "name": name,
                    "url": f"/file/uploads/{name}", "width": w, "height": h})


# ---------- 文件访问 / 图库 ----------
@app.route("/file/<kind>/<path:filename>")
def file(kind, filename):
    base = KIND_DIRS.get(kind)
    if not base:
        return "bad kind", 404
    return send_from_directory(base, filename)


@app.route("/image/<path:filename>")  # 兼容旧路径
def image(filename):
    return send_from_directory(OUTPUT_DIR, filename)


@app.route("/history")
def history():
    def lst(d, kind):
        out = []
        try:
            for f in os.listdir(d):
                if f.lower().endswith(IMG_EXT):
                    p = os.path.join(d, f)
                    out.append({"name": f, "kind": kind, "mtime": os.path.getmtime(p)})
        except OSError:
            pass
        out.sort(key=lambda x: -x["mtime"])
        return out

    items = lst(OUTPUT_DIR, "history") + lst(UPLOAD_DIR, "uploads")
    items.sort(key=lambda x: -x["mtime"])
    return jsonify({"ok": True, "files": items})


@app.route("/delete", methods=["POST"])
def delete():
    data = request.get_json(silent=True) or {}
    p = _resolve(data.get("kind") or "", data.get("name") or "")
    if not p:
        return jsonify({"ok": False, "error": "文件不存在或路径非法"}), 404
    try:
        os.remove(p)
        return jsonify({"ok": True})
    except OSError as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=7860, debug=False, threaded=True)
