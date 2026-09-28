# Qwen-Image-2.1 本地生图/改图工具包

在本地跑通 **Qwen-Image-2.1**（`unsloth/Qwen-Image-2.1-GGUF` 量化版）的完整开源工具包：8GB 级低显存显卡（如 RTX 3050）也能稳定出图，附带一个支持**历史图二次编辑**的 Web 界面。

## 特性

- 🖥️ **低显存友好**：核心策略是「扩散模型留显存、文本编码器/VAE 进内存」的拆分 + CPU offload，8GB 显存实测可跑
- 🖼️ **文生图**：支持最高 2K 分辨率、图中文字渲染、透明图（RGBA）
- ✏️ **指令式改图**：改背景、换配色、增删元素，支持最多 10 张参考图
- 🌐 **Web GUI**：Flask 界面，文生图 + 历史图库一键二次编辑 + 本地上传参考图 + 图片保存下载 / 右键菜单 + 单张删除 / 一键清空
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

**界面操作小抄**

| 想做的事 | 怎么做 |
| --- | --- |
| 保存图片到本地 | 结果大图下方「⬇ 保存图片」；历史缩略图悬停「⬇ 保存」；任意图片上右键 →「保存图片到本地」。保存后界面右下角会弹出**完整文件路径** |
| 设为参考图二次编辑 | 缩略图悬停「编辑」，或右键 →「设为参考图」，然后写编辑提示词 |
| 删除 / 清空 | 缩略图悬停「删除」、右上角「清空全部」，或右键 →「删除这张图」（均不可恢复） |

**「保存」是怎么落盘的**

界面上的保存按钮走 `POST /save`，由 **Flask 服务端直接把文件复制到本机下载目录**（`~/Downloads`，不存在则 `~/Desktop`），重名自动加 `(1)` `(2)` 后缀，并返回真实路径显示在界面上。之所以不走浏览器下载，是因为桌面应用内嵌的 WebView2 默认禁止下载（pywebview 的 `ALLOW_DOWNLOADS` 默认为 `False`），点保存会**静默失败**——界面上提示已触发，磁盘上却没有文件。

另有一个标准下载路由 `GET /download/<kind>/<name>`：与预览 `/file/<kind>/<name>` 共用同一套白名单校验（防目录穿越），但强制 `Content-Disposition: attachment`，用于直接分享链接或在浏览器里另存。`POST /save` 失败时前端会自动降级回它。

`GET /save-dir` 返回当前保存目录，前端用它显示「会存到哪」。

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

**关于下载**：启动器会显式打开 `webview.settings['ALLOW_DOWNLOADS'] = True`（pywebview 默认 `False`，这会让 WebView2 直接取消下载且不给任何提示）。开关放在 `launcher_config.json` 的 `allow_downloads` 里，默认 `true`。即便如此，桌面应用里的「保存图片」走的也是服务端直存（见上文），不依赖 WebView2 的下载链路。

## 安全与合规提示

> 本小节内容基于社区对 Qwen-Image-2.1 官方 Base 权重的实测观察，仅供参考，不构成法律意见。

1. **无内置运行时安全拦截器**  
   本地部署官方原始权重（Base model）时，模型代码层面没有内置的提示词黑名单或图像遮黑/模糊过滤器。与部分在线平台不同，它不会自动弹窗阻断或输出全黑占位图。

2. **文生图（T2I）限制宽松，图生图/局部编辑（I2I）略有约束**  
   社区反馈显示：文生图对敏感/成人提示词的遵从度较高；图生图/局部编辑受到一定程度的训练阶段指令限制，约束相对更多。具体行为会随权重版本、量化档位和采样参数变化。

3. **使用者自负合规责任**  
   在本地运行模型时，提示词与生成结果完全由用户控制。你必须遵守所在地法律法规，不得生成、传播或商业化以下类型内容，包括但不限于：儿童色情/性剥削内容、非自愿私密影像、暴力煽动、歧视性仇恨内容等。模型输出不代表本仓库作者观点。

4. **不适合直接面向公众的无过滤服务**  
   若将本工具接入任何公开或多人使用的产品，请自行增加内容审核、年龄验证、使用协议等合规机制。本仓库提供的工具链不包含此类机制。

5. **模型许可归原方所有**  
   Qwen-Image-2.1 权重与原始许可归阿里通义所有，本仓库仅提供部署与调用参考。

## License

MIT

### 仓库信息

- 仓库地址：https://github.com/H1088880/qwen-image-local
- 版权持有人：H1088880（LICENSE）
- 模型底座：Qwen-Image-2.1（阿里通义，权重与许可归原方所有，本仓库只含部署与调用工具链）
