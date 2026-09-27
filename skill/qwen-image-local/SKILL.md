---
name: qwen-image-local
description: 在本地部署并调用 Qwen-Image-2.1（unsloth/Qwen-Image-2.1-GGUF 量化版）完成文生图与图像编辑。当用户想"本地跑 Qwen 生图/改图"、"部署 Qwen-Image-2.1"、"用 GGUF 量化版出图"、"8GB/低显存跑 Qwen 图像模型"、或需要文字渲染/透明图(RGBA)/多参考图编辑等能力时使用。覆盖环境检测、量化方案选型、stable-diffusion.cpp (sd-cli) 部署、文生图与图编辑命令、参数调优与故障排查。优先用 stable-diffusion.cpp 而非 Python/PyTorch 方案。
agent_created: true
---

# Qwen-Image 本地生图改图（qwen-image-local）

## 用途

在本地部署并驱动 **Qwen-Image-2.1**（`unsloth/Qwen-Image-2.1-GGUF` 量化版），完成文生图（text-to-image）与图像编辑（image editing）。该模型是 7B 参数的统一文生图 + 编辑模型，搭配 Qwen3-VL 8B 文本编码器，原生支持 2K 分辨率、图中文字渲染、透明图（RGBA）、以及最多 10 张参考图的编辑。

本 skill 的核心价值：**让 8GB 级低显存显卡（如 RTX 3050）也能稳定跑通**，而非要求 24GB 高端卡。手段是「扩散模型留显存、文本编码器进内存」的拆分策略 + 低量化档位 + CPU offload。

## 何时使用

- 用户要「本地部署 Qwen 生图 / 改图」「跑 Qwen-Image-2.1」「用 unsloth GGUF 出图」
- 用户明确是低显存（≤8GB）或纯 CPU 环境，想跑图像生成模型
- 需要文字渲染、透明图、抠图改背景、多图参考等 Qwen-Image-2.1 特有能力
- 用户问「Qwen 生图改图怎么本地跑 / 哪个量化档位 / 怎么选后端」

## 核心原理（务必先理解）

Qwen-Image-2.1 的 GGUF 只是去噪器（denoiser），**三组件「三件套」分散在三个独立仓库**，缺一不可（⚠️ 网上很多教程把路径写成同一仓库的子目录，是错的）：

| 组件 | 仓库 | 文件 | 实测大小 | 放哪里 |
|---|---|---|---|---|
| 扩散模型 (DiT, 7B) | `unsloth/Qwen-Image-2.1-GGUF` | `qwen-image-2.1-Q4_K_M.gguf` | 3.91 GB | **显存** |
| 文本编码器 | `unsloth/Qwen3-VL-8B-Instruct-GGUF` | `Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf` | 4.79 GB | **CPU**（GGUF 格式，官方推荐 UD-Q4_K_XL 动态量化，比均匀 Q4_K_M 画质更好且更快） |
| VAE | `unsloth/Qwen-Image-2.1-FP8` | `vae/qwen_image_2.1_vae_bf16.safetensors` | 645 MB | **CPU** |

**关键决策（实测验证，8GB 显存 + 16GB 内存机器）**：
- 文本编码器选 UD-Q4_K_XL（官方推荐，LPIPS 0.029 / SSIM 0.959 优于均匀 Q4_K_M）
- `--backend "diffusion=vulkan0,te=cpu,vae=cpu"`：DiT 独占显存，文本编码器和 VAE 都走 CPU
- 系统内存是隐形瓶颈：16GB 内存被占用 88% 时连 512×512 都危险，出图前先释放内存

## 工作流程

### 第 1 步：检测环境

先确认本机 GPU 与内存，再据此选型。用以下命令探测：

- Windows (Git Bash / PowerShell)：`nvidia-smi --query-gpu=name,memory.total --format=csv,noheader`
- 内存：PowerShell `(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory`

根据探测结果对照 `references/quantization-guide.md` 的选型表。

