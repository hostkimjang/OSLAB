"""Edit the fleet's console recordings into the OSLab introduction video.

Every screen in the video comes from a continuous Proxmox console recording
made by fleet.py. The editor aligns the recordings at each workflow's start,
lays all of them out as one wall, zooms into featured workflows, and marks a
workflow as passed at the moment its guest checks passed.
"""

from __future__ import annotations

import argparse
import bisect
import colorsys
import hashlib
import json
import math
import random
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
VM_W, VM_H = 1280, 800
INK, MUTED, DIM = (241, 245, 249), (148, 163, 184), (100, 116, 139)
MINT, CORAL = (94, 234, 212), (251, 113, 133)
PANEL, EDGE = (14, 21, 36), (38, 50, 71)
CARD = (48, 104, 1376, 860)
COLUMN_X, COLUMN_W = 1468, 404
PROXY = (444, 278)
GRID_X, GRID_Y, GRID_GAP = 36, 300, 10
TILE_W = (W - 2 * GRID_X - 7 * GRID_GAP) / 8
TILE_H = TILE_W * 10 / 16
OPEN_RATE = 8.0  # Run seconds per video second on the opening wall.
INTRO = 3.0  # Video seconds the agents take to reach their VMs.
ARROW = [(0, 0), (0, 16.5), (4.1, 12.7), (6.9, 19.2), (9.5, 18.1), (6.8, 11.8), (12.2, 11.8)]


def clamp(value, low=0.0, high=1.0):
    return min(max(value, low), high)


def ease(value):
    value = clamp(value)
    return 4 * value ** 3 if value < .5 else 1 - (-2 * value + 2) ** 3 / 2


def ease_out(value):
    return 1 - (1 - clamp(value)) ** 3


def mix(start, end, amount):
    return start + (end - start) * amount


def blend(first, second, amount):
    return tuple(round(mix(a, b, amount)) for a, b in zip(first, second))


class Fonts:
    FILES = {"regular": "Geist-Regular", "medium": "Geist-Medium", "semibold": "Geist-SemiBold",
             "mono": "GeistMono-Medium", "mono-bold": "GeistMono-SemiBold"}

    def __init__(self, folder):
        self.paths = {}
        for style, stem in self.FILES.items():
            found = sorted(folder.rglob(f"{stem}.ttf")) or sorted(folder.rglob(f"{stem}.otf"))
            if not found:
                raise FileNotFoundError(f"Missing font {stem} under {folder}")
            self.paths[style] = found[0]
        self.cache = {}

    def __call__(self, style, size):
        if (style, size) not in self.cache:
            self.cache[style, size] = ImageFont.truetype(str(self.paths[style]), size)
        return self.cache[style, size]


def text(canvas, xy, value, font, fill=INK, alpha=1.0, anchor="la"):
    if alpha <= 0.01 or not value:
        return
    if alpha >= .99:
        ImageDraw.Draw(canvas).text(xy, value, font=font, fill=fill, anchor=anchor)
        return
    left, top, right, bottom = ImageDraw.Draw(canvas).textbbox(xy, value, font=font, anchor=anchor)
    left, top, right, bottom = math.floor(left), math.floor(top), math.ceil(right), math.ceil(bottom)
    layer = Image.new("RGBA", (right - left + 4, bottom - top + 4), (*fill, 0))
    ImageDraw.Draw(layer).text((xy[0] - left + 2, xy[1] - top + 2), value, font=font,
                               fill=(*fill, round(255 * alpha)), anchor=anchor)
    canvas.paste(layer, (left - 2, top - 2), layer)


def wrap(value, font, width):
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines, line = [], ""
    for word in value.split():
        trial = f"{line} {word}".strip()
        if line and measure.textlength(trial, font=font) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line] if line else lines


def fit(value, font, width):
    """Shorten a label with an ellipsis so that it fits in width."""
    measure = ImageDraw.Draw(Image.new("L", (1, 1)))
    if measure.textlength(value, font=font) <= width:
        return value
    while value and measure.textlength(value + "…", font=font) > width:
        value = value[:-1]
    return value.rstrip() + "…"


def box(canvas, rect, radius, fill=None, outline=None, width=1, alpha=1.0):
    if alpha <= 0.01:
        return
    x, y, w, h = rect
    left, top = math.floor(x), math.floor(y)
    layer = Image.new("RGBA", (math.ceil(x + w) - left + 1, math.ceil(y + h) - top + 1), (0, 0, 0, 0))
    level = round(255 * alpha)
    ImageDraw.Draw(layer).rounded_rectangle(
        (x - left, y - top, x - left + w, y - top + h), radius,
        fill=(*fill, level) if fill else None, outline=(*outline, level) if outline else None, width=width)
    canvas.paste(layer, (left, top), layer)


def rounded_mask(size, rect, radius, alpha=1.0):
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(rect, radius, fill=round(255 * alpha))
    return mask


def place(canvas, image, rect, crop=None, radius=0, alpha=1.0):
    """Draw a sub-pixel positioned image, optionally cropped, rounded and translucent."""
    x, y, w, h = rect
    left, top = max(0, math.floor(x)), max(0, math.floor(y))
    right, bottom = min(W, math.ceil(x + w)), min(H, math.ceil(y + h))
    if right <= left or bottom <= top or w < 1 or h < 1 or alpha <= 0.01:
        return
    sx, sy, sw, sh = crop or (0, 0, image.width, image.height)
    factor = int(min(sw / w, sh / h))
    if factor >= 2:
        # Box-filter large reductions first so small tiles do not shimmer.
        image = image.reduce(factor)
        sx, sy, sw, sh = sx / factor, sy / factor, sw / factor, sh / factor
    kx, ky = sw / w, sh / h
    region = image.transform((right - left, bottom - top), Image.Transform.AFFINE,
                             (kx, 0, sx + (left - x) * kx, 0, ky, sy + (top - y) * ky),
                             resample=Image.Resampling.BICUBIC)
    if radius <= 0 and alpha >= .99:
        canvas.paste(region, (left, top))
        return
    mask = rounded_mask(region.size, (x - left, y - top, x - left + w - 1, y - top + h - 1), radius, alpha)
    canvas.paste(region, (left, top), mask)


def backdrop():
    image = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(image)
    for row in range(H):
        draw.line((0, row, W, row), fill=blend((8, 11, 19), (11, 17, 30), row / (H - 1)))
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse((-420, -520, 980, 520), fill=34)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    image.paste(Image.new("RGB", (W, H), (34, 92, 98)), (0, 0), glow)
    for gy in range(18, H, 36):
        for gx in range(18, W, 36):
            draw.point((gx, gy), fill=(30, 39, 56))
    return image


def card_shadow(w, h, radius):
    pad = 70
    alpha = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(alpha).rounded_rectangle((pad, pad + 18, pad + w, pad + h + 18), radius, fill=150)
    layer = Image.new("RGBA", alpha.size, (0, 0, 0, 0))
    layer.putalpha(alpha.filter(ImageFilter.GaussianBlur(30)))
    return layer, pad


def brand(canvas, fonts, x, y, size=28, alpha=1.0):
    unit = size / 28
    for offset, width in ((0, 9), (13, 7)):
        points = [(x + offset * unit, y + 20 * unit), (x + (offset + 10) * unit, y),
                  (x + (offset + 10 + width) * unit, y), (x + (offset + width) * unit, y + 20 * unit)]
        layer = Image.new("RGBA", canvas.size if alpha < .99 else (1, 1))
        if alpha >= .99:
            ImageDraw.Draw(canvas).polygon(points, fill=MINT)
        else:
            ImageDraw.Draw(layer).polygon(points, fill=(*MINT, round(255 * alpha)))
            canvas.paste(layer, (0, 0), layer)
    text(canvas, (x + 38 * unit, y + 10 * unit), "OSLab", fonts("semibold", size), INK, alpha, "lm")


