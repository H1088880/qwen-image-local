#!/bin/bash
# 启动 Qwen-Image 本地生图 Web 界面
cd "$(dirname "$0")"
echo "正在启动 Qwen-Image 生图界面..."
echo "浏览器打开: http://127.0.0.1:7860"
echo "按 Ctrl+C 停止服务"
echo ""
./venv/Scripts/python.exe app.py
