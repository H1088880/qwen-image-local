@echo off
chcp 65001 >nul
REM 启动 Qwen-Image 本地生图 Web 界面
cd /d %~dp0
echo 正在启动 Qwen-Image 生图界面...
echo 启动后请在浏览器打开: http://127.0.0.1:7860
echo 关闭本窗口即停止服务
echo.
venv\Scripts\python.exe app.py
