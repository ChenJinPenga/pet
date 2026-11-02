# 用 u2net 把 D:\image 里的 Q 版静图抠成透明立绘，并按脚底对齐放到 640x360 舞台上。
# 不依赖 rembg 包：模型直接用 onnxruntime 跑。

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter

MODEL = Path(r"D:\dsh-pet-kitten\tools\u2net\u2net.onnx")
SRC = Path(r"D:\image")
OUT = Path(r"D:\dsh-pet-kitten\tools\kitten-frames\cut")
NAMES = {
    "sit.png": "坐",
    "cycle.png": "骑车",
    "play.png": "玩",
    "play2.png": "玩2",
    "image_918005171093202.png": "站",
}


def remove_bg(session: ort.InferenceSession, im: Image.Image) -> Image.Image:
    rgb = im.convert("RGB")
    w, h = rgb.size
    resized = rgb.resize((320, 320), Image.Resampling.LANCZOS)
    arr = np.asarray(resized).astype(np.float32) / 255.0
    arr = (arr - 0.485) / 0.229
    blob = arr.transpose(2, 0, 1)[None]
    pred = session.run(None, {session.get_inputs()[0].name: blob})[0]
    mask = pred[0, 0]
    mask = (mask - mask.min()) / (mask.max() - mask.min() + 1e-6)
    alpha = Image.fromarray((mask * 255).astype(np.uint8), "L").resize((w, h), Image.Resampling.LANCZOS)
    alpha = alpha.filter(ImageFilter.GaussianBlur(0.6))
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def trim(im: Image.Image, threshold: int = 24) -> Image.Image:
    a = np.asarray(im)[:, :, 3]
    ys, xs = np.where(a > threshold)
    if len(xs) == 0:
        return im
    pad = 8
    x0, y0 = max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad)
    x1, y1 = min(im.width, int(xs.max()) + pad + 1), min(im.height, int(ys.max()) + pad + 1)
    return im.crop((x0, y0, x1, y1))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    session = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    for src_name, label in NAMES.items():
        src = SRC / src_name
        cut = trim(remove_bg(session, Image.open(src)))
        cut.save(OUT / f"{label}.png")
        a = np.asarray(cut)[:, :, 3]
        ys, xs = np.where(a > 24)
        print(f"{label}: {cut.size} fg={float((a>24).mean()):.3f} bbox={xs.min()},{ys.min()}-{xs.max()},{ys.max()}")
        bg = Image.new("RGBA", (cut.width // 3, cut.height // 3), (48, 52, 56, 255))
        small = cut.resize(bg.size, Image.Resampling.LANCZOS)
        bg.alpha_composite(small)
        bg.convert("RGB").save(OUT / f"{label}-preview.jpg", quality=85)


if __name__ == "__main__":
    main()
