# 把绿幕短视频抠成 640x360 的逐帧透明动画。
# 每段先统计整段人物范围，再统一缩放、脚底对齐，避免逐帧裁切把动作抖掉。

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

FFMPEG = Path(r"D:\dsh-pet-kitten\tools\ffmpeg-dl\ffmpeg.exe")
SRC = Path(r"D:\image")
OUT = Path(r"D:\dsh-pet-kitten\pet\kitten-animation\webm")
W, H = 640, 360
FEET_Y = 330
FPS = 24

CLIPS = {
    "图片生成绿幕视频 (1).mp4": "坐着",
    "图片生成绿幕视频 (2).mp4": "趴着",
    "图片生成绿幕视频 (3).mp4": "玩耍",
    "图片生成绿幕视频 (4).mp4": "动作四",
}


def frames_of(path: Path, size: tuple[int, int]) -> np.ndarray:
    sw, sh = size
    cmd = [
        str(FFMPEG), "-v", "error", "-i", str(path),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    raw = subprocess.run(cmd, capture_output=True).stdout
    frame_bytes = sw * sh * 3
    count = len(raw) // frame_bytes
    return np.frombuffer(raw[: count * frame_bytes], np.uint8).reshape(count, sh, sw, 3)


def probe_size(path: Path) -> tuple[int, int]:
    cmd = [str(FFMPEG), "-v", "error", "-i", str(path), "-f", "null", "-"]
    # size comes from the earlier probe; these clips are all 720x960
    return 720, 960


# 豆包水印在这四段里的位置（源视频 720x960）。只擦文字块，不碰猫。
WATERMARKS = {
    "图片生成绿幕视频 (1).mp4": (190, 790, 530, 900),
    "图片生成绿幕视频 (2).mp4": (545, 888, 710, 945),
    "图片生成绿幕视频 (3).mp4": (545, 888, 710, 945),
    "图片生成绿幕视频 (4).mp4": (545, 888, 715, 945),
}


def erase_watermark(frame: np.ndarray, box: tuple[int, int, int, int]) -> np.ndarray:
    x0, y0, x1, y1 = box
    out = frame.copy()
    sample = out[max(0, y0 - 18) : y0, x0:x1]
    if sample.size == 0:
        sample = out[y1 : min(out.shape[0], y1 + 18), x0:x1]
    if sample.size == 0:
        return out
    fill = np.median(sample.reshape(-1, 3), axis=0).astype(np.uint8)
    out[y0:y1, x0:x1] = fill
    return out


def key_alpha(frame: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    h, w = frame.shape[:2]
    border = np.concatenate([
        frame[:12].reshape(-1, 3),
        frame[-12:].reshape(-1, 3),
        frame[:, :12].reshape(-1, 3),
        frame[:, -12:].reshape(-1, 3),
    ]).astype(np.int16)
    key = np.median(border, axis=0)
    dist = np.abs(frame.astype(np.int16) - key).sum(axis=2)
    alpha = np.clip((dist - 16) / 26, 0, 1)
    alpha[:8, :] = 0
    alpha[-8:, :] = 0
    alpha[:, :8] = 0
    alpha[:, -8:] = 0
    rgb = frame.astype(np.int16)
    cap = np.maximum(rgb[:, :, 0], rgb[:, :, 2]) + 6
    rgb[:, :, 1] = np.minimum(rgb[:, :, 1], cap)
    return np.clip(rgb, 0, 255).astype(np.uint8), alpha


def union_box(frames: np.ndarray) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = frames.shape[2], frames.shape[1], 0, 0
    for frame in frames[::4]:
        _, alpha = key_alpha(frame)
        ys, xs = np.where(alpha > 0.45)
        if len(xs) == 0:
            continue
        x0, y0 = min(x0, int(xs.min())), min(y0, int(ys.min()))
        x1, y1 = max(x1, int(xs.max())), max(y1, int(ys.max()))
    pad = 12
    return max(0, x0 - pad), max(0, y0 - pad), min(frames.shape[2] - 1, x1 + pad), min(frames.shape[1] - 1, y1 + pad)


def place(rgb: np.ndarray, alpha: np.ndarray, box, scale: float) -> np.ndarray:
    x0, y0, x1, y1 = box
    crop_rgb = rgb[y0 : y1 + 1, x0 : x1 + 1]
    crop_a = alpha[y0 : y1 + 1, x0 : x1 + 1]
    ch, cw = crop_rgb.shape[:2]
    nw, nh = max(2, int(cw * scale)), max(2, int(ch * scale))
    # nearest-neighbor resize keeps the pipe dependency-free and fast enough at 24fps
    ys = np.clip((np.arange(nh) * ch / nh).astype(np.int32), 0, ch - 1)
    xs = np.clip((np.arange(nw) * cw / nw).astype(np.int32), 0, cw - 1)
    small_rgb = crop_rgb[ys][:, xs]
    small_a = (np.clip(crop_a[ys][:, xs], 0, 1) * 255).astype(np.uint8)
    canvas = np.zeros((H, W, 4), np.uint8)
    left = int(round(W / 2 - nw / 2))
    top = int(round(FEET_Y - nh))
    x_from, y_from = max(0, left), max(0, top)
    x_to, y_to = min(W, left + nw), min(H, top + nh)
    sx, sy = x_from - left, y_from - top
    canvas[y_from:y_to, x_from:x_to, :3] = small_rgb[sy : sy + (y_to - y_from), sx : sx + (x_to - x_from)]
    canvas[y_from:y_to, x_from:x_to, 3] = small_a[sy : sy + (y_to - y_from), sx : sx + (x_to - x_from)]
    return canvas


def encode(name: str, canvases: list[np.ndarray]) -> None:
    dest = OUT / f"{name}.webm"
    cmd = [
        str(FFMPEG), "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "pipe:0",
        "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
        "-b:v", "0", "-crf", "32", "-an", "-r", str(FPS),
        str(dest),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    for canvas in canvases:
        proc.stdin.write(canvas.tobytes())
    proc.stdin.close()
    err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    code = proc.wait()
    if code != 0:
        raise RuntimeError(err[-1500:])
    alpha = canvases[len(canvases) // 2][:, :, 3]
    print(f"{name}: {len(canvases)} frames, {dest.stat().st_size // 1024} KiB, transparent {float((alpha < 8).mean()):.3f}")


def convert(src_name: str, dest_name: str) -> None:
    src = SRC / src_name
    sw, sh = probe_size(src)
    frames = frames_of(src, (sw, sh))
    box_wm = WATERMARKS.get(src_name)
    if box_wm is not None:
        frames = np.stack([erase_watermark(frame, box_wm) for frame in frames])
    box = union_box(frames)
    bw, bh = box[2] - box[0] + 1, box[3] - box[1] + 1
    scale = min(520 / bw, 280 / bh)
    canvases = []
    for frame in frames:
        rgb, alpha = key_alpha(frame)
        canvases.append(place(rgb, alpha, box, scale))
    encode(dest_name, canvases)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.webm"):
        old.unlink()
    for src_name, dest_name in CLIPS.items():
        convert(src_name, dest_name)


if __name__ == "__main__":
    main()
