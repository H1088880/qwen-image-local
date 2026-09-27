# 部署指南（setup-guide）

## 一、安装 stable-diffusion.cpp (sd-cli)

### Windows（预编译，推荐）

1. 打开 `https://github.com/leejet/stable-diffusion.cpp/releases`
2. 下载最新 release 中适合的 zip：
   - **首选 Vulkan 版** `sd-master-*-bin-win-vulkan-x64.zip`：开箱即用，自动识别 NVIDIA/AMD/Intel 显卡（实测 RTX 3050 直接识别为 Vulkan0）
   - cuda12 版 `sd-master-*-bin-win-cuda12-x64.zip`：⚠️ 预编译包**不带** cudart64_12/cublas64_12/cublasLt64_12.dll，缺这些会静默回退 CPU（`--list-devices` 只显示 CPU）。需另装 CUDA Toolkit 12 或补齐这 3 个 DLL 才能用 GPU
   - 纯 CPU → `sd-master-*-bin-win-cpu-x64.zip`
3. 解压，得到 `sd-cli.exe`（可能位于 `bin/` 子目录）。
4. 验证 GPU 识别：`./sd-cli.exe --list-devices`，应看到 `Vulkan0 <显卡名>`（或 CUDA 设备）。

### 国内下载 GitHub release 加速（实测）

GitHub release 直连不稳定（HTTP 000 / 超时）时，加镜像前缀：

```bash
curl -L -o sd-cli.zip \
  "https://gh-proxy.com/https://github.com/leejet/stable-diffusion.cpp/releases/download/master-920-2f88688/sd-master-2f88688-bin-win-vulkan-x64.zip"
```

### 从源码编译（需要 CUDA/Vulkan 加速时）

```bash
git clone --recursive https://github.com/leejet/stable-diffusion.cpp.git
cd stable-diffusion.cpp
mkdir build && cd build
cmake ..                       # 基础 CPU
cmake .. -DGGML_USE_CUBLAS=ON  # CUDA (NVIDIA)
cmake .. -DGGML_USE_VULKAN=ON  # Vulkan (跨平台)
cmake --build . --config Release
# 产物在 ./bin/Release/
```

## 二、下载三件套模型

⚠️ **三件套分散在三个独立仓库**（很多教程误写成同一仓库子目录）：

| 组件 | 仓库 | 文件名 | 实测大小 |
|---|---|---|---|
| 扩散模型 | `unsloth/Qwen-Image-2.1-GGUF` | `qwen-image-2.1-Q4_K_M.gguf` | 3.91 GB |
| 文本编码器 | `unsloth/Qwen3-VL-8B-Instruct-GGUF` | `Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf` | 4.79 GB |
| VAE | `unsloth/Qwen-Image-2.1-FP8` | `vae/qwen_image_2.1_vae_bf16.safetensors` | 645 MB |

### 国内镜像下载（实测 hf-mirror 可用，HF 直连常 502）

```bash
# 扩散模型（也可换 Q8_0/Q6_K/Q5_K_M/Q4_K_S/Q3_K_XL/Q2_K 等档位）
curl -L -C - -o qwen-image-2.1-Q4_K_M.gguf \
  "https://hf-mirror.com/unsloth/Qwen-Image-2.1-GGUF/resolve/main/qwen-image-2.1-Q4_K_M.gguf"
# 文本编码器（GGUF 格式，UD-Q4_K_XL 为官方推荐动态量化）
curl -L -C - -o Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf \
  "https://hf-mirror.com/unsloth/Qwen3-VL-8B-Instruct-GGUF/resolve/main/Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf"
# VAE
curl -L -C - -o qwen_image_2.1_vae_bf16.safetensors \
  "https://hf-mirror.com/unsloth/Qwen-Image-2.1-FP8/resolve/main/vae/qwen_image_2.1_vae_bf16.safetensors"
```

海外环境把 `hf-mirror.com` 换回 `huggingface.co` 即可，或用 `huggingface-cli download <repo> <file> --local-dir .`。

### 验证下载是否成功

- 文件大小须与上表一致；若只有 15 字节且内容为 `Entry not found`，说明路径错了（常见于把三件套误当同一仓库）。
- 下载中断可用 `curl -C -` 断点续传。

## 三、校验完整性

仓库提供 `SHA256SUMS` 文件。下载后校验：

```bash
# Linux/macOS
sha256sum -c SHA256SUMS
# Windows PowerShell
Get-FileHash .\qwen-image-2.1-Q4_K_M.gguf -Algorithm SHA256
# 与 SHA256SUMS 中对应条目比对
```

## 四、目录组织建议（实测结构）

```
qwen-image-2.1/               # 建议放空间充足的盘（需 ~9.5GB）
├── vulkan/
│   └── sd-cli.exe            # Vulkan 版推理引擎（含 ggml-vulkan.dll）
├── models/
│   ├── qwen-image-2.1-Q4_K_M.gguf          # 扩散模型 3.91GB
│   ├── Qwen3-VL-8B-Instruct-UD-Q4_K_XL.gguf  # 文本编码器 4.79GB
│   └── qwen_image_2.1_vae_bf16.safetensors # VAE 645MB
├── out/                      # 输出目录
└── run.log                   # 运行日志（排查 OOM 用）
```

## 五、磁盘/内存预估（实测数据）

- 磁盘：三件套共约 9.4 GB，加上 sd-cli 预留 12GB
- 显存：DiT Q4_K_M 权重约 4GB + 激活，`--max-vram 6` 预算 6GB 时 8GB 卡可跑通
- 系统内存：文本编码器走 CPU 需 ~5GB；⚠️ 16GB 内存且占用率 88% 时会失败，出图前先关大程序（实测空闲内存 <1GB 时即使 512×512 也会 OOM）

## 六、实测性能参考（RTX 3050 8GB + i5-12400F + 16GB RAM，512×512）

| 阶段 | 耗时 |
|---|---|
| 文本编码器加载+编码（CPU） | ~133 s |
| 扩散模型加载 | ~126 s |
| 采样 20 步（Vulkan GPU） | ~162 s（2.1 s/it） |
| VAE 解码（CPU） | ~75 s |
| **总计（首次）** | **~448 s（7.5 分钟）** |

后续生成若进程不退出可复用已加载权重；分辨率升到 768/1024 时采样与 VAE 时间相应增加。
