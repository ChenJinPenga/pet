# 把抠好的 Q 版立绘做成 dsh-pet 能播的透明动作。
# 舞台 640x360，脚底对齐 y=330，默认朝左。
# 会动的部分：呼吸、转身、走路、被拎起、点击、余额。
# 走路用骑车姿势做轮子滚动和身体起伏，窗口本身会按 lead/tail 平移。

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

CUT = Path(r"D:\dsh-pet-kitten\tools\kitten-frames\cut")
OUT = Path(r"D:\dsh-pet-kitten\pet\kitten-animation\webm")
WORK = Path(r"D:\dsh-pet-kitten\tools\kitten-frames\motion")
FFMPEG = Path(r"D:\dsh-pet-kitten\tools\ffmpeg-dl\ffmpeg.exe")

W, H = 640, 360
FEET_Y = 330
FPS = 12
BODY_H = 250


def load(name: str) -> Image.Image:
    im = Image.open(CUT / f"{name}.png").convert("RGBA")
    scale = BODY_H / im.height
    nw, nh = max(2, int(im.width * scale)), BODY_H
    return im.resize((nw, nh), Image.Resampling.LANCZOS)


def blank() -> Image.Image:
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def paste(canvas: Image.Image, sprite: Image.Image, cx: float, feet: float, scale: float = 1.0, squash: float = 1.0) -> None:
    sw = max(2, int(sprite.width * scale))
    sh = max(2, int(sprite.height * scale * squash))
    frame = sprite.resize((sw, sh), Image.Resampling.BILINEAR)
    x = int(round(cx - sw / 2))
    y = int(round(feet - sh))
    canvas.alpha_composite(frame, (x, y))


def pose(name: str, n: int, fn) -> list[Image.Image]:
    sprite = load(name)
    return [fn(sprite, i, n) for i in range(n)]


def idle_frames() -> list[Image.Image]:
    n = int(4 * FPS)

    def frame(sprite, i, n):
        t = i / n
        breath = math.sin(t * math.tau)
        im = blank()
        paste(im, sprite, W / 2, FEET_Y - 3 * breath, 1 + 0.03 * breath, 1 - 0.035 * breath)
        return im

    return pose("坐", n, frame)


def turn_frames() -> list[Image.Image]:
    # 侧面压扁到几乎消失，再从另一侧展开。渲染端在播完后翻转朝向。
    n = int(0.7 * FPS)
    sprite = load("坐")

    def frame(i):
        t = i / max(1, n - 1)
        width = abs(math.cos(t * math.pi))
        width = max(0.08, width)
        im = blank()
        sw = max(2, int(sprite.width * width))
        sh = sprite.height
        frame_im = sprite.resize((sw, sh), Image.Resampling.BILINEAR)
        x = int(round(W / 2 - sw / 2))
        y = int(round(FEET_Y - sh))
        im.alpha_composite(frame_im, (x, y))
        return im

    return [frame(i) for i in range(n)]


def walk_frames() -> list[Image.Image]:
    n = int(2.4 * FPS)
    sprite = load("骑车")

    def frame(i):
        t = i / n
        bob = abs(math.sin(t * math.tau * 2)) * 8
        lean = 1 + 0.04 * math.sin(t * math.tau * 2)
        im = blank()
        paste(im, sprite, W / 2 + 6 * math.sin(t * math.tau * 2), FEET_Y - bob, lean, 1 / lean)
        return im

    return [frame(i) for i in range(n)]


def drag_frames() -> list[Image.Image]:
    n = int(1.6 * FPS)
    sprite = load("站")

    def frame(i):
        t = i / n
        wobble = math.sin(t * math.tau * 2)
        im = blank()
        paste(im, sprite, W / 2 + 10 * wobble, FEET_Y - 42, 0.94, 1.08)
        return im

    return [frame(i) for i in range(n)]


def click_frames(which: str) -> list[Image.Image]:
    n = int(1.2 * FPS)
    name = "玩" if which == "happy" else "玩2" if which == "shy" else "坐"
    sprite = load(name)

    def frame(i):
        t = i / n
        if t < 0.22:
            k = t / 0.22
            squash, lift = 1 - 0.18 * k, 0
        else:
            u = (t - 0.22) / 0.78
            bounce = math.sin(u * math.pi) * (1 - u)
            squash, lift = 1 + 0.08 * bounce, 16 * bounce
        dx = 0
        if which == "shy":
            dx = 12 * math.sin(t * math.pi)
        elif which == "tsun":
            dx = 8 * math.sin(t * math.tau * 2)
        im = blank()
        paste(im, sprite, W / 2 + dx, FEET_Y - lift, 1, squash)
        return im

    return [frame(i) for i in range(n)]


def balance_frames(level: int) -> list[Image.Image]:
    n = int(2.4 * FPS)
    sprite = load("坐")
    lifts = (16, 8, 0, -4, -10, -16)
    scales = (1.05, 1.02, 1.0, 0.98, 0.94, 0.9)

    def frame(i):
        t = i / n
        bob = math.sin(t * math.tau) * max(1, 6 - level)
        im = blank()
        paste(im, sprite, W / 2, FEET_Y - lifts[level] - bob, scales[level])
        return im

    return [frame(i) for i in range(n)]


def write_frames(frames: list[Image.Image], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob("*.png"):
        old.unlink()
    for i, im in enumerate(frames):
        im.save(folder / f"{i:04d}.png")


def encode(folder: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(FFMPEG), "-y", "-hide_banner",
        "-framerate", str(FPS),
        "-i", str(folder / "%04d.png"),
        "-c:v", "libvpx-vp9",
        "-pix_fmt", "yuva420p",
        "-auto-alt-ref", "0",
        "-b:v", "0", "-crf", "30",
        "-an", "-r", str(FPS),
        str(dest),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-1500:])
    print(f"{dest.name} {dest.stat().st_size // 1024} KiB")


def main() -> None:
    jobs = {
        "待机呼吸": idle_frames(),
        "转身": turn_frames(),
        "骑车": walk_frames(),
        "被拎起": drag_frames(),
        "开心": click_frames("happy"),
        "害羞": click_frames("shy"),
        "傲娇": click_frames("tsun"),
    }
    for level in range(6):
        jobs[f"余额{level}"] = balance_frames(level)
    for name, frames in jobs.items():
        folder = WORK / name
        write_frames(frames, folder)
        encode(folder, OUT / f"{name}.webm")


if __name__ == "__main__":
    main()