def agent_color(index):
    """Bright colors that stay distinct between neighbouring agents, a golden ratio apart in hue."""
    red, green, blue = colorsys.hls_to_rgb((.47 + index * .618034) % 1.0, .66, .8)
    return round(red * 255), round(green * 255), round(blue * 255)


def cursor_sprite(color, height):
    """An arrow pointer with a dark outline and a soft shadow, and the offset of its tip."""
    scale = 4
    unit = height / 19.2 * scale
    pad = 8 * scale
    size = (math.ceil(12.2 * unit / scale) * scale + 2 * pad, math.ceil(19.2 * unit / scale) * scale + 2 * pad)
    points = [(pad + x * unit, pad + y * unit) for x, y in ARROW]
    shadow = Image.new("L", size, 0)
    ImageDraw.Draw(shadow).polygon([(x + 1.5 * scale, y + 2.5 * scale) for x, y in points], fill=130)
    sprite = Image.new("RGBA", size, (2, 4, 8, 0))
    sprite.putalpha(shadow.filter(ImageFilter.GaussianBlur(2.5 * scale)))
    arrow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(arrow).polygon(points, fill=(*color, 255), outline=(8, 11, 19, 255), width=round(1.3 * scale))
    sprite.alpha_composite(arrow)
    return sprite.resize((size[0] // scale, size[1] // scale), Image.Resampling.LANCZOS), pad // scale


def tag_sprite(label, color, font):
    """A name tag in the agent's color, as multiplayer editors label each cursor."""
    width = math.ceil(ImageDraw.Draw(Image.new("L", (1, 1))).textlength(label, font=font)) + round(font.size * 1.1)
    height = round(font.size * 1.7)
    tag = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tag)
    draw.rounded_rectangle((0, 0, width - 1, height - 1), round(height * .3), fill=(*color, 255))
    draw.text((width / 2, height / 2), label, font=font, fill=(6, 9, 16), anchor="mm")
    return tag


def faded(sprite, alpha):
    if alpha >= .99:
        return sprite
    copy = sprite.copy()
    copy.putalpha(sprite.getchannel("A").point(lambda value: round(value * alpha)))
    return copy


def bezier(points, u):
    (x0, y0), (x1, y1), (x2, y2), (x3, y3) = points
    a, b, c, d = (1 - u) ** 3, 3 * u * (1 - u) ** 2, 3 * u * u * (1 - u), u ** 3
    return a * x0 + b * x1 + c * x2 + d * x3, a * y0 + b * y1 + c * y2 + d * y3


@dataclass
class Case:
    id: str
    title: str
    scenario: str
    steps: list
    checks: list
    start: float
    finish: float
    t0: float
    video: Path
    stages: dict
    inputs: list
    wave: int
    proxy: Path | None = None

    def offset(self, epoch):
        return epoch - self.t0

    @property
    def result(self):
        return self.stages.get("stage-3", self.finish)

    @property
    def duration(self):
        return self.finish - self.start


def load_cases(run_dir):
    fleet = json.loads((run_dir / "fleet.json").read_text(encoding="utf-8"))
    chosen = {}
    for wave in fleet["waves"]:
        for case_id, result in wave.get("cases", {}).items():
            meta = wave.get("recordings", {}).get(case_id)
            if result["result"] == "pass" and meta and meta["status"] == "complete":
                chosen[case_id] = (wave["wave"], result, meta)
    cases = []
    for case_id in sorted(chosen):
        wave, result, meta = chosen[case_id]
        row = json.loads((run_dir / f"case-{case_id}.json").read_text(encoding="utf-8"))
        stages = {}
        for shot in row["timeline"]:
            stages.setdefault(shot["stage"], shot["time"])
        if not result["started"] <= stages["stage-0"] <= stages["stage-3"] <= result["finished"]:
            raise ValueError(f"Case {case_id} timeline does not match its recorded run")
        cases.append(Case(case_id, row["title"], row["scenario"], row["actions"], row["checks"],
                          result["started"], result["finished"], meta["t0"],
                          run_dir / "recordings" / f"wave-{wave}" / meta["file"], stages, row["inputs"], wave))
    return cases


def make_proxies(cases, ffmpeg, folder):
    """Downscale each run to a 10 fps tile clip from its start to its result screen."""
    folder.mkdir(parents=True, exist_ok=True)
    running = []
    for case in cases:
        case.proxy = folder / f"{case.id}-{case.wave}.mkv"
        if case.proxy.exists():
            continue
        length = case.result - case.start + .6
        running.append(subprocess.Popen([
            ffmpeg, "-v", "error", "-y", "-ss", f"{case.offset(case.start):.3f}", "-i", str(case.video),
            "-t", f"{length:.3f}", "-vf", f"fps=10,scale={PROXY[0]}:{PROXY[1]}:flags=area",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "15", "-pix_fmt", "yuv444p", "-g", "10",
            str(case.proxy)]))
        if len(running) >= 8:
            running.pop(0).wait()
    for process in running:
        if process.wait():
            raise RuntimeError("Proxy encoding failed")


class Reader:
    """Read frames from a video in time order, seeking when a jump is large."""

    def __init__(self, ffmpeg, path, size=(VM_W, VM_H), fps=30):
        self.ffmpeg, self.path, self.size, self.fps = ffmpeg, path, size, fps
        self.process = None
        self.origin = 0.0
        self.index = -1
        self.frame = Image.new("RGB", size, (8, 11, 19))

    def open(self, offset):
        self.close()
        scale = f",scale={self.size[0]}:{self.size[1]}:flags=area" if self.size != (VM_W, VM_H) else ""
        self.process = subprocess.Popen([
            self.ffmpeg, "-v", "error", "-ss", f"{offset:.3f}", "-i", str(self.path),
            "-vf", f"fps={self.fps}{scale}", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=self.size[0] * self.size[1] * 3 * 4)
        self.origin = offset
        self.index = -1

    def at(self, offset):
        offset = max(0.0, offset)
        target = round((offset - self.origin) * self.fps)
        if self.process is None or target < self.index or target - self.index > self.fps * 12:
            self.open(offset)
            target = 0
        length = self.size[0] * self.size[1] * 3
        while self.index < target:
            data = self.process.stdout.read(length)
            if len(data) < length:
                self.index = target  # End of the clip: hold its last frame.
                break
            self.frame = Image.frombytes("RGB", self.size, data)
            self.index += 1
        return self.frame

    def close(self):
        if self.process is not None:
            self.process.stdout.close()
            self.process.kill()
            self.process.wait()
            self.process = None


class Remap:
    """Map output seconds to source epochs: near real time around actions, faster in between."""

    def __init__(self, start, end, events, duration, slow=1.25, before=.7, after=1.1, cap=4.0, holds=()):
        holds = sorted((epoch, length) for epoch, length in holds if start <= epoch <= end)
        duration -= sum(length for _, length in holds)
        windows = []
        for event in sorted(e for e in events if start <= e <= end):
            span = [max(start, event - before), min(end, event + after)]
            if windows and span[0] <= windows[-1][1]:
                windows[-1][1] = max(windows[-1][1], span[1])
            else:
                windows.append(span)
        interest = sum(b - a for a, b in windows)
        gap = end - start - interest
        if interest:
            slow = min(cap, max(slow, interest / (duration * .78)))
        rest = duration - interest / slow
        fast = gap / rest if rest > .05 and gap > 0 else slow
        if fast <= slow or not windows:
            slow = fast = (end - start) / duration
            windows = []
        self.segments = []
        cursor, out = start, 0.0
        for a, b in windows + [[end, end]]:
            for low, high, speed in ((cursor, a, fast), (a, b, slow)):
                while high > low:
                    # Freeze on a moment the viewer needs time to read.
                    stop = next((epoch for epoch, _ in holds if low <= epoch < high), high)
                    if stop > low:
                        length = (stop - low) / speed
                        self.segments.append((out, out + length, low, stop, speed))
                        out += length
                    if stop < high:
                        epoch, pause = holds.pop(0)
                        self.segments.append((out, out + pause, epoch, epoch, 0.0))
                        out += pause
                    low = stop
            cursor = max(cursor, b)
        self.end = end
        self.duration = out
        self.starts = [segment[0] for segment in self.segments]

    def source(self, t):
        index = max(0, bisect.bisect_right(self.starts, t) - 1)
        out_a, out_b, src_a, src_b, speed = self.segments[index]
        return min(src_b, src_a + (t - out_a) * speed) if t < self.duration else self.end

    def output(self, epoch):
        for out_a, out_b, src_a, src_b, speed in self.segments:
            if epoch <= src_b:
                return out_a + (max(0.0, epoch - src_a) / speed if speed else 0.0)
        return self.duration

    def speed(self, t):
        if t >= self.duration:
            return 0.0
        index = max(0, bisect.bisect_right(self.starts, t) - 1)
        # Keep the label steady through brief fast-forward hops between actions.
        while index > 0 and self.segments[index][4] and self.segments[index][1] - self.segments[index][0] < .45:
            index -= 1
        return self.segments[index][4]


def speed_label(speed):
    if speed <= 0:
        return "PAUSED"
    return f"{speed:.1f}× SPEED" if speed < 2 else f"{round(speed)}× SPEED"


def roi_state(roi):
    """A camera state (center x, center y, zoom) that frames a region of the VM screen."""
    if roi is None:
        return VM_W / 2, VM_H / 2, 1.0
    x0, y0, x1, y1 = roi
    width = max(x1 - x0, (y1 - y0) * 1.6)
    zoom = clamp(VM_W / width, 1.0, 2.4)
    half_w, half_h = VM_W / zoom / 2, VM_H / zoom / 2
    return clamp((x0 + x1) / 2, half_w, VM_W - half_w), clamp((y0 + y1) / 2, half_h, VM_H - half_h), zoom


def camera_crop(state):
    cx, cy, zoom = state
    w, h = VM_W / zoom, VM_H / zoom
    return cx - w / 2, cy - h / 2, w, h


class Camera:
    def __init__(self, keys, move=.55):
        self.keys = sorted(keys)
        self.move = move

    def state(self, t):
        times = [key[0] for key in self.keys]
        index = bisect.bisect_right(times, t) - 1
        if index < 0:
            return self.keys[0][1]
        current = self.keys[index][1]
        if index + 1 >= len(self.keys):
            return current
        arrive, target = self.keys[index + 1]
        travel = min(self.move, arrive - self.keys[index][0])
        amount = ease((t - (arrive - travel)) / travel) if travel > 0 else 0.0
        return (mix(current[0], target[0], amount), mix(current[1], target[1], amount),
                math.exp(mix(math.log(current[2]), math.log(target[2]), amount)))


def key_label(keys):
    names = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "win": "Win", "escape": "Esc",
             "enter": "Enter", "return": "Enter", "space": "Space", "home": "Home", "end": "End"}
    return " + ".join(names.get(key.lower(), key.upper() if len(key) == 1 else key.title()) for key in keys)


class Track:
    """An agent's pointer: parked at its last recorded MCP click and gliding into the next one."""

    def __init__(self, case):
        self.clicks = [(row["time"], row["x"], row["y"]) for row in case.inputs if row["device"] == "mouse"]
        self.click_times = [moment for moment, _, _ in self.clicks]
        self.key_times = sorted(row["time"] for row in case.inputs if row["device"] == "keyboard")

    def position(self, epoch, glide):
        index = bisect.bisect_right(self.click_times, epoch)
        start = self.clicks[index - 1][1:] if index else (VM_W / 2, VM_H / 2)
        if index == len(self.clicks):
            return start
        moment, x, y = self.clicks[index]
        span = min(glide, moment - self.click_times[index - 1]) if index else glide
        if span <= 0 or epoch < moment - span:
            return start
        amount = ease((epoch - moment + span) / span)
        distance = max(math.dist(start, (x, y)), 1.0)
        # Bow the path a little, as the recorded MCP moves did on their way to each click.
        bend = math.sin(math.pi * amount) * min(60.0, distance * .12)
        return (start[0] + (x - start[0]) * amount - bend * (y - start[1]) / distance,
                start[1] + (y - start[1]) * amount + bend * (x - start[0]) / distance)

    def last_click(self, epoch):
        index = bisect.bisect_right(self.click_times, epoch)
        return self.click_times[index - 1] if index else None

    def typing(self, epoch, window):
        index = bisect.bisect_right(self.key_times, epoch)
        return index > 0 and epoch - self.key_times[index - 1] < window


@dataclass
class Feature:
    case: Case
    task: str
    beats: list
    finding: str = ""
    verified: str = ""
    duration: float = 7.0
    hold: float = .9
    begin: float | None = None
    pauses: list = field(default_factory=list)
    roi: tuple | None = None
    fixed_stage: str = "stage-2"
    remap: Remap = None
    camera: Camera = None
    reader: Reader = None
    clicks: list = field(default_factory=list)
    chips: list = field(default_factory=list)

    def prepare(self, ffmpeg):
        case = self.case
        events = [case.stages[name] for name in ("stage-0", "stage-1", "stage-2", "stage-3")]
        events += [row["time"] for row in case.inputs]
        begin = self.begin if self.begin is not None else min(case.stages["stage-0"] - 2.5, min(e for e, _ in self.beats))
        self.remap = Remap(max(case.start, begin), case.finish + .3, events, self.duration - self.hold, holds=self.pauses)
        keys = [(max(0.0, self.remap.output(epoch)), roi_state(roi)) for epoch, roi in self.beats]
        self.camera = Camera(keys)
        self.reader = Reader(ffmpeg, case.video)
        self.clicks = [(self.remap.output(row["time"]), row["x"], row["y"]) for row in case.inputs if row["device"] == "mouse"]
        typed = []
        for row in case.inputs:
            if row["device"] != "keyboard":
                continue
            moment = self.remap.output(row["time"])
            single = len(row["keys"]) == 1 and len(row["keys"][0]) == 1
            if single and typed and typed[-1][2] and moment - typed[-1][0] < .6:
                typed[-1] = (moment, typed[-1][1] + row["keys"][0], True)
            else:
                typed.append((moment, row["keys"][0] if single else key_label(row["keys"]), single))
        self.chips = [(moment, f"Type  {label}" if single else label) for moment, label, single in typed]

    def epoch(self, t):
        return self.remap.source(t)

    def frame(self, t):
        # Hold the result screen while the guest checks run after the program closes.
        return self.reader.at(self.case.offset(min(self.epoch(t), self.case.result + .15)))


class Film:
    def __init__(self, args, cases):
        self.args = args
        self.fonts = Fonts(args.fonts)
        self.cases = cases
        self.by_id = {case.id: case for case in cases}
        self.background = backdrop()
        self.shadow, self.shadow_pad = card_shadow(CARD[2], CARD[3], 18)
        self.tiles = {case.id: Reader(args.ffmpeg, case.proxy, PROXY, 10) for case in cases}
        self.checks_total = sum(len(case.checks) for case in cases)
        self.colors = {case.id: agent_color(index) for index, case in enumerate(cases)}
        self.tracks = {case.id: Track(case) for case in cases}
        self.labels = {case.id: fit(case.title, self.fonts("medium", 15), TILE_W - 30) for case in cases}
        self.pointers = {}
        for case in cases:
            color = self.colors[case.id]
            for size, height, font in (("wall", 19, self.fonts("mono-bold", 12)), ("screen", 34, self.fonts("mono-bold", 20))):
                self.pointers[case.id, size] = (*cursor_sprite(color, height), tag_sprite(f"Agent {case.id}", color, font), height)

    # Wall of every recorded run --------------------------------------------------------

    def tile_rect(self, index, camera=(1.0, W / 2, H / 2)):
        zoom, cx, cy = camera
        col, row = index % 8, index // 8
        x = GRID_X + col * (TILE_W + GRID_GAP)
        y = GRID_Y + row * (TILE_H + GRID_GAP)
        return (x - cx) * zoom + W / 2, (y - cy) * zoom + H / 2, TILE_W * zoom, TILE_H * zoom

    def wall(self, canvas, tau, camera=(1.0, W / 2, H / 2), labels=1.0, rate=OPEN_RATE, skip=None, cursors=1.0,
             reveal=None):
        fonts = self.fonts
        draw = ImageDraw.Draw(canvas)
        shown = []
        for index, case in enumerate(self.cases):
            rect = self.tile_rect(index, camera)
            x, y, w, h = rect
            if case.id == skip or x > W or y > H or x + w < 0 or y + h < 0:
                continue
            hold = case.result - case.start + .3
            opened = 1.0 if reveal is None else reveal(index)
            if opened < 1:
                # An empty slot waits for its agent, and the tile opens from its center on arrival.
                box(canvas, rect, 6, fill=PANEL, outline=EDGE, alpha=.9)
                if opened > 0:
                    grow = mix(.82, 1.0, ease_out(opened))
                    place(canvas, self.tiles[case.id].at(clamp(tau, 0, hold)),
                          (x + w * (1 - grow) / 2, y + h * (1 - grow) / 2, w * grow, h * grow), radius=6,
                          alpha=ease_out(opened))
                continue
            place(canvas, self.tiles[case.id].at(clamp(tau, 0, hold)), rect)
            passed = tau >= case.duration
            draw.rectangle((x - 1, y - 1, x + w, y + h), outline=MINT if passed else EDGE, width=2 if passed else 1)
            if labels > .01:
                label = fonts("medium", 15)
                width = draw.textlength(self.labels[case.id], font=label)
                box(canvas, (x + 6, y + h - 30, min(w - 12, width + 18), 24), 6, fill=(6, 9, 16), alpha=.82 * labels)
                text(canvas, (x + 15, y + h - 18), self.labels[case.id], label, INK, labels, "lm")
                if passed:
                    age = (tau - case.duration) / rate
                    pop = 1 + .35 * (1 - ease_out(age / .3))
                    bw, bh = 62 * pop, 22 * pop
                    box(canvas, (x + w - 8 - bw, y + 8, bw, bh), 6, fill=MINT, alpha=labels)
                    text(canvas, (x + w - 8 - bw / 2, y + 8 + bh / 2), "PASS", fonts("mono-bold", round(13 * pop)),
                         (6, 30, 28), labels, "mm")
                else:
                    pulse = .55 + .45 * math.sin(tau * 2.2 + index)
                    box(canvas, (x + w - 18, y + 9, 9, 9), 5, fill=MINT, alpha=pulse * labels)
            shown.append((case, rect))
        if cursors > .01:
            for case, rect in shown:
                self.wall_cursor(canvas, case, rect, tau, rate, cursors)

    def cursor(self, canvas, case_id, point, size="wall", alpha=1.0, typing=False, phase=0.0):
        """Draw an agent's arrow and name tag with the arrow's tip at point."""
        if alpha <= .01:
            return
        sprite, tip, tag, height = self.pointers[case_id, size]
        x, y = round(point[0]), round(point[1])
        arrow = faded(sprite, alpha)
        canvas.paste(arrow, (x - tip, y - tip), arrow)
        tag_x, tag_y = x + round(height * .5), y + round(height * .85)
        label = faded(tag, alpha)
        canvas.paste(label, (tag_x, tag_y), label)
        if typing:
            # A typing bubble beside the tag while the agent sends keys.
            color, size = self.colors[case_id], tag.height
            left = tag_x + tag.width + 3
            box(canvas, (left, tag_y, size * 1.7, size), size / 2, fill=PANEL, outline=color, alpha=alpha)
            for dot in range(3):
                lift = .5 + .5 * math.sin(phase * 9 - dot * 1.1)
                radius = size * .11
                cx, cy = left + size * (.45 + .4 * dot), tag_y + size / 2 - lift * size * .12
                box(canvas, (cx - radius, cy - radius, 2 * radius, 2 * radius), radius, fill=color,
                    alpha=alpha * (.45 + .55 * lift))

    def ripple(self, canvas, point, color, age, length=.45, reach=28):
        if not 0 <= age < length:
            return
        radius = mix(4, reach, ease_out(age / length))
        size = round(2 * reach + 16)
        middle = size / 2
        ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(ring).ellipse((middle - radius, middle - radius, middle + radius, middle + radius),
                                     outline=(*color, round(255 * (1 - age / length))), width=max(2, round(reach / 9)))
        canvas.paste(ring, (round(point[0] - middle), round(point[1] - middle)), ring)

    def wall_cursor(self, canvas, case, rect, tau, rate, alpha):
        """Draw a tile's agent at its recorded pointer position, with its clicks and key presses."""
        x, y, w, h = rect
        track = self.tracks[case.id]
        epoch = case.start + clamp(tau, 0, case.duration)
        px, py = track.position(epoch, .45 * rate)
        point = (x + px * w / VM_W, y + py * h / VM_H)
        clicked = track.last_click(epoch)
        if clicked is not None:
            self.ripple(canvas, point, self.colors[case.id], (epoch - clicked) / rate)
        # A finished agent dims while its tile keeps the PASS badge.
        rest = mix(1.0, .35, ease_out((tau - case.duration) / rate / .5)) if tau >= case.duration else 1.0
        self.cursor(canvas, case.id, point, "wall", alpha * rest,
                    typing=tau < case.duration and track.typing(epoch, .3 * rate), phase=tau / rate)

    def screen_pointer(self, canvas, case, clicks, t, rect, crop, alpha=1.0):
        """Show the agent's cursor gliding into each recorded click on a zoomed screen."""
        x, y, w, h = rect
        start = (VM_W / 2, VM_H / 2)
        for moment, px, py in clicks:
            age = t - moment
            if age < -.6:
                return
            if age < .9:
                amount = ease((age + .5) / .5)
                vx, vy = mix(start[0], px, amount), mix(start[1], py, amount)
                sx, sy = x + (vx - crop[0]) * w / crop[2], y + (vy - crop[1]) * h / crop[3]
                if x <= sx <= x + w and y <= sy <= y + h:
                    target = (x + (px - crop[0]) * w / crop[2], y + (py - crop[1]) * h / crop[3])
                    self.ripple(canvas, target, self.colors[case.id], age, .7, 46)
                    self.cursor(canvas, case.id, (sx, sy), "screen",
                                alpha * clamp((age + .6) / .15) * clamp((.9 - age) / .3))
                return
            start = (px, py)

    def counters(self, canvas, tau, alpha=1.0, rate=OPEN_RATE, active=None):
        fonts = self.fonts
        passed = [case for case in self.cases if tau >= case.duration]
        if active is None:
            active = len(self.cases) - len(passed)
        checks = sum(len(case.checks) for case in passed)
        y = 920
        x = 48
        for label, value, color in (("ACTIVE AGENTS", str(active), INK),
                                    ("PASSED", f"{len(passed)}/{len(self.cases)}", MINT), ("GUEST CHECKS", str(checks), INK)):
            text(canvas, (x, y), label, fonts("mono", 18), MUTED, alpha)
            text(canvas, (x, y + 26), value, fonts("mono-bold", 40), color, alpha)
            x += 300
        minutes, seconds = divmod(int(max(tau, 0)), 60)
        text(canvas, (W - 48, y), f"T+{minutes:02d}:{seconds:02d}", fonts("mono-bold", 40), INK, alpha, "ra")
        text(canvas, (W - 48, y + 50), f"{round(rate)}× TIME-LAPSE", fonts("mono", 18), MUTED, alpha, "ra")
        note = fonts("regular", 17)
        text(canvas, (48, H - 46), "Each tile is a continuous console recording of its own Windows 11 VM, recorded in "
             "waves of up to 8 VMs and aligned at each run's start.", note, DIM, alpha, "ls")
        text(canvas, (48, H - 20), "Cursors show where each scripted agent clicked through MCP. Movement between clicks "
             "is interpolated.", note, DIM, alpha, "ls")

    def headline(self, canvas, alpha=1.0):
        fonts = self.fonts
        brand(canvas, fonts, 48, 40, 30, alpha)
        text(canvas, (48, 104), f"{len(self.cases)} Windows VMs. {len(self.cases)} real programs.",
             fonts("semibold", 72), INK, alpha)
        text(canvas, (50, 202), "A test agent drives each VM through the OSLab MCP server. "
             "OSLab checks every result inside the guest.", fonts("regular", 30), MUTED, alpha)

    # Featured workflows --------------------------------------------------------------

    def screen(self, canvas, feature, t, rect=CARD, radius=18, alpha=1.0, overlays=True):
        image = feature.frame(t)
        state = feature.camera.state(t)
        crop = camera_crop(state)
        x, y, w, h = rect
        if alpha > .99 and (w, h) == CARD[2:]:
            canvas.paste(self.shadow, (round(x) - self.shadow_pad, round(y) - self.shadow_pad), self.shadow)
        place(canvas, image, rect, crop, radius, alpha)
        box(canvas, rect, radius, outline=EDGE, alpha=alpha)
        if not overlays:
            return
        self.screen_pointer(canvas, feature.case, feature.clicks, t, rect, crop, alpha)
        for moment, label in reversed(feature.chips):
            age = t - moment
            if 0 <= age < 1.0:
                font = self.fonts("mono-bold", 30)
                width = ImageDraw.Draw(canvas).textlength(label, font=font) + 48
                fade = min(1.0, (1.0 - age) / .25, age / .08 + .2)
                lift = 10 * (1 - ease_out(age / .2))
                chip = (x + w / 2 - width / 2, y + h + 26 - lift, width, 52)
                box(canvas, chip, 12, fill=(20, 30, 48), outline=EDGE, alpha=fade)
                text(canvas, (x + w / 2, y + h + 52 - lift), label, font, INK, fade, "mm")
                break

    def column(self, canvas, feature, t, alpha=1.0, number=None):
        if alpha <= .01:
            return
        fonts, case = self.fonts, feature.case
        epoch = feature.epoch(t)
        x, y = COLUMN_X, CARD[1]
        text(canvas, (x, y + 4), f"PROGRAM {case.id} OF {len(self.cases)}", fonts("mono", 18), MUTED, alpha)
        y += 40
        for line in wrap(case.title, fonts("semibold", 46), COLUMN_W):
            text(canvas, (x, y), line, fonts("semibold", 46), INK, alpha)
            y += 54
        for line in wrap(feature.task, fonts("regular", 28), COLUMN_W):
            text(canvas, (x, y + 6), line, fonts("regular", 28), MUTED, alpha)
            y += 36
        y += 34
        marks = [case.stages["stage-0"], case.stages["stage-1"], case.stages["stage-2"], case.finish]
        steps = case.steps[:4]
        marks = marks[len(marks) - len(steps):]
        for index, step in enumerate(steps):
            done = epoch >= marks[index]
            active = not done and (index == 0 or epoch >= marks[index - 1])
            color = MINT if done else INK if active else DIM
            box(canvas, (x, y + 4, 26, 26), 13, fill=MINT if done else None, outline=color, width=2, alpha=alpha)
            if done:
                draw = ImageDraw.Draw(canvas)
                draw.line((x + 7, y + 17, x + 12, y + 22, x + 20, y + 11), fill=(6, 30, 28), width=3)
            lines = wrap(step, fonts("medium", 26), COLUMN_W - 44)
            for line in lines:
                text(canvas, (x + 42, y + 1), line, fonts("medium", 26), INK if (done or active) else DIM, alpha)
                y += 34
            y += 18
        panel = (x, CARD[1] + CARD[3] - 230, COLUMN_W, 230)
        verified = epoch >= case.finish
        fixed = epoch >= case.stages.get(feature.fixed_stage, case.result)
        found = feature.finding and epoch >= case.stages["stage-1"] and not fixed
        tone = MINT if verified else CORAL if found else INK if fixed else MUTED
        box(canvas, panel, 16, fill=PANEL, outline=tone if (verified or found) else EDGE, width=2, alpha=alpha)
        text(canvas, (x + 24, panel[1] + 26), "GUEST CHECK", fonts("mono", 18), MUTED, alpha)
        if verified:
            status, detail = "PASS", feature.verified
        elif found:
            status, detail = "FOUND", feature.finding
        elif fixed:
            status, detail = "CHECKING", "Reading the result back inside the guest"
        else:
            status, detail = "RUNNING", feature.case.scenario
        text(canvas, (x + 24, panel[1] + 56), status, fonts("mono-bold", 44), tone, alpha)
        for index, line in enumerate(wrap(detail, fonts("regular", 24), COLUMN_W - 48)[:3]):
            text(canvas, (x + 24, panel[1] + 116 + index * 30), line, fonts("regular", 24), INK, alpha)
        if verified:
            text(canvas, (x + COLUMN_W - 24, panel[1] + 26), f"{len(case.checks)} checks", fonts("mono", 18), MINT, alpha, "ra")

    def feature_header(self, canvas, feature, t, alpha=1.0):
        brand(canvas, self.fonts, 48, 42, 26, alpha)
        speed = feature.remap.speed(t)
        text(canvas, (CARD[0] + CARD[2], 52), f"REAL CONSOLE RECORDING  ·  {speed_label(speed)}",
             self.fonts("mono", 20), MUTED, alpha, "rm")

    def feature_frame(self, feature, t, offset=0.0, alpha=1.0, column=1.0):
        canvas = self.background.copy()
        self.feature_into(canvas, feature, t, offset, alpha, column)
        return canvas

    def feature_into(self, canvas, feature, t, offset=0.0, alpha=1.0, column=1.0):
        rect = (CARD[0] + offset, CARD[1], CARD[2], CARD[3])
        self.screen(canvas, feature, t, rect, alpha=alpha)
        self.column(canvas, feature, t, alpha * column)
        self.feature_header(canvas, feature, t, alpha * column)

    # How it works ------------------------------------------------------------------------

    def diagram(self, canvas, t):
        fonts = self.fonts
        title_alpha = ease_out(t / .4)
        text(canvas, (W / 2, 170), "How OSLab runs each workflow", fonts("semibold", 60), INK, title_alpha, "mm")
        nodes = [
            ((310, 470), "MCP client", "a test script, Codex or Claude"),
            ((770, 470), "OSLab MCP", "screenshot · click · move · keys"),
            ((1230, 470), "Proxmox console", "VNC over WebSocket"),
            ((1650, 470), "Windows 11 VM", "a fresh clone for each run"),
            ((1650, 760), "QEMU Guest Agent", "reads files inside the guest"),
            ((1010, 760), "Guest checks", "hashes · cells · DB rows · media"),
        ]
        links = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
        size = (380, 170)
        shown = []
        for index, ((cx, cy), name, detail) in enumerate(nodes):
            appear = ease_out((t - .35 - .28 * index) / .35)
            shown.append(appear)
            if appear <= 0:
                continue
            rect = (cx - size[0] / 2, cy - size[1] / 2 + 18 * (1 - appear), *size)
            box(canvas, rect, 18, fill=PANEL, outline=EDGE, width=2, alpha=appear)
            text(canvas, (cx, rect[1] + 62), name, fonts("semibold", 38), INK, appear, "mm")
            text(canvas, (cx, rect[1] + 116), detail, fonts("regular", 24), MUTED, appear, "mm")
        draw = ImageDraw.Draw(canvas)
        for index, (a, b) in enumerate(links):
            progress = ease((t - .35 - .28 * b - .1) / .35)
            if progress <= 0:
                continue
            (ax, ay), (bx, by) = nodes[a][0], nodes[b][0]
            if ay == by:
                sign = 1 if bx > ax else -1
                start, end = (ax + sign * size[0] / 2, ay), (bx - sign * size[0] / 2, by)
            else:
                start, end = (ax, ay + size[1] / 2), (bx, by - size[1] / 2)
            tip = (mix(start[0], end[0], progress), mix(start[1], end[1], progress))
            draw.line((*start, *tip), fill=(56, 74, 99), width=4)
            if progress >= 1:
                for phase in (0.0, .5):
                    cycle = (t * .9 + phase + index * .17) % 1
                    px, py = mix(start[0], end[0], cycle), mix(start[1], end[1], cycle)
                    draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=MINT)
        pass_alpha = ease_out((t - 2.2) / .4)
        if pass_alpha > 0:
            rect = (450, 700, 300, 120)
            box(canvas, rect, 18, fill=(10, 40, 40), outline=MINT, width=2, alpha=pass_alpha)
            text(canvas, (600, 742), "PASS", fonts("mono-bold", 44), MINT, pass_alpha, "mm")
            text(canvas, (600, 790), "or the exact failure", fonts("regular", 22), INK, pass_alpha, "mm")
            progress = ease((t - 2.3) / .3)
            draw.line((820, 760, mix(820, 750, progress), 760), fill=(56, 74, 99), width=4)
        note = ease_out((t - 2.8) / .5)
        text(canvas, (W / 2, 960), "It runs in the background. Your own mouse and keyboard stay free.",
             fonts("medium", 32), MINT, note, "mm")

    # End card ------------------------------------------------------------------------------

    def end_card(self, canvas, t):
        fonts = self.fonts
        shade = Image.new("RGB", (W, H), (6, 9, 15))
        canvas.paste(shade, (0, 0), Image.new("L", (W, H), round(205 * ease_out(t / .5))))
        a = ease_out((t - .2) / .5)
        brand(canvas, fonts, W / 2 - 245, 330, 96, a)
        text(canvas, (W / 2, 520), "Disposable Windows VMs for real-world QA", fonts("regular", 44), INK, a, "mm")
        b = ease_out((t - .5) / .5)
        text(canvas, (W / 2, 600), f"{len(self.cases)}/{len(self.cases)} programs passed  ·  "
             f"{self.checks_total} checks verified in the guest", fonts("mono", 30), MINT, b, "mm")
        c = ease_out((t - .8) / .5)
        text(canvas, (W / 2, 760), "github.com/hostkimjang/OSLAB", fonts("semibold", 44), INK, c, "mm")
        text(canvas, (W / 2, 820), "Includes an MCP server for Codex and Claude", fonts("regular", 28), MUTED, c, "mm")