### 第 2 步：选定后端与量化方案

**默认选 `stable-diffusion.cpp`（sd-cli）**，理由：纯 C/C++ 免 Python/PyTorch、预编译 exe 开箱即用、支持 Vulkan/CUDA、自带 VAE tiling 与 CPU offload，最低 4GB 显存即可跑。

量化方案按显存选（详见 `references/quantization-guide.md`）：

- **≤8GB 显存**（本 skill 主要目标）：`Q4_K_M` 扩散模型 + Int8 文本编码器 + CPU offload + VAE tiling
- 12–16GB：`Q4_K_M` @ 1024×1024 直接跑
- 24GB+：INT8/FP8 高精度
- 纯 CPU：12–16GB 内存 + `Q4_K_M` + `Q4_K_XL` 文本编码器

备选后端：ComfyUI + ComfyUI-GGUF（需 molbal fork，配置繁琐）；Unsloth Desktop（GUI 一键）。排除 Ollama（对 Qwen-Image-2.1 支持弱）。

### 第 3 步：安装 sd-cli 并下载三件套

部署完整命令见 `references/setup-guide.md`。要点（含国内镜像实测经验）：

1. 从 `https://github.com/leejet/stable-diffusion.cpp/releases` 下载预编译包：**首选 Vulkan 版**（开箱即用，自动识别 NVIDIA/AMD/Intel 显卡）；cuda12 版需要另配 cudart/cublas DLL（预编译包不带，会报 not found）。
2. 国内下载 GitHub release 不稳定时，用镜像前缀：`https://gh-proxy.com/<原始URL>`。
3. 三件套从三个 HF 仓库下载（见上表）；HF 直连 502 时改用 `https://hf-mirror.com/<仓库名>/resolve/main/<文件名>`。
4. 校验文件大小是否与仓库清单一致（curl 下载 15 字节的 "Entry not found" 说明路径错了）。

### 第 4 步：文生图

**8GB 显存实测可用的完整命令**（RTX 3050 + 16GB 内存验证通过，512×512 全程约 7.5 分钟）：

```bash
sd-cli \
  --diffusion-model qwen-image-2.1-Q4_K_M.gguf \
  --vae qwen_image_2.1_vae_bf16.safetensors \
  --llm Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  -p "a cartoon sloth mascot waving, flat vector illustration, bright colours" \
  --steps 20 --cfg-scale 6.0 --sampling-method euler \
  -W 512 -H 512 --diffusion-fa \
  --backend "diffusion=vulkan0,te=cpu,vae=cpu" \
  --max-vram 6 \
  -o out.png
```

显存充裕（12GB+）时可简化为 `-W 1024 -H 1024 --diffusion-fa --vae-tiling --backend vulkan0`。参数说明与调优见 `references/commands.md`。

### 第 5 步：图像编辑（二次改图）

Qwen-Image-2.1 支持指令式编辑（改背景、换服装配色、增删元素、局部标注、多参考图）。核心是 `-i <原图>` + `--strength <强度>`，**prompt 要写「改完之后的样子」**，而不是「把 xx 改成 yy」这种操作描述之外的闲话（两种写法都能工作，但描述结果画面更稳）。

```bash
cd /g/qwen-image-2.1/vulkan && ./sd-cli.exe \
  --diffusion-model ../models/qwen-image-2.1-Q4_K_M.gguf \
  --vae ../models/qwen_image_2.1_vae_bf16.safetensors \
  --llm ../models/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  -i ../webui/history/model1.png \
  -p "把裙子改成酒红色丝绒长裙，背景换成夜色江景，其余保持不变" \
  --steps 20 --cfg-scale 6.0 --sampling-method euler \
  -W 448 -H 768 --diffusion-fa \
  --backend "diffusion=vulkan0,te=cpu,vae=cpu" --max-vram 6 \
  --strength 0.65 \
  -o ../out/edited.png
```

