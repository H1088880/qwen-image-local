# Qwen-Image-2.1 本地生图/改图工具包

在本地跑通 **Qwen-Image-2.1**（`unsloth/Qwen-Image-2.1-GGUF` 量化版）的完整开源工具包：8GB 级低显存显卡（如 RTX 3050）也能稳定出图，附带一个支持**历史图二次编辑**的 Web 界面。

## 特性

- 🖥️ **低显存友好**：核心策略是「扩散模型留显存、文本编码器/VAE 进内存」的拆分 + CPU offload，8GB 显存实测可跑
- 🖼️ **文生图**：支持最高 2K 分辨率、图中文字渲染、透明图（RGBA）
- ✏️ **指令式改图**：改背景、换配色、增删元素，支持最多 10 张参考图
- 🌐 **Web GUI**：Flask 界面，文生图 + 历史图库一键二次编辑 + 本地上传参考图
- 🖥️ **桌面应用（可选）**：可打包成双击即用的 exe，自动拉起服务、关窗自动停（见 [desktop-app/](desktop-app/)）
- 📦 **免 Python/PyTorch 出图**：底层用 stable-diffusion.cpp（sd-cli）预编译版，纯 C/C++
- 🤖 **Agent Skill 附带**：包含一份可直接装入 AI Agent（如 WorkBuddy/Claude Code 等）的 skill 文档

## 目录结构

```
.
├── README.md
├── LICENSE
├── skill/
│   └── qwen-image-local/        # Agent Skill（SKILL.md + 4 份参考文档）
│       ├── SKILL.md             # 技能主文档：原理、工作流、参数速记
│       └── references/
│           ├── setup-guide.md          # 部署与三件套下载明细
│           ├── quantization-guide.md   # 量化档位与显存选型表
│           ├── commands.md             # 文生图/改图/透明图完整命令
│           └── troubleshooting.md      # OOM 等常见问题排查
├── webui/                       # Flask Web 界面源码
│   ├── app.py                   # 后端（含目录白名单防穿越、任务队列）
│   ├── templates/index.html     # 前端页面
│   ├── start_webui.bat          # Windows 一键启动
│   ├── start_webui.sh           # Linux/macOS 一键启动
│   └── requirements.txt
└── desktop-app/                 # 可选：桌面应用启动器（pywebview + PyInstaller）
    ├── launcher.py              # 拉起服务 + 原生窗口 + 关窗清理
    ├── launcher_config.json     # 配置（webui 路径/端口/窗口尺寸）
    └── README.md
```

## 快速开始

### 1. 部署 sd-cli 与模型三件套

按 [`skill/qwen-image-local/references/setup-guide.md`](skill/qwen-image-local/references/setup-guide.md) 操作，核心要点：

1. 从 [stable-diffusion.cpp releases](https://github.com/leejet/stable-diffusion.cpp/releases) 下载 **Vulkan 版**预编译包（开箱即用，自动识别 N/A/I 卡），解压为 `vulkan/` 目录
2. 下载模型「三件套」到 `models/` 目录（三件套分散在三个 HuggingFace 仓库，国内可用 `hf-mirror.com` 镜像）：

| 组件 | 仓库 | 文件 | 大小 |
|---|---|---|---|
| 扩散模型 (DiT 7B) | `unsloth/Qwen-Image-2.1-GGUF` | `qwen-image-2.1-Q4_K_M.gguf` | 3.91 GB |
| 文本编码器 | `unsloth/Qwen3-VL-8B-Instruct-GGUF` | `Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf` | 4.79 GB |
| VAE | `unsloth/Qwen-Image-2.1-FP8` | `vae/qwen_image_2.1_vae_bf16.safetensors` | 645 MB |

3. 最终目录结构：

```
qwen-image-2.1/
├── vulkan/        # sd-cli.exe 及其 DLL
├── models/        # 三件套模型文件
└── webui/         # 本仓库 webui 目录（放进来即可）
```

### 2. 启动 Web 界面

```bash
cd webui
pip install -r requirements.txt

# Windows：双击 start_webui.bat，或
venv 方式启动见 start_webui.sh
```

浏览器打开 http://127.0.0.1:7860 即可使用。

### 3. 命令行直接出图（可选）

不想要 Web 界面也可以直接跑 sd-cli，完整命令见 [`skill/qwen-image-local/references/commands.md`](skill/qwen-image-local/references/commands.md)：

```bash
sd-cli \
  --diffusion-model qwen-image-2.1-Q4_K_M.gguf \
  --vae qwen_image_2.1_vae_bf16.safetensors \
  --llm Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  -p "a cartoon sloth mascot waving, flat vector illustration" \
  --steps 20 --cfg-scale 6.0 --sampling-method euler \
  -W 512 -H 512 --diffusion-fa \
  --backend "diffusion=vulkan0,te=cpu,vae=cpu" \
  --max-vram 6 -o out.png
```

## 关键参数速记

- **分辨率**：必须能被 32 整除，从 512×512 起步，成功后逐步上调
- **步数 / CFG / 采样器**：sd-cli 用 `20 / 6.0 / Euler`
- **改图强度**：`--strength` 0.2–0.4 微调 / 0.5–0.7 换装换背景（推荐 0.65）/ 0.75+ 大幅重画
- **显存兜底三板斧**：`te=cpu` → `--max-vram 6` → `vae=cpu`，详见 troubleshooting

## 实测参考（RTX 3050 8GB + 16GB 内存）

- 512×512 文生图全程约 7.5 分钟
- 448×768 图像编辑约 6–10 分钟
- 竖版 448×768 ✅ / 竖版 512×896 ❌（latent 过大 OOM）

## 桌面应用（可选）

不想每次先开终端、再开浏览器，可以把 WebUI 打包成双击即用的桌面程序：自动后台拉起 Flask、服务就绪后弹出原生窗口、**关窗自动停掉服务**，不留后台进程。

```bash
cd desktop-app
pip install pywebview pyinstaller

pyinstaller --noconfirm --clean --onedir --windowed --name QwenImageLocal \
  --collect-all webview --collect-all clr_loader --collect-all pythonnet launcher.py

cp launcher_config.json dist/QwenImageLocal/   # 配置文件需与 exe 同目录
```

把 `desktop-app/` 放在项目目录内（与 `webui/` 同级）时**无需任何配置**，启动器会自动定位 WebUI 目录。详见 [desktop-app/README.md](desktop-app/README.md)。

## License

MIT