class Story:
    """The edit: a list of timed shots rendered by the Film."""

    def __init__(self, film, features, montage, args):
        self.film = film
        self.features = features
        self.montage = montage
        self.shots = []
        self.duration = 0.0
        self.tau = args.open_tau
        self.open_length = INTRO + 5.6
        self.arrivals = self.dispatch()
        self.add(self.open_length, self.opening)
        self.push_tau = self.wall_tau(self.open_length)
        self.push_camera = self.open_camera(self.open_length)
        self.add(1.35, self.push_in)
        for index, feature in enumerate(features):
            self.add(feature.duration, lambda t, f=feature: film.feature_frame(f, t))
            if index + 1 < len(features):
                self.add(.6, lambda t, a=feature, b=features[index + 1]: self.slide(a, b, t))
        self.add(.7, self.pull_out)
        self.add(6.6, self.how)
        for group in montage:
            self.add(4.2, lambda t, g=group: self.quad(g, t))
        self.final_tau = self.push_tau + 1.35 * OPEN_RATE
        last = max(case.duration for case in film.cases) + 1.5
        self.final_rate = (last - self.final_tau) / 5.5
        self.add(5.5, self.finale)
        self.add(3.6, self.ending)

    def add(self, length, render):
        self.shots.append((length, render))
        self.duration += length

    def frame(self, t):
        for length, render in self.shots:
            if t < length:
                return render(t)
            t -= length
        return self.shots[-1][1](self.shots[-1][0])

    def wall_tau(self, t):
        return self.tau + (t - INTRO) * OPEN_RATE

    def open_camera(self, t):
        """Drift slowly toward the middle of the wall while it plays."""
        zoom = mix(1.0, 1.03, ease(t / self.open_length))
        middle = GRID_Y + 2 * (TILE_H + GRID_GAP) - GRID_GAP / 2
        return zoom, W / 2, middle - (middle - H / 2) / zoom

    def dispatch(self):
        """Launch and arrival times of the agents flying in from the left edge, nearest slots first."""
        film = self.film
        jitter = random.Random(32)
        order = sorted(range(len(film.cases)), key=lambda index: film.tile_rect(index)[0] + jitter.uniform(0, 260))
        plan = {}
        for rank, index in enumerate(order):
            launch = .3 + rank * .038 + jitter.uniform(0, .05)
            flight = .7 + film.tile_rect(index)[0] / 2400 + jitter.uniform(0, .15)
            plan[index] = (launch, launch + flight, jitter.uniform(-1, 1))
        return plan

    def flights(self, canvas, t, camera, tau):
        """Agents fly in to their VMs and stay parked while each tile opens."""
        film = self.film
        middle = GRID_Y + 2 * (TILE_H + GRID_GAP)
        trails = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        trail = ImageDraw.Draw(trails)
        flying = []
        for index, case in enumerate(film.cases):
            launch, arrival, swing = self.arrivals[index]
            if not launch <= t < arrival + .35:
                continue
            x, y, w, h = film.tile_rect(index, camera)
            px, py = film.tracks[case.id].position(case.start + max(tau, 0.0), .45 * OPEN_RATE)
            target = (x + px * w / VM_W, y + py * h / VM_H)
            origin = (-50, middle + 170 * swing)
            path = (origin, (origin[0] + 420, origin[1] + 140 * swing), (target[0] - 260, target[1] - 120 * swing), target)
            progress = ease((t - launch) / (arrival - launch))
            color = film.colors[case.id]
            if t < arrival:
                for step in range(1, 9):
                    tx, ty = bezier(path, max(0.0, progress - step * .02))
                    radius = 3.4 * (1 - step / 9)
                    trail.ellipse((tx - radius, ty - radius, tx + radius, ty + radius),
                                  fill=(*color, round(170 * (1 - step / 9))))
            else:
                film.ripple(canvas, target, color, t - arrival, .5, 34)
            flying.append((case.id, bezier(path, progress)))
        canvas.paste(trails, (0, 0), trails)
        for case_id, point in flying:
            film.cursor(canvas, case_id, point, "wall")

    def opening(self, t):
        film = self.film
        canvas = film.background.copy()
        tau = self.wall_tau(t)
        camera = self.open_camera(t)
        film.wall(canvas, max(tau, 0.0), camera, reveal=lambda index: (t - self.arrivals[index][1]) / .35)
        self.flights(canvas, t, camera, tau)
        # The first frame doubles as the player's poster, so the title is visible from the start.
        film.headline(canvas)
        arrived = [case for index, case in enumerate(film.cases) if t >= self.arrivals[index][1]]
        film.counters(canvas, max(tau, 0.0), active=sum(tau < case.duration for case in arrived))
        return canvas

    def push_in(self, t, length=1.35):
        film, feature = self.film, self.features[0]
        index = [case.id for case in film.cases].index(feature.case.id)
        tau = self.push_tau + t * OPEN_RATE
        p = ease(t / length)
        start = self.push_camera
        x0, y0, _, _ = film.tile_rect(index, start)
        zoom = math.exp(mix(math.log(start[0]), math.log(CARD[2] / TILE_W), p))
        sx, sy = mix(x0, CARD[0], p), mix(y0, CARD[1], p)
        wx, wy = GRID_X + index % 8 * (TILE_W + GRID_GAP), GRID_Y + index // 8 * (TILE_H + GRID_GAP)
        # Keep the tile's top-left corner on a straight path while the zoom grows exponentially.
        camera = (zoom, wx - (sx - W / 2) / zoom, wy - (sy - H / 2) / zoom)
        canvas = film.background.copy()
        film.wall(canvas, tau, camera, labels=1 - clamp(p * 4), skip=feature.case.id, cursors=1 - clamp(p * 4))
        canvas = Image.blend(canvas, film.background, clamp(p * 1.6))
        rect = film.tile_rect(index, camera)
        tile = film.tiles[feature.case.id].at(clamp(tau, 0, feature.case.result - feature.case.start))
        place(canvas, tile, rect, radius=18 * p)
        place(canvas, feature.frame(0), rect, camera_crop(feature.camera.state(0)), 18 * p, clamp((p - .35) / .4))
        fade = 1 - clamp(p * 3)
        film.headline(canvas, fade)
        film.counters(canvas, tau, fade)
        film.column(canvas, feature, 0, clamp((p - .82) / .18))
        film.feature_header(canvas, feature, 0, clamp((p - .82) / .18))
        return canvas

    def slide(self, outgoing, incoming, t, length=.6):
        film = self.film
        p = ease(t / length)
        canvas = film.background.copy()
        out_alpha, in_alpha = 1 - clamp(p * 1.4), clamp(p * 1.4 - .4)
        if out_alpha > 0:
            film.screen(canvas, outgoing, outgoing.duration, (CARD[0] - p * 140, CARD[1], CARD[2], CARD[3]),
                        alpha=out_alpha, overlays=False)
        if in_alpha > 0:
            film.screen(canvas, incoming, 0, (CARD[0] + (1 - p) * 140, CARD[1], CARD[2], CARD[3]),
                        alpha=in_alpha, overlays=False)
        film.column(canvas, outgoing, outgoing.duration, 1 - clamp(p * 2))
        film.column(canvas, incoming, 0, clamp(p * 2 - 1))
        brand(canvas, film.fonts, 48, 42, 26)
        return canvas

    def pull_out(self, t, length=.7, last=None):
        film = self.film
        p = ease(t / length)
        canvas = self.diagram_background()
        last = last or self.features[-1]
        scale = mix(1.0, .82, p)
        rect = (CARD[0] + CARD[2] * (1 - scale) / 2, CARD[1] + CARD[3] * (1 - scale) / 2, CARD[2] * scale, CARD[3] * scale)
        film.screen(canvas, last, last.duration, rect, alpha=1 - p, overlays=False)
        return canvas

    def diagram_background(self):
        if not hasattr(self, "_diagram_background"):
            canvas = self.film.background.copy()
            self.film.wall(canvas, self.final_tau, labels=0, cursors=0)
            blurred = canvas.filter(ImageFilter.GaussianBlur(14))
            shade = Image.new("RGB", (W, H), (6, 9, 15))
            blurred.paste(shade, (0, 0), Image.new("L", (W, H), 200))
            self._diagram_background = blurred
        return self._diagram_background.copy()

    def how(self, t):
        canvas = self.diagram_background()
        self.film.diagram(canvas, t)
        return canvas

    def quad(self, group, t):
        film = self.film
        canvas = film.background.copy()
        brand(canvas, film.fonts, 48, 42, 26)
        text(canvas, (W - 48, 52), "MORE PROGRAMS  ·  REAL CONSOLE RECORDINGS", film.fonts("mono", 20), MUTED, 1, "rm")
        width, height, gap = 776, 485, 20
        left, top = (W - 2 * width - gap) / 2, 88
        for index, clip in enumerate(group):
            x = left + index % 2 * (width + gap)
            y = top + index // 2 * (height + gap)
            appear = ease_out((t - index * .08) / .35)
            rect = (x, y + 20 * (1 - appear), width, height)
            local = max(0.0, t - .1)
            epoch = clip.remap.source(local)
            image = clip.reader.at(clip.case.offset(min(epoch, clip.case.result + .15)))
            crop = camera_crop(roi_state(clip.roi))
            scale = image.width / VM_W
            place(canvas, image, rect, tuple(value * scale for value in crop), radius=14, alpha=appear)
            box(canvas, rect, 14, outline=EDGE, alpha=appear)
            film.screen_pointer(canvas, clip.case, clip.clicks, local, rect, crop, appear)
            label = film.fonts("semibold", 26)
            caption = f"{clip.case.title}  ·  {clip.task}"
            width_text = ImageDraw.Draw(canvas).textlength(caption, font=label)
            box(canvas, (x + 16, rect[1] + height - 64, width_text + 32, 48), 10, fill=(6, 9, 16), alpha=.86 * appear)
            text(canvas, (x + 32, rect[1] + height - 40), caption, label, INK, appear, "lm")
            done = epoch >= clip.case.finish
            if done:
                age = local - clip.remap.output(clip.case.finish)
                pop = 1 + .3 * (1 - ease_out(age / .3))
                bw, bh = 220 * pop, 48 * pop
                box(canvas, (x + width - 16 - bw, rect[1] + 16, bw, bh), 10, fill=MINT, alpha=appear)
                text(canvas, (x + width - 16 - bw / 2, rect[1] + 16 + bh / 2), f"PASS · {len(clip.case.checks)} checks",
                     film.fonts("mono-bold", round(20 * pop)), (6, 30, 28), appear, "mm")
        return canvas

    def finale(self, t, length=5.5):
        film = self.film
        canvas = film.background.copy()
        tau = self.final_tau + t * self.final_rate
        appear = ease_out(t / .4)
        zoom = mix(1.06, 1.0, ease(t / length))
        film.wall(canvas, tau, (zoom, W / 2, H / 2), rate=self.final_rate)
        text(canvas, (48, 104), "Every run checked inside its own guest.", film.fonts("semibold", 64), INK, appear)
        brand(canvas, film.fonts, 48, 40, 30, appear)
        film.counters(canvas, tau, appear, rate=self.final_rate)
        return canvas

    def ending(self, t):
        canvas = self.finale(5.5)
        self.film.end_card(canvas, t)
        return canvas


