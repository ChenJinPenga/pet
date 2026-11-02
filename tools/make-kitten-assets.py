# 从一张小猫照片生成 dsh-pet 可播放的透明动画。
# 照片没有绿幕、也没有可分离轮廓，所以做成圆形肖像徽章，而不是假装抠出全身。
# 输出：640x360、yuva420p、libvpx-vp9，脚底对齐 FEET_Y=330。

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SRC = Path(r"D:\image\88.jpg")
OUT_DIR = Path(r"D:\dsh-pet-kitten\pet\kitten-animation\webm")
WORK = Path(r"D:\dsh-pet-kitten\tools\kitten-frames")
FFMPEG = Path(r"D:\dsh-pet-kitten\tools\ffmpeg-dl\ffmpeg.exe")

W, H = 640, 360
FPS = 12
IDLE_SEC = 4.0
DRAG_SEC = 2.0
CLICK_SEC = 1.6
CX = W // 2
# 徽章中心略高于脚底线，底缘落在 y=330 附近
BASE_CY = 214
BASE_D = 228


def make_badge(src: Path) -> Image.Image:
    im = Image.open(src).convert("RGB")
    # 竖图居中裁成正方形，保留脸部所在的上中部
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = max(0, int(h * 0.08))
    if top + side > h:
        top = h - side
    crop = im.crop((left, top, left + side, top + side))
    d = 460
    crop = crop.resize((d, d), Image.Resampling.LANCZOS)
    arr = np.asarray(crop).astype(np.float32)
    yy, xx = np.mgrid[0:d, 0:d]
    r = np.sqrt((xx - (d - 1) / 2) ** 2 + (yy - (d - 1) / 2) ** 2)
    radius = d * 0.46
    # 软边圆形 alpha
    alpha = np.clip((radius - r) / 2.2, 0, 1)
    # 轻微暗角，让徽章边缘收得住
    shade = np.clip(1 - np.maximum(r - radius * 0.72, 0) / (radius * 0.34) * 0.28, 0.72, 1)
    rgb = np.clip(arr * shade[..., None], 0, 255).astype(np.uint8)
    rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])
    badge = Image.fromarray(rgba, "RGBA")
    # 一圈暖色描边，和照片的木色背景分开
    ring = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    ring_px = np.zeros((d, d, 4), np.uint8)
    edge = (r >= radius - 7) & (r <= radius + 1.5)
    ring_px[edge] = (255, 236, 214, 230)
    ring = Image.fromarray(ring_px, "RGBA")
    badge = Image.alpha_composite(badge, ring)
    return badge


def paste_badge(canvas: Image.Image, badge: Image.Image, cx: float, cy: float, scale: float, alpha: float = 1.0) -> None:
    d = max(2, int(round(BASE_D * scale)))
    sprite = badge.resize((d, d), Image.Resampling.LANCZOS)
    if alpha < 0.999:
        arr = np.asarray(sprite).astype(np.float32)
        arr[..., 3] *= alpha
        sprite = Image.fromarray(arr.astype(np.uint8), "RGBA")
    x = int(round(cx - d / 2))
    y = int(round(cy - d / 2))
    canvas.alpha_composite(sprite, (x, y))


def blank() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def frames_idle(badge: Image.Image) -> list[Image.Image]:
    n = int(IDLE_SEC * FPS)
    out = []
    for i in range(n):
        t = i / n
        # 慢呼吸：垂直轻微挤压 + 上下 4px
        breath = math.sin(t * math.tau)
        scale = 1 + 0.035 * breath
        cy = BASE_CY - 4 * breath
        im = blank()
        paste_badge(im, badge, CX, cy, scale)
        out.append(im)
    return out


def frames_drag(badge: Image.Image) -> list[Image.Image]:
    n = int(DRAG_SEC * FPS)
    out = []
    for i in range(n):
        t = i / n
        wobble = math.sin(t * math.tau * 2)
        # 被拎起：整体上移，轻微左右晃，纵向拉长一点
        cy = BASE_CY - 46 + 6 * wobble
        cx = CX + 8 * math.sin(t * math.tau)
        scale = 0.92 + 0.03 * wobble
        im = blank()
        paste_badge(im, badge, cx, cy, scale)
        out.append(im)
    return out


def frames_click(badge: Image.Image, kind: str) -> list[Image.Image]:
    n = int(CLICK_SEC * FPS)
    out = []
    for i in range(n):
        t = i / n
        # 0.18 处压扁，之后回弹过冲
        if t < 0.18:
            k = t / 0.18
            squash = 1 - 0.22 * k
            cy = BASE_CY + 10 * k
            rot_shift = 0
        else:
            u = (t - 0.18) / 0.82
            # ease-out 回弹
            bounce = math.sin(u * math.pi) * (1 - u)
            squash = 1 + 0.08 * bounce
            cy = BASE_CY - 18 * bounce
            rot_shift = 0
        if kind == "shy":
            cx = CX + 10 * math.sin(t * math.pi)
            scale = squash * 0.96
        elif kind == "happy":
            cx = CX
            scale = squash * (1.04 if t < 0.45 else 1.0)
            cy -= 8 * math.sin(min(t, 0.5) / 0.5 * math.pi)
        else:
            cx = CX + (6 if t < 0.3 else -4) * (1 - t)
            scale = squash
        im = blank()
        paste_badge(im, badge, cx, cy, scale)
        out.append(im)
    return out


def frames_balance(badge: Image.Image, level: int) -> list[Image.Image]:
    # 6 档：从轻快到发蔫。用高低和缩放区分，不画文字（镜像会反）。
    n = int(2.4 * FPS)
    lifts = (18, 10, 0, -6, -14, -22)
    scales = (1.06, 1.03, 1.0, 0.97, 0.93, 0.88)
    out = []
    for i in range(n):
        t = i / n
        bob = math.sin(t * math.tau) * (6 - level)
        im = blank()
        paste_badge(im, badge, CX, BASE_CY - lifts[level] + bob, scales[level])
        out.append(im)
    return out


def write_frames(frames: list[Image.Image], folder: Path) -> None:
    if folder.exists():
        for p in folder.glob("*.png"):
            p.unlink()
    folder.mkdir(parents=True, exist_ok=True)
    for i, im in enumerate(frames):
        im.save(folder / f"{i:04d}.png")


def encode(folder: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(FFMPEG),
        "-y",
        "-hide_banner",
        "-framerate",
        str(FPS),
        "-i",
        str(folder / "%04d.png"),
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-b:v",
        "0",
        "-crf",
        "32",
        "-an",
        "-r",
        str(FPS),
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])
    print(f"encoded {dest.name} {dest.stat().st_size // 1024} KiB")


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    badge = make_badge(SRC)
    badge.save(WORK / "badge.png")
    jobs = {
        "待机呼吸": frames_idle(badge),
        "被拎起": frames_drag(badge),
        "开心": frames_click(badge, "happy"),
        "害羞": frames_click(badge, "shy"),
        "傲娇": frames_click(badge, "tsun"),
    }
    for i in range(6):
        jobs[f"余额{i}"] = frames_balance(badge, i)
    for name, frames in jobs.items():
        folder = WORK / name
        write_frames(frames, folder)
        encode(folder, OUT_DIR / f"{name}.webm")
    print("done", len(jobs), "clips ->", OUT_DIR)


if __name__ == "__main__":
    main()