**`--strength` 怎么选**（默认 0.75，8GB 卡上建议 0.4–0.7）：

| 强度 | 效果 | 适用场景 |
|---|---|---|
| 0.2–0.4 | 几乎只改细节 | 调色、光影、材质微调、修瑕疵 |
| 0.5–0.7 | 保留构图与主体 | 换服装/换配色/换背景（推荐默认 0.65） |
| 0.75–0.95 | 大幅重画 | 只想保留大致构图与姿态 |

**编辑模式要点**：
- 输出尺寸默认沿用原图（须能被 64 整除，如 448×768）；改尺寸等于重画，等于浪费编辑能力
- 编辑比文生图多一次 VAE 编码，8GB 卡上约 6–10 分钟
- 想稳定复现就固定 seed；想多方案就同 prompt 换 seed 出 2–3 张挑
- 上限：竖版 448×768 ✅，竖版 512×896 ❌（latent 过大 OOM）

### 第 5.5 步：Web GUI（推荐给非命令行用户）

> 💡 用户只想「打开生图界面」时，直接调用 `qwen-webui` skill 一键启动即可，无需走本步。

已在 `G:/qwen-image-2.1/webui/` 实现 Flask 版界面（端口 7860），支持文生图 + **历史图二次编辑**：

- 启动：`cd /g/qwen-image-2.1/webui && ./venv/Scripts/python.exe app.py`（后台常驻，不要用 `&`，会被 shell 回收）
- 历史图库每张图悬停有「编辑」按钮 → 自动填入为参考图 → 写编辑 prompt → 生成
- 参考图两个来源：历史图库的图（kind=history）、本地上传（kind=uploads，存 `webui/uploads/`）
- 「沿用参考图尺寸」默认勾选，自动按 64 对齐，避免手填尺寸出错
- 改动强度滑块即 `--strength`；单任务锁（显存受限，同时只跑一个）

**后端实现要点（改动时别踩）**：
- 参考图路径必须经 `_resolve(kind, name)` 白名单校验，防目录穿越；只认 `history` / `uploads` 两个目录
- 判定出图成功要用传入的 `out_path`，**不能用 `cmd[-1]`** —— `-i/--strength` 若追加在 `-o` 之后会把 `-o` 的值顶掉，导致误判失败（已踩过）
- 图片宽高用纯 Python 解析 PNG/JPEG/WEBP 头，不引入 Pillow 依赖

### 第 6 步：故障排查

常见问题（OOM、模型不识别、透明图、文字乱码等）与解法见 `references/troubleshooting.md`。

**实测 OOM 三板斧（8GB 显存按顺序用）**：
1. 文本编码器 OOM（LLM prompt encoding failed）→ `--backend te=cpu`
2. 采样 OOM（diffusion model compute failed）→ 加 `--max-vram 6`，确认 DiT 权重独占显存，别用 `--offload-to-cpu`（内存不足时反而更糟）
3. VAE 解码 OOM（vae decode compute failed，常见于采样成功后）→ `--backend vae=cpu`（CPU 解码只慢 1-2 分钟，稳）
4. 兜底：降分辨率 1024→768→512

## 关键参数速记

- **分辨率**：必须能被 32 整除；从 1024×1024 起步，成功后逐步上调（上限 2048/边）
- **步数**：sd-cli 用 20 步；diffusers 用 40 步
- **CFG**：sd-cli 用 6.0；diffusers 用 1.0（禁用 CFG）
- **采样器**：Euler
- **batch**：保持 1
- **seed**：固定 42 便于复现对比

## 资源文件

- `references/quantization-guide.md` — 量化档位与显存选型速查表
- `references/setup-guide.md` — Windows/Linux/macOS 部署与三件套下载明细
- `references/commands.md` — 文生图 / 图编辑 / 透明图 / 多参考图完整命令与参数
- `references/troubleshooting.md` — 常见问题与排查步骤