def build_features(film, specs, ffmpeg):
    features = []
    for spec in specs:
        case = film.by_id.get(spec["id"])
        if case is None:
            continue
        beats = [(case.stages.get(name, case.stages["stage-0"]) + delta, roi) for name, delta, roi in spec["beats"]]
        feature = Feature(case, spec["task"], beats, spec.get("finding", ""), spec["verified"](case), spec.get("duration", 7.0))
        if "from" in spec:
            name, delta = spec["from"]
            feature.begin = case.stages[name] + delta
        feature.pauses = [(case.stages[name] + delta, length) for name, delta, length in spec.get("pauses", [])]
        feature.fixed_stage = spec.get("fixed", "stage-2" if spec.get("finding") else "stage-3")
        feature.prepare(ffmpeg)
        features.append(feature)
    return features


def build_montage(film, specs, ffmpeg):
    groups = []
    for group in specs:
        clips = []
        for case_id, task, roi, start in group:
            case = film.by_id.get(case_id)
            if case is None:
                continue
            clip = Feature(case, task, [(case.stages["stage-0"], None)], duration=4.0, hold=.6)
            clip.roi = roi
            events = [case.stages[name] for name in ("stage-1", "stage-2", "stage-3")]
            clip.remap = Remap(case.stages[start[0]] + start[1], case.finish + .2, events, 3.5, cap=8.0)
            clip.clicks = [(clip.remap.output(row["time"]), row["x"], row["y"]) for row in case.inputs
                           if row["device"] == "mouse"]
            clip.reader = Reader(ffmpeg, case.video, (960, 600))
            clips.append(clip)
        if clips:
            groups.append(clips)
    return groups


