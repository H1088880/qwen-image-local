# 命令参考（commands）

## 文生图（text-to-image）

```bash
sd-cli \
  --diffusion-model models/qwen-image-2.1-Q4_K_M.gguf \
  --vae models/qwen_image_2.1_vae_bf16.safetensors \
  --llm models/qwen3vl_8b_int8_convrot.safetensors \
  -p "a cartoon sloth mascot waving, flat vector illustration, bright colours" \
  --steps 20 --cfg-scale 6.0 --sampling-method euler \
  -W 1024 -H 1024 --diffusion-fa -o out/out.png
```

参数说明：

| 参数 | 值 | 说明 |
|---|---|---|
| `--diffusion-model` | `.gguf` 路径 | 扩散模型（DiT） |
| `--vae` | `.safetensors` 路径 | VAE 解码器 |
| `--llm` | `.safetensors` 路径 | 文本编码器 |
| `-p` / `--prompt` | 字符串 | 正向提示词 |
| `--steps` | 20 | 采样步数（sd-cli 默认） |
| `--cfg-scale` | 6.0 | 引导强度（sd-cli 用 6.0） |
| `--sampling-method` | euler | 采样器 |
| `-W` / `-H` | 宽/高 | 须被 32 整除 |
| `--diffusion-fa` | - | 开启 Flash Attention，省显存 |
| `-o` | 路径 | 输出文件 |
| `-s` / `--seed` | 整数 | 固定随机种子，默认 42 |

## 图像编辑（image-to-image / 指令编辑）

Qwen-Image-2.1 支持指令式编辑，用 `-i` 传输入图，prompt 写编辑指令：

```bash
sd-cli \
  --diffusion-model models/qwen-image-2.1-Q4_K_M.gguf \
  --vae models/qwen_image_2.1_vae_bf16.safetensors \
  --llm models/qwen3vl_8b_int8_convrot.safetensors \
  -i input.png \
  -p "change the background to a sunny beach, keep the subject unchanged" \
  --steps 20 --cfg-scale 6.0 --sampling-method euler \
  -o out/edited.png
```

编辑能力（模型原生支持）：
- 改背景 / 增删元素 / 变换风格（保持主体结构与身份）
- 局部编辑：用圆形标注、涂鸦标注或独立 mask 指定编辑区域
- 多参考图：最多 10 张参考图，保持人物/产品身份一致

## 透明图（RGBA 生成）

Qwen-Image-2.1 原生支持生成透明图与抠图。prompt 中明确要求透明背景：

```bash
sd-cli \
  --diffusion-model models/qwen-image-2.1-Q4_K_M.gguf \
  --vae models/qwen_image_2.1_vae_bf16.safetensors \
  --llm models/qwen3vl_8b_int8_convrot.safetensors \
  -p "a red apple on transparent background, RGBA" \
  --steps 20 --cfg-scale 6.0 --sampling-method euler \
  -o out/apple.png
```

## 图中文字渲染

模型擅长在图中渲染文字，prompt 中明确要渲染的文字内容：

```bash
-p "a neon shop sign that reads \"QWEN IMAGE 2.1\", rainy night, reflections on wet pavement"
```

## 低显存加固参数

8GB 或以下显存时追加/调整：

- `--diffusion-fa`：Flash Attention（省显存）
- 开 VAE tiling（`--vae-tiling`，如 sd-cli 支持）减少解码峰值显存
- 文本编码器 CPU offload（sd-cli 默认会把部分层放内存）
- 降分辨率：1024→768→512
- 降量化：Q4_K_M→Q4_0
- 保持 `--batch-size 1`（如参数存在）

## diffusers 方案（备选，需 24GB 或高配）

若用户有高配 GPU 且偏好 Python 生态：

```python
import torch
from diffusers import QwenImage21Pipeline
pipe = QwenImage21Pipeline.from_pretrained(
    "Qwen/Qwen-Image-2.1", torch_dtype=torch.bfloat16
).to("cuda")
image = pipe(
    prompt="A neon shop sign that reads \"QWEN IMAGE 2.1\", rainy night",
    width=2048, height=2048, num_inference_steps=40,
    generator=torch.Generator("cuda").manual_seed(42),
).images[0]
image.save("t2i_example.png")
```

注意：diffusers 方案步数用 40、CFG 用 1.0（禁用 CFG），与 sd-cli（20 步 / CFG 6.0）不同，按实际后端选用参数。
