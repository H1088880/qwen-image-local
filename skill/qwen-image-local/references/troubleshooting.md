# 故障排查（troubleshooting）

## OOM（显存不足）——实测三板斧（8GB 显存验证）

**先查显存再出图**（重要！其他程序会偷显存导致"之前能跑的尺寸现在 OOM"）：

```bash
nvidia-smi --query-gpu=memory.total,memory.used,memory.free --format=csv,noheader
# free 需 ≥ 6GB（DiT 权重 4GB + 激活 2GB）。不足则先关闭占显存的程序
```

**常见显存杀手**（实测）：ComfyUI 常驻占 2GB+ 显存（即使空闲）、爱奇艺播放器、豆包、微信小程序、多开 Edge WebView。残留进程退出后显存可能未释放，`tasklist | grep -i python` + `taskkill //PID <pid> //F` 清理。

症状与对症下药（按报错信息定位）：

1. **文本编码阶段 OOM**（`LLM prompt encoding failed` / `Device memory allocation failed` 出现在条件编码时）
   → `--backend "diffusion=vulkan0,te=cpu,vae=cpu"`，文本编码器走 CPU

2. **采样阶段 OOM**（`diffusion model compute failed` / `cannot make enough memory available on Vulkan0`）
   → 先查显存占用（见上），释放后重试
   → 加 `--max-vram 6` 限制显存预算，让 DiT 权重独占 GPU
   → ⚠️ 不要用 `--offload-to-cpu`：内存不足时它把 DiT 权重也搬进内存，两头都爆

3. **VAE 解码阶段 OOM**（采样 20/20 完成后报 `vae decode compute failed` / `wan_vae segment failed`）
   → `--backend vae=cpu`（VAE 仅 645MB，CPU 解码 512×512 约 75s，稳）

4. **系统内存不足**（`RAM free` 只有几百 MB，auto-fit 把权重全部排到 disk）
   → 关闭占内存的程序后重试；16GB 机器空闲内存至少留 6GB
   → 这是隐形瓶颈：显存够但内存不足同样会失败

5. 兜底：降分辨率（见下方实测分辨率上限）

## 8GB 显存实测分辨率上限（Q4_K_M，free ~6.5GB 时）

| 分辨率 | latent | 结果 |
|---|---|---|
| 512×512（方形） | 64×64 | ✅ 稳定（基准） |
| 448×768（9:16 竖版） | 56×96 | ✅ 稳定 |
| 512×896（9:16 竖版） | 64×112 | ❌ 采样 OOM（need 545MB > available 417MB） |
| 1024×1024 | 128×128 | ❌ 需 12GB+ 显存 |

竖版 9:16 用 **448×768**；方形用 512×512。更高分辨率需 12GB+ 显存或更激进量化（Q4_0）。

## 模型加载失败 / 不识别架构

症状：`Unknown model architecture` 或下载后无法加载。

- **sd-cli**：确认用最新版 release，Qwen-Image 支持是 2025/09 才加入的，旧版不识别。
- **ComfyUI**：city96/ComfyUI-GGUF 尚不支持 Qwen-Image-2.1，需用 molbal/ComfyUI-GGUF fork；GGUF 文件放 `models/unet/`（不是 `models/diffusion_models/`）。
- 确认三件套齐全（扩散模型 + 文本编码器 + VAE 缺一不可）。
- 确认文本编码器是 GGUF 格式（`Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf`，来自 unsloth/Qwen3-VL-8B-Instruct-GGUF 仓库），网上流传的 `qwen3vl_8b_int8_convrot.safetensors` 是 ComfyUI 专用转换版，sd-cli 不用。

## sd-cli 检测不到 GPU（只显示 CPU）

- cuda12 版预编译包不带 CUDA runtime：`ldd ggml-cuda.dll` 若显示 `cudart64_12.dll => not found`，需装 CUDA Toolkit 12 或补齐 cudart/cublas/cublasLt 三个 DLL。
- 最省事方案：改用 **Vulkan 版**，零额外依赖，`--list-devices` 直接显示 `Vulkan0 <显卡名>`。

## 下载损坏 / 文件不完整

症状：加载报错或生成异常。

- 用 SHA256SUMS 校验文件完整性（见 setup-guide.md 第三节）。
- 用 `huggingface-cli download`（支持断点续传）而非 curl 一次性拉大文件。

## 生成图片空白 / 全黑 / 纯色

- 检查采样器与步数是否匹配后端（sd-cli：euler + 20 步）。
- 检查 CFG 设置：sd-cli 用 6.0，diffusers 用 1.0，混用会导致异常。
- 确认 VAE 文件正确（`qwen_image_2.1_vae_bf16.safetensors`）。

## 透明图（RGBA）出不来

- prompt 中明确写 "transparent background" 或 "RGBA"。
- 确认输出为 PNG 格式（`.png` 才保留 alpha 通道）。
- 确认模型量化档位支持透明输出（Q4_K_M 应支持）。

## 图中文字乱码 / 渲染错误

- 把要渲染的文字用引号包裹在 prompt 中，明确 "reads \"...\"" 句式。
- 降低复杂度：长文本拆短，或先用 1024×1024 而非高分辨率。
- 文字渲染对量化档位敏感，Q4 档可能出现瑕疵，可尝试更高档（Q6_K/Q8_0，若显存允许）。

## 生成速度过慢

- 确认用的是 GPU 后端（Vulkan/CUDA）而非纯 CPU。
- 首次生成慢（模型加载）属正常，后续生成更快。
- 降低步数（20 → 15）可提速但可能降质量。
- CPU offload 会显著变慢，仅显存不足时启用。

## 许可 / 下载 401 错误

- 部分模型需在 Hugging Face 接受 license 并配置 HF token。
- 配置：`huggingface-cli login` 后重试下载。

## 安全与合规提示

> 基于社区对 Qwen-Image-2.1 官方 Base 权重的实测观察，仅供参考，不构成法律意见。

- **无内置运行时安全拦截器**：本地部署官方原始权重（Base model）时，模型代码层面没有提示词黑名单或图像遮黑/模糊过滤器，不会自动弹窗阻断或输出全黑占位图。
- **T2I 与 I2I 限制差异**：文生图（T2I）对敏感/成人提示词遵从度较高、限制较宽松；图生图/局部编辑（I2I）受训练阶段指令限制更多。具体行为随权重版本、量化档位、采样参数变化。
- **使用者自负合规责任**：提示词与生成结果由用户控制。使用本工具时必须遵守所在地法律法规，不得生成、传播或商业化儿童色情/性剥削、非自愿私密影像、暴力煽动、歧视仇恨等违法违规内容。
- **不适合无过滤的公众服务**：若接入公开或多人使用的产品，请自行增加内容审核、年龄验证、用户协议等合规机制。本仓库工具链不提供此类机制。
- **模型许可归原方所有**：Qwen-Image-2.1 权重与原始许可归阿里通义所有，本仓库仅提供部署与调用参考。