def check_value(case, prefix, key="observed"):
    for row in case.checks:
        if row["name"].startswith(prefix):
            return row.get(key)
    return None


FEATURES = [
    {"id": "02", "task": "Release gate recalculation", "from": ("stage-0", .05),
     "finding": "BLOCKED: 37 of 42 artifacts, 5 missing",
     "verified": lambda case: "Totals recalculated to 42/42 and the gate formula reads PASS",
     "pauses": [("stage-1", .1, 1.3)],
     "beats": [("stage-0", .05, None), ("stage-0", .3, (0, 125, 700, 350)), ("stage-3", .6, (0, 125, 700, 350))]},
    {"id": "03", "task": "Local recording contract",
     "verified": lambda case: "H.264 1280×720 with AAC audio, "
                              f"{check_value(case, 'Container duration', 'measured_seconds') or 0:.1f} s recorded",
     "beats": [("stage-0", -1.0, None), ("stage-1", -.8, (880, 500, 1280, 720)),
               ("stage-2", -.6, (440, 60, 1120, 450)), ("stage-3", -.9, (880, 500, 1280, 720)),
               ("stage-3", .9, None)]},
    {"id": "05", "task": "Startup budget fix", "from": ("stage-1", -2.5),
     "finding": "All 4 cold starts exceeded the 2,000 ms budget",
     "verified": lambda case: "Only startupTimeoutMs changed. All 4 starts pass at 3,500 ms",
     "pauses": [("stage-1", .1, 1.2)],
     "beats": [("stage-1", -2.5, None), ("stage-1", -.3, (0, 60, 760, 360)), ("stage-3", 1.0, (0, 60, 760, 360))]},
    {"id": "01", "task": "Release archive restore",
     "verified": lambda case: f"{sum(row['name'].endswith('SHA-256') for row in case.checks)} recovered files, "
                              "subfolders included, match their SHA-256 hashes",
     "beats": [("stage-0", -1.0, None), ("stage-1", -.6, (0, 95, 560, 250)),
               ("extract-dialog", .1, (388, 226, 892, 516)), ("stage-2", 1.0, None),
               ("stage-3-window", .3, (0, 95, 560, 250))]},
]

MONTAGE = [
    [("08", "schema migration", (0, 80, 660, 420), ("stage-0", -.5)),
     ("10", "seek to 12 s", (0, 140, 980, 760), ("stage-0", -.5)),
     ("09", "retry policy merge", (0, 50, 1000, 330), ("stage-0", -.5)),
     ("25", "missing file trace", None, ("stage-0", -.5))],
    [("32", "CPU spike and recovery", None, ("stage-0", -.5)),
     ("17", "clipped page export", (0, 140, 900, 720), ("stage-2", -1.0)),
     ("13", "slide order check", None, ("stage-0", -.5)),
     ("12", "signed PDF handoff", (140, 120, 900, 520), ("stage-0", -.5))],
]


def write_receipt(run_dir, cases, video, path):
    """Record what the video shows without lab-internal identifiers."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import run as product

    registry = product.load_cases()
    inventory = json.loads((run_dir / "program-inventory.json").read_text(encoding="utf-8"))
    fleet = json.loads((run_dir / "fleet.json").read_text(encoding="utf-8"))
    # Count every VM that ran in a wave, including attempts that failed and ran again later.
    wave_sizes = {wave["wave"]: len(wave.get("cases", {})) for wave in fleet["waves"]}
    waves = sorted({case.wave for case in cases})
    office = {"02": "calc", "12": "writer", "13": "impress", "14": "draw"}
    rows = []
    for case in cases:
        package = office.get(case.id) or registry[case.id][1].get("package")
        version = inventory["versions"].get(package, {}).get("version") if package != "windows" else inventory["windows"]
        case_json = json.loads((run_dir / f"case-{case.id}.json").read_text(encoding="utf-8"))
        meta = json.loads(case.video.with_suffix(".json").read_text(encoding="utf-8"))
        rows.append({
            "id": case.id, "program": case.title, "version": version, "scenario": case.scenario,
            "steps": case.steps, "wave": case.wave, "run_seconds": round(case.duration, 1),
            "checks": [{"name": row["name"], "passed": row["passed"]} for row in case.checks],
            "recording": {"fps": meta["fps"], "frames": meta["frames"], "seconds": meta["seconds"]},
            "stage_screenshot_sha256": case_json["frame_hashes"],
        })
    data = Path(video).read_bytes()
    receipt = {
        "schema_version": 2,
        "title": "OSLab introduction video: 32 Windows programs on disposable Proxmox VMs",
        "windows_version": inventory["windows"],
        "cases_passed": len(rows),
        "checks_passed": sum(len(row["checks"]) for row in rows),
        "capture": {"fps": 30, "max_vms_per_wave": max(wave_sizes[wave] for wave in waves), "waves": waves,
                    "alignment": "The wall shows every recording from its own workflow start."},
        "video": {"file": Path(video).name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "width": W, "height": H, "fps": FPS},
        "cases": rows,
    }
    Path(path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--fonts", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--open-tau", type=float, default=20.0,
                        help="Run time on the wall when the last agent has reached its VM")
    parser.add_argument("--preview", nargs="*", type=float, help="Render these seconds to a contact sheet")
    parser.add_argument("--crf", type=int, default=18)
    parser.add_argument("--receipt", type=Path,
                        help="Write the JSON record of the programs, checks and this encoded video next to it, then exit")
    args = parser.parse_args()
    cases = load_cases(args.run_dir)
    if args.receipt:
        write_receipt(args.run_dir, cases, args.receipt, args.receipt.with_name(f"{args.receipt.stem}-attestation.json"))
        return 0
    make_proxies(cases, args.ffmpeg, args.out / "proxies")
    film = Film(args, cases)
    story = Story(film, build_features(film, FEATURES, args.ffmpeg), build_montage(film, MONTAGE, args.ffmpeg), args)
    args.out.mkdir(parents=True, exist_ok=True)
    print(f"{len(cases)} runs, {story.duration:.1f} s", flush=True)
    if args.preview is not None:
        moments = args.preview or [0, 4, 6.7, 9, 12, 16, 22, 30, 37, 42, 47, 52, 57, story.duration - .5]
        sheet = Image.new("RGB", (960 * 2, 540 * math.ceil(len(moments) / 2)), "black")
        for index, moment in enumerate(moments):
            frame = story.frame(moment)
            frame.save(args.out / f"preview-{moment:05.1f}.png")
            sheet.paste(frame.resize((960, 540), Image.Resampling.LANCZOS), (index % 2 * 960, index // 2 * 540))
        sheet.save(args.out / "preview.png")
        return 0
    master = args.out / "oslab-intro-master.mp4"
    encoder = subprocess.Popen([
        args.ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(master)], stdin=subprocess.PIPE)
    total = round(story.duration * FPS)
    for index in range(total):
        encoder.stdin.write(story.frame(index / FPS).tobytes())
        if index % (FPS * 5) == 0:
            print(f"{index / FPS:5.1f} s", flush=True)
    encoder.stdin.close()
    if encoder.wait():
        raise RuntimeError("Video encoding failed")
    print(master, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
