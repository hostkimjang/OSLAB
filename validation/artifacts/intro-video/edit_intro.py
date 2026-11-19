"""Edit the OSLab introduction film from real captures.

The film walks through OSLab in six chapters between a cold open and an end card:

1. Scenario: the YAML file of a public demo scenario.
2. Run: the terminal output of a real `oslab run`, replayed with its recorded timing, next to
   the console recording of the disposable VM that the run created.
3. Evidence: the files that run wrote and its HTML report recorded in a browser.
4. Dashboard: a browser recording of the web dashboard launching a run on the lab.
5. AI agents: the console recording of a VM that an AI agent operated through the OSLab MCP
   server, next to the agent's tool calls.
6. Scale: the 32-VM Windows QA fleet edited by windows-product-qa/edit_video.py.

capture_cli.py, capture_dashboard.mjs and capture_agent.py record chapters 2 to 5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
from bisect import bisect_right
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "windows-product-qa"))

import edit_video as ev  # noqa: E402  The fleet editor provides the drawing helpers and the 32-VM wall.
from edit_video import (  # noqa: E402
    CORAL, DIM, EDGE, FPS, H, INK, MINT, MUTED, PANEL, W, Reader, Remap, box, brand, clamp, ease, ease_out, mix,
    place, text, wrap,
)

AMBER = (251, 191, 36)
SKY = (125, 211, 252)
VIOLET = (196, 181, 253)
TERMINAL = (8, 12, 20)
CHAPTERS = ["Scenario", "Run", "Evidence", "Dashboard", "AI agents", "Scale"]


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fit_rect(size, rect):
    """The largest rectangle with the image's aspect ratio centered in rect."""
    x, y, w, h = rect
    scale = min(w / size[0], h / size[1])
    return x + (w - size[0] * scale) / 2, y + (h - size[1] * scale) / 2, size[0] * scale, size[1] * scale


def dissolve(first, second, amount):
    return Image.blend(first, second, clamp(amount)) if amount > 0 else first


class Look:
    """Shared fonts, background and the elements that repeat across chapters."""

    def __init__(self, fonts):
        self.fonts = fonts
        self.background = ev.backdrop()
        self.measure = ImageDraw.Draw(Image.new("L", (1, 1)))

    def width(self, value, font):
        return self.measure.textlength(value, font=font)

    def nav(self, canvas, active, progress, alpha=1.0):
        """Chapter numbers at the top right, with the current chapter named and its progress underlined."""
        x = W - 48
        for index in reversed(range(len(CHAPTERS))):
            current = index == active
            label = f"{index + 1:02d}  {CHAPTERS[index].upper()}" if current else f"{index + 1:02d}"
            font = self.fonts("mono-bold" if current else "mono", 18)
            width = self.width(label, font)
            x -= width
            color = MINT if current else MUTED if index < active else DIM
            text(canvas, (x, 52), label, font, color, alpha, "lm")
            if current:
                box(canvas, (x, 66, width, 3), 1.5, fill=EDGE, alpha=alpha)
                box(canvas, (x, 66, max(3.0, width * clamp(progress)), 3), 1.5, fill=MINT, alpha=alpha)
            x -= 22

    def heading(self, canvas, t, number, title, body, x=48, y=112, width=560):
        """Chapter label, title and one sentence, sliding in at the start of a chapter."""
        fonts = self.fonts
        a = ease_out(t / .5)
        lift = 14 * (1 - a)
        text(canvas, (x, y + lift), f"{number:02d} · {CHAPTERS[number - 1].upper()}", fonts("mono", 18), MINT, a)
        y += 42
        for line in wrap(title, fonts("semibold", 52), width):
            text(canvas, (x, y + lift), line, fonts("semibold", 52), INK, a)
            y += 62
        y += 12
        b = ease_out((t - .15) / .5)
        for line in wrap(body, fonts("regular", 27), width):
            text(canvas, (x, y + 8 * (1 - b)), line, fonts("regular", 27), MUTED, b)
            y += 37
        return y

    def window(self, canvas, rect, title, badge="", alpha=1.0, fill=PANEL):
        """A window card with a title bar. Returns the content rectangle."""
        x, y, w, h = rect
        box(canvas, rect, 14, fill=fill, outline=EDGE, width=1, alpha=alpha)
        box(canvas, (x + 1, y + 40, w - 2, 1), 0, fill=EDGE, alpha=alpha)
        text(canvas, (x + 20, y + 21), title, self.fonts("mono", 18), MUTED, alpha, "lm")
        if badge:
            text(canvas, (x + w - 20, y + 21), badge, self.fonts("mono", 17), DIM, alpha, "rm")
        return x + 1, y + 41, w - 2, h - 42

    def footnote(self, canvas, value, alpha=1.0):
        text(canvas, (48, H - 22), value, self.fonts("regular", 22), DIM, alpha, "ls")

    def stamp(self, canvas, center, label, detail, age, color=MINT):
        """A result badge that pops in when a run finishes."""
        if age < 0:
            return
        pop = 1 + .25 * (1 - ease_out(age / .3))
        a = ease_out(age / .2)
        w = max(330, self.width(detail, self.fonts("regular", 22)) + 64) * pop
        h = 120 * pop
        x, y = center[0] - w / 2, center[1] - h / 2
        box(canvas, (x, y, w, h), 18, fill=(9, 34, 34) if color == MINT else (46, 14, 22), outline=color, width=3, alpha=a)
        text(canvas, (center[0], y + h * .4), label, self.fonts("mono-bold", round(48 * pop)), color, a, "mm")
        text(canvas, (center[0], y + h * .76), detail, self.fonts("regular", round(22 * pop)), INK, a, "mm")


# Cold open and end card -----------------------------------------------------------------------


class ColdOpen:
    """The 32-VM wall fills as agents arrive, then the title card."""

    duration = 7.6
    nav = False

    def __init__(self, look, fleet):
        self.look, self.fleet = look, fleet
        self.title_at = 4.7
        self.still = None

    def wall(self, t):
        film, story = self.fleet.film, self.fleet.story
        canvas = look_copy(self.look)
        tau = story.wall_tau(t)
        camera = story.open_camera(t)
        film.wall(canvas, max(tau, 0.0), camera, reveal=lambda index: (t - story.arrivals[index][1]) / .35)
        story.flights(canvas, t, camera, tau)
        return canvas

    def frame(self, t):
        fonts = self.look.fonts
        if t < self.title_at:
            canvas = self.wall(t)
            # The first frame doubles as the player's poster, so the brand and the title show from the start.
            brand(canvas, fonts, 48, 42, 26)
            text(canvas, (48, 104), "Every test gets a fresh Windows VM.", fonts("semibold", 68), INK)
            text(canvas, (50, 198), "OSLab clones a disposable VM, runs the test inside it, keeps the evidence "
                 "and removes the VM.", fonts("regular", 29), MUTED)
            text(canvas, (48, H - 84), f"32 recorded Windows VMs  ·  up to 8 at once  ·  starts aligned  ·  "
                 f"{ev.OPEN_RATE:g}× replay", fonts("mono", 24), MINT, ease_out((t - 1.2) / .5))
            self.look.footnote(canvas, "Console recordings from chapter 6. The cursor flights are animated. Once a tile "
                               "opens, its cursor follows the agent's recorded MCP clicks.")
            return canvas
        if self.still is None:
            frozen = self.wall(self.title_at)
            still = frozen.filter(ImageFilter.GaussianBlur(16))
            still.paste(Image.new("RGB", (W, H), (6, 9, 15)), (0, 0), Image.new("L", (W, H), 196))
            self.still = frozen, still
        frozen, still = self.still
        local = t - self.title_at
        canvas = dissolve(frozen, still, ease(local / .6))
        a = ease_out((local - .25) / .5)
        brand(canvas, fonts, W / 2 - 300, 380, 118, a)
        b = ease_out((local - .5) / .5)
        text(canvas, (W / 2, 590), "Scenario-based OS integration testing on disposable VMs", fonts("regular", 44), INK, b, "mm")
        c = ease_out((local - .8) / .5)
        text(canvas, (W / 2, 668), "Windows on Proxmox  ·  CLI and web dashboard  ·  MCP for Codex and Claude",
             fonts("mono", 24), MINT, c, "mm")
        return canvas


def look_copy(look):
    return look.background.copy()


class EndCard:
    duration = 6.5
    nav = False

    def __init__(self, look, fleet):
        self.look, self.fleet = look, fleet
        self.base = None

    def frame(self, t):
        fonts = self.look.fonts
        if self.base is None:
            self.base = self.fleet.story.diagram_background()
        canvas = self.base.copy()
        a = ease_out(t / .5)
        brand(canvas, fonts, W / 2 - 250, 250, 100, a)
        text(canvas, (W / 2, 432), "Disposable Windows VMs for real-world QA", fonts("regular", 46), INK, a, "mm")
        rows = [("Scenario YAML", "a fresh VM, the build, the checks"), ("Evidence", "JSON, JUnit and HTML for every run"),
                ("Dashboard", "launch runs and review results"), ("MCP", "Codex and Claude operate the VM screen")]
        for index, (name, detail) in enumerate(rows):
            b = ease_out((t - .35 - index * .12) / .4)
            y = 540 + index * 62
            text(canvas, (W / 2 - 40, y), name, fonts("mono-bold", 30), MINT, b, "rm")
            text(canvas, (W / 2 - 10, y), detail, fonts("regular", 30), INK, b, "lm")
        c = ease_out((t - 1.0) / .5)
        text(canvas, (W / 2, 880), "github.com/hostkimjang/OSLAB", fonts("semibold", 46), INK, c, "mm")
        return canvas


# 1. Scenario -----------------------------------------------------------------------------------

SECTIONS = [
    (("provider", "isolation"), "Clone a fresh VM from a Windows template"),
    (("guest",), "Reach the guest through QEMU Guest Agent"),
    (("artifact",), "Upload the build and run its command"),
    (("outputs",), "Collect the result file"),
    (("assertions",), "Check the exit code and the output"),
    (("reports", "cleanup"), "Keep the reports and destroy the VM"),
]


def yaml_tokens(line):
    """Split a YAML line into colored pieces for the editor panel."""
    indent = len(line) - len(line.lstrip(" "))
    body = line[indent:]
    pieces = [(" " * indent, INK)]
    if body.startswith("- "):
        pieces.append(("- ", DIM))
        body = body[2:]
    match = re.match(r"([\w.-]+)(:)(.*)$", body)
    if match:
        pieces += [(match[1], SKY), (":", DIM)]
        body = match[3]
    value = body.strip()
    if value.startswith(("'", '"')):
        color = AMBER
    elif re.fullmatch(r"-?\d+(\.\d+)?|true|false", value):
        color = VIOLET
    else:
        color = INK
    pieces.append((body, color))
    return pieces


class ScenarioChapter:
    number = 1
    duration = 12.0
    nav = True

    def __init__(self, look, path, label):
        self.look = look
        self.label = label
        self.lines = Path(path).read_text(encoding="utf-8").splitlines()
        tops = [(index, line.split(":")[0]) for index, line in enumerate(self.lines) if line and not line[0].isspace()]
        spans = {key: (start, end) for (start, key), (end, _) in zip(tops, tops[1:] + [(len(self.lines), "")])}
        self.bands = [(min(spans[key][0] for key in keys), max(spans[key][1] for key in keys), label)
                      for keys, label in SECTIONS]
        # The whole file shows first. Then the panel zooms in and steps through the sections.
        self.first_band, self.band_length, self.zoom_length = 1.8, 1.6, .5
        self.rect = (628, 104, 1244, 930)
        self.small, self.large = 16, 24

    def band_at(self, t):
        return clamp(int((t - self.first_band) // self.band_length), 0, len(self.bands) - 1)

    def band_span(self, t):
        """First and last line of the highlighted section, gliding over from the previous section."""
        active = self.band_at(t)
        target, previous = self.bands[active], self.bands[max(active - 1, 0)]
        moved = ease((t - self.first_band - active * self.band_length) / .35) if active else 1.0
        return mix(previous[0], target[0], moved), mix(previous[1], target[1], moved)

    def scroll(self, t):
        """The first visible line of the zoomed view, which keeps the highlighted section in the middle."""
        top, bottom = self.band_span(t)
        visible = (self.rect[3] - 42) / (self.large * 1.42) - 1
        return clamp((top + bottom) / 2 - visible / 2, 0, max(0.0, len(self.lines) - visible))

    def code(self, t, size, scroll):
        """The panel content with the YAML at one font size, scrolled down by scroll lines.

        Every distance scales with the font size, so the small view enlarged by large / small lines up with
        the large view and the two can dissolve into each other during the zoom."""
        look = self.look
        width, height = self.rect[2] - 2, self.rect[3] - 42
        view = Image.new("RGB", (width, height), TERMINAL)
        font = look.fonts("mono", size)
        step, x0 = size * 1.42, size * 3.4
        y0 = size * .875 - scroll * step
        highlighting = t >= self.first_band
        if highlighting:
            top, bottom = self.band_span(t)
            band = (8, y0 + top * step - size * .2, width - 16, (bottom - top) * step + size * .25)
            box(view, band, 8, fill=(18, 52, 56), alpha=.9 * ease_out((t - self.first_band) / .3))
            box(view, (band[0], band[1], 4, band[3]), 2, fill=MINT)
        active = self.bands[self.band_at(t)]
        for index, line in enumerate(self.lines):
            yy = y0 + index * step
            reveal = ease_out((t - .5 - index * .02) / .15)
            if reveal <= .01 or not -step < yy < height:
                continue
            inside = active[0] <= index < active[1]
            alpha = reveal * (1.0 if inside or not highlighting else .42)
            text(view, (x0 - size * 1.1, yy), str(index + 1), font, DIM, alpha * .8, "ra")
            x = x0
            for piece, color in yaml_tokens(line):
                if piece:
                    text(view, (x, yy), piece, font, color, alpha)
                    x += look.width(piece, font)
        return view

    def panel(self, t):
        """The whole file in small type, then a zoom into the highlighted section in large type."""
        zoom = ease((t - self.first_band) / self.zoom_length)
        if zoom <= 0:
            return self.code(t, self.small, 0.0)
        large = self.code(t, self.large, self.scroll(t))
        if zoom >= 1:
            return large
        # Enlarge the small view toward the large layout, then dissolve into the sharp large text.
        factor = self.large / self.small
        scale = mix(1.0, factor, zoom)
        shift = zoom * self.scroll(t) * self.large * 1.42
        small = self.code(t, self.small, 0.0)
        enlarged = small.transform(small.size, Image.Transform.AFFINE, (1 / scale, 0, 0, 0, 1 / scale, shift / scale),
                                   resample=Image.Resampling.BICUBIC, fillcolor=TERMINAL)
        return Image.blend(enlarged, large, clamp((zoom - .45) / .55))

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        y = look.heading(canvas, t, 1, "Describe the test once.",
                         "A scenario file names the Windows template, the build and its command, the result "
                         "to collect and the checks to pass.", width=520)
        highlighting = t >= self.first_band
        active = self.band_at(t)
        y += 30
        for index, (_, _, label) in enumerate(self.bands):
            a = ease_out((t - 1.0 - index * .08) / .4)
            done = highlighting and index < active
            current = highlighting and index == active
            color = INK if current else MUTED if done else DIM
            box(canvas, (48, y + 6, 24, 24), 12, fill=MINT if done or current else None,
                outline=MINT if done or current else DIM, width=2, alpha=a)
            if done:
                ImageDraw.Draw(canvas).line((54, y + 18, 59, y + 23, 67, y + 13), fill=(6, 30, 28), width=3)
            for line in wrap(label, fonts("medium", 26), 500):
                text(canvas, (88, y + 2), line, fonts("medium", 26), color, a)
                y += 34
            y += 16
        a = ease_out((t - .2) / .5)
        content = look.window(canvas, self.rect, self.label, "YAML", a, fill=TERMINAL)
        place(canvas, self.panel(t), content, radius=13, alpha=a)
        look.footnote(canvas, f"{self.label} from this repository. The runs in the next chapters use a local "
                      "copy with the lab's template and VMID range.")
        return canvas


# 2. Run ----------------------------------------------------------------------------------------

STEPS = [
    ("Clone", "vm.clone.start", "vm.clone.done"),
    ("Boot", "vm.start.start", "vm.boot.done"),
    ("Guest agent", "guest.ready.wait", "guest.ready.done"),
    ("Preflight", "preflight.start", "preflight.done"),
    ("Upload", "artifact.prepare.start", "artifact.upload.done"),
    ("Run", "product.command.start", "product.command.done"),
    ("Assert", "output.collect.start", "assertions.done"),
    ("Destroy", "vm.stop.start", "vm.destroy.done"),
]
STATUS_COLORS = {"[OK]": MINT, "[..]": AMBER, "[!!]": CORAL}


class Progress:
    """The lifecycle events a run wrote to logs/progress.jsonl."""

    def __init__(self, path):
        self.events = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        self.first = {}
        for event in self.events:
            event["epoch"] = datetime.fromisoformat(event["timestamp"]).timestamp()
            self.first.setdefault(event["phase"], event)

    def at(self, phase):
        return self.first[phase]["epoch"]


def aliased(value, aliases):
    for row in aliases:
        value = value.replace(row["find"], row["replace"])
    return value


def terminal_pieces(line):
    """Color a line of oslab output: time, status, phase and message."""
    if line.startswith(" "):
        return [(line, DIM)]
    pieces = []
    match = re.match(r"(\d{4}-\d\d-\d\dT\S+)( .*)$", line)
    if match:
        pieces.append((match[1], DIM))
        line = match[2]
    for token, color in STATUS_COLORS.items():
        if line.strip().startswith(token):
            head, _, line = line.partition(token)
            pieces += [(head, INK), (token, color)]
            break
    match = re.match(r"(\s*[\w.]+)( - )(.*)$", line)
    if match:
        return pieces + [(match[1], INK), (match[2], DIM), (match[3], MUTED)]
    return pieces + [(line, INK)]


def wrap_pieces(pieces, limit):
    """Break colored pieces into terminal rows of at most limit characters."""
    rows, row, used = [], [], 0
    for value, color in pieces:
        while value:
            room = limit - used
            part, value = value[:room], value[room:]
            row.append((part, color))
            used += len(part)
            if used >= limit:
                rows.append(row)
                row, used = [], 0
    if row or not rows:
        rows.append(row)
    return rows


class Clip:
    """A recording with the epoch of its first frame, read in time order."""

    def __init__(self, ffmpeg, video, meta):
        meta = load_json(meta)
        seconds = meta.get("seconds")
        if not isinstance(seconds, (int, float)) or not seconds > 0:
            raise ValueError(f"{video}: the capture metadata needs the recording length in seconds")
        if not Path(video).is_file() or not Path(video).stat().st_size:
            raise ValueError(f"{video} is missing or empty")
        self.meta = meta
        self.t0 = meta["t0"]
        self.size = (meta.get("width", 1280), meta.get("height", 800))
        self.end = self.t0 + seconds
        self.reader = Reader(ffmpeg, video, self.size)

    def at(self, epoch):
        return self.reader.at(clamp(epoch - self.t0, 0, max(self.end - self.t0 - 1 / self.reader.fps, 0)))


class RunChapter:
    number = 2
    duration = 25.0
    nav = True
    terminal_rect = (48, 206, 880, 830)
    row_height = 27

    def __init__(self, look, folder, ffmpeg):
        self.look = look
        self.terminal = load_json(folder / "terminal.json")
        self.aliases = load_json(folder / "aliases.json")
        self.progress = Progress(folder / "progress.jsonl")
        self.steps = [step for step in STEPS if step[1] in self.progress.first and step[2] in self.progress.first]
        run = load_json(folder / "run.json")
        details = run.get("details", {})
        assertions = details.get("assertions", {})
        # The badge reports what the run recorded, so a failed run can never show PASS.
        self.passed = run.get("status") == "passed" and assertions.get("failed") == 0
        verdict = f"{assertions.get('total', 0)} assertions passed" if self.passed else f"status {run.get('status')}"
        destroyed = details.get("vm", {}).get("destroyed")
        self.verdict = verdict + ("  ·  VM destroyed" if destroyed else "")
        self.console = Clip(ffmpeg, folder / "console.mkv", folder / "console.json")
        self.clips = [self.console]
        self.typing, self.hold = 2.2, 2.6
        lines = sorted(self.terminal["lines"], key=lambda row: row["t"])
        done = self.progress.at("run.done")
        events = [self.progress.at(done) for _, _, done in self.steps] + [self.progress.at("run.done")]
        # Play on until the last line the CLI printed, which can come after run.done.
        self.remap = Remap(self.terminal["started"], max(done + .4, lines[-1]["t"] + .2), events,
                           self.duration - self.typing - self.hold, before=.6, after=.9, cap=6.0)
        self.command = aliased(self.terminal["command"], self.aliases)
        self.font = look.fonts("mono", 20)
        self.limit = int((self.terminal_rect[2] - 42) / look.width("M", self.font))
        # Wrap the recorded output once. Each frame shows the rows printed by its source time.
        self.rows = []
        for row in lines:
            for piece_row in wrap_pieces(terminal_pieces(aliased(row["text"].rstrip(), self.aliases)), self.limit):
                self.rows.append((row["t"], piece_row))
        self.row_times = [moment for moment, _ in self.rows]

    def epoch(self, t):
        return self.remap.source(t - self.typing) if t >= self.typing else self.terminal["started"]

    def draw_terminal(self, canvas, t, a):
        look, font = self.look, self.font
        content = look.window(canvas, self.terminal_rect, "Windows PowerShell", "oslab run", a, fill=TERMINAL)
        x, y, w, h = content
        visible = int((h - 30) / self.row_height)
        rows = []
        typed = self.command[:int(len(self.command) * clamp(t / (self.typing - .3)))]
        for index, part in enumerate(typed.split("\n")):
            rows += wrap_pieces([("PS> " if index == 0 else "", MINT), (part, INK)], self.limit)
        if t >= self.typing:
            printed = bisect_right(self.row_times, self.epoch(t))
            rows += [row for _, row in self.rows[max(0, printed - visible):printed]]
        for index, row in enumerate(rows[-visible:]):
            xx = x + 20
            for value, color in row:
                text(canvas, (xx, y + 16 + index * self.row_height), value, font, color, a)
                xx += look.width(value, font)

    def draw_console(self, canvas, epoch, rect, a):
        look = self.look
        content = look.window(canvas, rect, "Disposable VM  ·  Windows 11 console", "Proxmox console", a, fill=(0, 0, 0))
        clone, destroyed = self.progress.at("vm.clone.done"), self.progress.at("vm.destroy.done")
        # Show the recording until the VM powered off. A recording that ended earlier holds its last frame.
        powered_off = self.console.meta.get("powered_off", destroyed)
        if self.console.t0 <= epoch < min(powered_off, destroyed):
            place(canvas, self.console.at(epoch), fit_rect(self.console.size, content), alpha=a)
            return
        if epoch < clone:
            message = "Cloning a VM from the template…"
        elif epoch < self.console.t0:
            message = "Starting the VM…"
        elif epoch < destroyed:
            message = "VM stopped  ·  destroying the clone…"
        elif self.finished(epoch):
            return
        else:
            message = "VM destroyed"
        text(canvas, (content[0] + content[2] / 2, content[1] + content[3] / 2), message,
             look.fonts("mono", 24), MUTED, a, "mm")

    def finished(self, epoch):
        return epoch >= self.progress.at("run.done")

    def draw_lifecycle(self, canvas, t, epoch, rect, a):
        fonts = self.look.fonts
        x, y, w, h = rect
        box(canvas, rect, 14, fill=PANEL, outline=EDGE, alpha=a)
        started = self.progress.at("run.created")
        elapsed = max(0.0, min(epoch, self.progress.at("run.done")) - started) if t >= self.typing else 0.0
        text(canvas, (x + 22, y + 26), "LIFECYCLE  ·  REAL DURATIONS", fonts("mono", 17), DIM, a, "lm")
        speed = self.remap.speed(t - self.typing) if self.typing <= t < self.duration - self.hold else 0.0
        label = f"T+{int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}   " + ev.speed_label(speed)
        text(canvas, (x + w - 22, y + 26), label, fonts("mono", 17), MUTED, a, "rm")
        track_y = y + 84
        gap = (w - 80) / (len(self.steps) - 1)
        box(canvas, (x + 40, track_y - 2, w - 80, 4), 2, fill=EDGE, alpha=a)
        for index, (name, begin, done) in enumerate(self.steps):
            cx = x + 40 + index * gap
            first, last = self.progress.at(begin), self.progress.at(done)
            finished, running = epoch >= last, first <= epoch < last
            if finished and index:
                box(canvas, (cx - gap, track_y - 2, gap, 4), 2, fill=MINT, alpha=a)
            radius = 11 if running else 9
            pulse = .6 + .4 * math.sin(t * 7) if running else 1.0
            box(canvas, (cx - radius, track_y - radius, 2 * radius, 2 * radius), radius,
                fill=MINT if finished else AMBER if running else PANEL, outline=MINT if finished else AMBER if running else DIM,
                width=2, alpha=a * pulse)
            color = INK if finished or running else DIM
            text(canvas, (cx, track_y + 34), name, fonts("medium", 19), color, a, "mm")
            if finished:
                text(canvas, (cx, track_y + 62), f"{last - first:.1f} s", fonts("mono", 17), MINT, a, "mm")

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        a = ease_out(t / .5)
        text(canvas, (48, 104), "02 · RUN", fonts("mono", 18), MINT, a)
        text(canvas, (48, 134), "Run it on a fresh VM.", fonts("semibold", 46), INK, a)
        text(canvas, (640, 150), "One command clones the VM, runs the build, checks it and destroys the VM.",
             fonts("regular", 26), MUTED, ease_out((t - .2) / .5), "lm")
        epoch = self.epoch(t)
        self.draw_terminal(canvas, t, a)
        self.draw_console(canvas, epoch if t >= self.typing else 0.0, (960, 206, 912, 612), a)
        self.draw_lifecycle(canvas, t, epoch, (960, 836, 912, 200), a)
        done = self.progress.at("run.done")
        if self.finished(epoch):
            age = t - self.typing - self.remap.output(done)
            look.stamp(canvas, (1416, 512), "PASS" if self.passed else "FAIL", self.verdict, age,
                       MINT if self.passed else CORAL)
        look.footnote(canvas, "Recorded CLI output and VM console of one run, aligned by timestamp. Command typing is "
                      "animated, waits are shortened, and local names and paths are replaced.", a)
        return canvas


# 3. Evidence ------------------------------------------------------------------------------------

FILE_NOTES = {
    "run.json": "status, timings and file index",
    "logs/progress.jsonl": "every lifecycle step",
    "raw/actual-output.json": "what the build wrote",
    "normalized/command-result.json": "what the assertions read",
    "reports/result.json": "for tools",
    "reports/result.junit.xml": "for CI",
    "reports/result.html": "for people",
}


class EvidenceChapter:
    number = 3
    duration = 13.5
    nav = True

    def __init__(self, look, folder, ffmpeg):
        self.look = look
        # One row per file, with a row for each folder before its first file.
        self.rows = []
        folders = set()
        for line in (folder / "runtree.txt").read_text(encoding="utf-8").splitlines():
            parts = line.rsplit(None, 1)
            if len(parts) != 2 or not parts[1].isdigit():
                continue
            path = parts[0].replace("\\", "/").lstrip("/")
            names = path.split("/")
            for depth in range(1, len(names)):
                parent = "/".join(names[:depth])
                if parent not in folders:
                    folders.add(parent)
                    self.rows.append((parent, names[depth - 1] + "/", depth - 1))
            self.rows.append((path, names[-1], len(names) - 1))
        self.report = Clip(ffmpeg, folder / "report.mkv", folder / "report.json")
        # The report page keeps its content in a centered column. Crop the margins to enlarge the text.
        width = self.report.size[0]
        self.crop = (width * .15, 0, width * .7, width * .7 / 1.6)
        self.clips = [self.report]
        self.assertions = load_json(folder / "reports" / "result.json")["assertions"]["results"]
        self.run_id = load_json(folder / "run.json")["runId"]

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        y = look.heading(canvas, t, 3, "Every run leaves evidence.",
                         "Logs, raw and normalized output, and JSON, JUnit and HTML reports land in one folder.")
        y += 26
        text(canvas, (48, y), f"runs/{self.run_id}/", fonts("mono-bold", 20), INK, ease_out((t - .5) / .4))
        y += 40
        for index, (path, name, depth) in enumerate(self.rows):
            a = ease_out((t - .7 - index * .1) / .35)
            color = INK if path in FILE_NOTES else DIM if name.endswith("/") else MUTED
            text(canvas, (68 + depth * 28, y), name, fonts("mono", 21), color, a)
            note = FILE_NOTES.get(path)
            if note:
                text(canvas, (652, y), note, fonts("regular", 21), MINT, a, "ra")
            y += 33
        rect = (700, 104, 1172, 772)
        a = ease_out((t - .3) / .5)
        content = look.window(canvas, rect, "reports/result.html", "HTML report", a, fill=(255, 255, 255))
        start = self.report.t0
        place(canvas, self.report.at(start + max(0.0, t - 1.0)), fit_rect(self.crop[2:], content), self.crop, alpha=a)
        panel = (700, 894, 1172, 142)
        box(canvas, panel, 14, fill=PANEL, outline=EDGE, alpha=a)
        text(canvas, (724, 922), "ASSERTIONS  ·  reports/result.json", fonts("mono", 17), DIM, a, "lm")
        for index, row in enumerate(self.assertions[:3]):
            b = ease_out((t - 2.0 - index * .2) / .4)
            yy = 960 + index * 30
            passed = row["passed"]
            text(canvas, (724, yy), "PASS" if passed else "FAIL", fonts("mono-bold", 20), MINT if passed else CORAL, b, "lm")
            text(canvas, (800, yy), str(row.get("id", row.get("name", ""))), fonts("mono", 20), INK, b, "lm")
            text(canvas, (1848, yy), row.get("message", ""), fonts("regular", 20), MUTED, b, "rm")
        look.footnote(canvas, "Files written by the run in chapter 2. The HTML report was recorded in a browser.", a)
        return canvas


# 4. Dashboard -----------------------------------------------------------------------------------

DASHBOARD_STEPS = [
    ("Pick a scenario and a build", "launch"),
    ("Launch it on a disposable VM", "first_log"),
    ("Watch the run live", "finished"),
    ("Review the results and evidence", "results"),
]


def pointer_path(actions):
    """Recorded pointer positions as (epoch, x, y), in time order."""
    return [(row["t"], row["x"], row["y"]) for row in actions if row.get("x") is not None and row.get("y") is not None]


def pointer_at(path, epoch, glide=.35):
    """Pointer position at epoch, easing from each recorded position to the next."""
    times = [row[0] for row in path]
    index = max(0, min(len(path) - 1, bisect_right(times, epoch) - 1))
    _, x, y = path[index]
    if index + 1 < len(path):
        moment, nx, ny = path[index + 1]
        span = min(glide, moment - path[index][0])
        if span > 0 and epoch > moment - span:
            amount = ease((epoch - moment + span) / span)
            x, y = mix(x, nx, amount), mix(y, ny, amount)
    return x, y


class DashboardChapter:
    number = 4
    duration = 26.0
    nav = True

    def __init__(self, look, folder, ffmpeg):
        self.look = look
        self.clip = Clip(ffmpeg, folder / "dashboard.mkv", folder / "dashboard.json")
        self.clips = [self.clip]
        self.actions = load_json(folder / "actions.json")
        self.moments = load_json(folder / "chapters.json")
        self.path = pointer_path(self.actions)
        if not self.path:
            raise ValueError(f"{folder / 'actions.json'} has no pointer positions")
        if abs(self.clip.size[0] / self.clip.size[1] - ev.VM_W / ev.VM_H) > .01:
            raise ValueError(f"The dashboard recording must have the 16:10 shape of the console, not {self.clip.size}")
        self.clicks = [(row["t"], row["x"], row["y"]) for row in self.actions if row["type"] == "click"]
        events = [row["t"] for row in self.actions if row["type"] in ("click", "type")] + list(self.moments.values())
        self.hold = 1.2
        self.remap = Remap(self.clip.t0 + .3, self.clip.end - .1, events, self.duration - self.hold, cap=6.0)
        self.camera = ev.Camera(self.camera_keys(folder), move=.6)
        self.cursor = ev.cursor_sprite((248, 250, 252), 30)

    def camera_keys(self, folder):
        """Zoom into the Run click, the live console while the run plays and the HTML report.

        The dashboard frame has the 16:10 shape of a 1280x800 console, so the fleet editor's camera applies.
        boxes.json gives the live console and the report preview in recording pixels."""
        self.scale = self.clip.size[0] / ev.VM_W
        boxes = load_json(folder / "boxes.json") if (folder / "boxes.json").exists() else {}
        out = self.remap.output
        keys = [(0.0, ev.roi_state(None))]
        launch = self.moments["launch"]
        x, y = (value / self.scale for value in pointer_at(self.path, launch))
        keys.append((out(launch) - .2, ev.roi_state((x - 420, y - 260, x + 420, y + 260))))
        if "live_console" in boxes:
            live = [value / self.scale for value in boxes["live_console"]["box"]]
            keys += [(out(self.moments["first_log"]) + .3, ev.roi_state(live)),
                     (out(self.moments["finished"]) + .6, ev.roi_state(None))]
        else:
            keys.append((out(launch) + 1.6, ev.roi_state(None)))
        if "report" in boxes:
            report = [value / self.scale for value in boxes["report"]["box"]]
            keys.append((out(self.moments["report"]) + .4, ev.roi_state(report)))
        return sorted(keys)

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        a = ease_out(t / .5)
        epoch = self.remap.source(t)
        rect = (48, 104, 1376, 900)
        content = look.window(canvas, rect, "OSLab dashboard  ·  localhost", "browser recording", a, fill=(12, 16, 26))
        state = self.camera.state(t)
        crop = tuple(value * self.scale for value in ev.camera_crop(state))
        place(canvas, self.clip.at(epoch), content, crop, alpha=a)

        def screen(px, py):
            return content[0] + (px - crop[0]) * content[2] / crop[2], content[1] + (py - crop[1]) * content[3] / crop[3]

        # The ring stays where the click landed while the pointer moves on.
        clicked = [click for click in self.clicks if click[0] <= epoch]
        if clicked:
            moment, cx, cy = clicked[-1]
            _ripple(look, canvas, screen(cx, cy), t - self.remap.output(moment))
        sx, sy = screen(*pointer_at(self.path, epoch))
        sprite, tip = self.cursor
        if content[0] <= sx <= content[0] + content[2] and content[1] <= sy <= content[1] + content[3]:
            canvas.paste(sprite, (round(sx) - tip, round(sy) - tip), sprite)
        y = look.heading(canvas, t, 4, "Or click Run in the dashboard.",
                         "The local web dashboard launches the same runs and keeps every result.", x=1468, width=404)
        y += 30
        for index, (label, key) in enumerate(DASHBOARD_STEPS):
            done = key in self.moments and epoch >= self.moments[key]
            b = ease_out((t - .8 - index * .1) / .4)
            box(canvas, (1468, y + 4, 24, 24), 12, fill=MINT if done else None, outline=MINT if done else DIM, width=2, alpha=b)
            if done:
                ImageDraw.Draw(canvas).line((1474, y + 16, 1479, 21 + y, 1487, y + 11), fill=(6, 30, 28), width=3)
            for line in wrap(label, fonts("medium", 24), 360):
                text(canvas, (1506, y + 2), line, fonts("medium", 24), INK if done else MUTED, b)
                y += 32
            y += 14
        speed = self.remap.speed(t)
        text(canvas, (1424, 84), "REAL BROWSER RECORDING  ·  " + ev.speed_label(speed), fonts("mono", 16), MUTED, a, "rs")
        look.footnote(canvas, "Browser recording of the dashboard, driven by a Playwright script while it ran a scenario "
                      "on the lab. Lab names are replaced, and waits play faster.", a)
        return canvas


def _ripple(look, canvas, point, age, color=MINT, length=.6, reach=40):
    if not 0 <= age < length:
        return
    radius = mix(6, reach, ease_out(age / length))
    size = round(2 * reach + 16)
    ring = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    middle = size / 2
    ImageDraw.Draw(ring).ellipse((middle - radius, middle - radius, middle + radius, middle + radius),
                                 outline=(*color, round(255 * (1 - age / length))), width=4)
    canvas.paste(ring, (round(point[0] - middle), round(point[1] - middle)), ring)


# 5. AI agents -----------------------------------------------------------------------------------


def mark(canvas, xy, color, done, alpha):
    """A small check mark for finished steps, or a dot for running ones."""
    x, y = xy
    if not done:
        box(canvas, (x + 5, y + 5, 9, 9), 4.5, fill=color, alpha=alpha)
        return
    layer = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    ImageDraw.Draw(layer).line((2, 10, 7, 15, 17, 4), fill=(*color, round(255 * alpha)), width=3)
    canvas.paste(layer, (round(x), round(y)), layer)


def transcript_rows(calls, aliases):
    """Group the agent's MCP calls into transcript rows. Single printable keys become one typed text that
    grows as each key lands."""
    rows = []
    for call in calls:
        tool, args = call["tool"], call.get("args", {})
        keys = args.get("keys") or ([args["key"]] if "key" in args else [])
        # Shift with one character types that character.
        if len(keys) == 2 and keys[0].lower() == "shift" and len(keys[1]) == 1:
            keys = [keys[1].upper()]
        single = tool == "press_key" and len(keys) == 1 and len(keys[0]) == 1
        if single and rows and rows[-1]["typed"]:
            rows[-1]["characters"].append((call["end"], keys[0]))
            rows[-1]["end"] = call["end"]
            continue
        if single:
            rows.append({"tool": "type", "text": "", "typed": True, "start": call["start"], "end": call["end"],
                         "characters": [(call["end"], keys[0])]})
        elif tool == "press_key":
            label = keys[0] if len(keys) == 1 and keys[0].lower() == "space" else ev.key_label(keys)
            rows.append({"tool": "press_key", "text": label, "typed": False, "start": call["start"], "end": call["end"]})
        elif tool in ("click", "move_mouse"):
            rows.append({"tool": "click" if tool == "click" else "move", "text": f"{args.get('x')}, {args.get('y')}",
                         "typed": False, "start": call["start"], "end": call["end"]})
        else:
            rows.append({"tool": tool, "text": aliased(call.get("summary", ""), aliases), "typed": False,
                         "start": call["start"], "end": call["end"]})
    return rows


def row_text(row, epoch):
    """A transcript row's text at epoch. Typed text shows only the keys sent so far."""
    if not row["typed"]:
        return row["text"]
    return "".join(character for moment, character in row["characters"] if moment <= epoch)


class AgentChapter:
    number = 5
    duration = 32.0
    nav = True
    actions = ("press_key", "click", "move_mouse")

    def __init__(self, look, folder, ffmpeg):
        self.look = look
        session = load_json(folder / "calls.json")
        aliases = load_json(folder / "aliases.json") if (folder / "aliases.json").exists() else []
        self.agent, self.calls = session.get("agent", "Codex"), session["calls"]
        self.prompt = aliased(session["prompt"], aliases)
        self.checks = load_json(folder / "checks.json")
        # The verdict comes from the guest checks: every check must have passed and there must be at least one.
        self.passed = bool(self.checks) and all(row.get("passed") is True for row in self.checks)
        check_times = [row["t"] for row in self.checks if isinstance(row.get("t"), (int, float))]
        self.checked = max(check_times, default=self.calls[-1]["end"])
        self.clip = Clip(ffmpeg, folder / "console.mkv", folder / "console.json")
        self.clips = [self.clip]
        self.rows = transcript_rows(self.calls, aliases)
        self.path = [(call["end"], call["args"]["x"], call["args"]["y"]) for call in self.calls
                     if call["tool"] in ("click", "move_mouse")]
        self.clicks = [call["end"] for call in self.calls if call["tool"] == "click"]
        self.hold = 3.2
        start, end = self.calls[0]["start"] - 1.2, max(self.calls[-1]["end"] + .8, self.checked + .4)
        # Inputs play a few times faster than real time. The agent's screenshots and thinking pass quickly.
        events = [call["end"] for call in self.calls if call["tool"] in self.actions] + check_times
        self.remap = Remap(start, end, events, self.duration - self.hold - 1.0, slow=6.0, before=1.2, after=.4, cap=6.0)
        self.color = ev.agent_color(0)
        self.sprite = ev.cursor_sprite(self.color, 34)
        self.tag = ev.tag_sprite(self.agent, self.color, look.fonts("mono-bold", 20))

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        a = ease_out(t / .5)
        local = t - 1.0
        epoch = self.remap.source(max(local, 0.0))
        text(canvas, (48, 104), "05 · AI AGENTS", fonts("mono", 18), MINT, a)
        text(canvas, (48, 134), "Let an AI agent use the desktop.", fonts("semibold", 40), INK, a)
        panel = look.window(canvas, (48, 212, 640, 824), f"{self.agent}  ·  OSLab MCP", "", a, fill=TERMINAL)
        x, y, w, _ = panel
        lines = wrap(self.prompt, fonts("regular", 22), w - 64)
        bubble = (x + 18, y + 18, w - 36, 30 * len(lines) + 30)
        box(canvas, bubble, 12, fill=(24, 34, 52), alpha=a)
        for index, line in enumerate(lines):
            text(canvas, (x + 34, y + 33 + index * 30), line, fonts("regular", 22), INK, a)
        yy = bubble[1] + bubble[3] + 22
        shown = [row for row in self.rows if row["start"] <= epoch]
        room = int((panel[1] + panel[3] - yy - 12) / 38)
        for row in shown[-room:] if room > 0 else []:
            done = epoch >= row["end"]
            mark(canvas, (x + 22, yy + 3), MINT if done else AMBER, done, a)
            text(canvas, (x + 52, yy), row["tool"], fonts("mono-bold", 20), SKY, a)
            text(canvas, (x + 230, yy), ev.fit(row_text(row, epoch), fonts("mono", 20), w - 246), fonts("mono", 20), INK, a)
            yy += 38
        content = look.window(canvas, (720, 104, 1152, 788), "Windows 11 VM  ·  operated through the Proxmox console",
                              "", a, fill=(0, 0, 0))
        frame_rect = fit_rect(self.clip.size, content)
        place(canvas, self.clip.at(epoch), frame_rect, alpha=a)
        fx, fy, fw, fh = frame_rect
        if self.path and epoch >= self.path[0][0] - .6:
            px, py = pointer_at([(self.path[0][0] - .6, self.path[0][1], self.path[0][2])] + self.path, epoch)
            point = (fx + px * fw / self.clip.size[0], fy + py * fh / self.clip.size[1])
            last = max((moment for moment in self.clicks if moment <= epoch), default=None)
            if last is not None:
                _ripple(look, canvas, point, local - self.remap.output(last), self.color)
            sprite, tip = self.sprite
            canvas.paste(sprite, (round(point[0]) - tip, round(point[1]) - tip), sprite)
            canvas.paste(self.tag, (round(point[0]) + 16, round(point[1]) + 28), self.tag)
        checked = epoch >= self.checked
        verdict = MINT if self.passed else CORAL
        panel_rect = (720, 910, 1152, 126)
        box(canvas, panel_rect, 14, fill=PANEL, outline=verdict if checked else EDGE, width=2 if checked else 1, alpha=a)
        text(canvas, (744, 940), "GUEST CHECKS  ·  QEMU Guest Agent", fonts("mono", 17), DIM, a, "lm")
        if checked:
            status, color = ("PASS" if self.passed else "FAIL"), verdict
        elif epoch >= self.calls[-1]["end"]:
            status, color = "CHECKING THE GUEST", AMBER
        else:
            status, color = "WAITING FOR THE AGENT", MUTED
        text(canvas, (744, 990), status, fonts("mono-bold", 34), color, a, "lm")
        # Each check appears at the time the guest agent reported it.
        for index, row in enumerate(self.checks[:3]):
            moment = row.get("t", self.checked)
            if epoch < moment:
                continue
            b = ease_out((local - self.remap.output(moment) - index * .12) / .3)
            passed = row.get("passed") is True
            mark(canvas, (1220, 945 + index * 30), MINT if passed else CORAL, passed, b)
            text(canvas, (1250, 954 + index * 30), row["name"], fonts("regular", 21), INK, b, "lm")
        speed = self.remap.speed(local) if local >= 0 else 0.0
        text(canvas, (1872, 84), "REAL CONSOLE RECORDING  ·  " + ev.speed_label(speed), fonts("mono", 17), MUTED, a, "rs")
        look.footnote(canvas, f"Console recording of a VM that {self.agent} operated through the OSLab MCP server, with "
                      "waits shortened. The host mouse and keyboard stay free.", a)
        return canvas


# 6. Scale -----------------------------------------------------------------------------------------


def load_fleet(fleet_dir, fonts, ffmpeg, work):
    args = SimpleNamespace(fonts=fonts, ffmpeg=ffmpeg, open_tau=20.0)
    cases = ev.load_cases(fleet_dir)
    ev.make_proxies(cases, ffmpeg, work / "proxies")
    film = ev.Film(args, cases)
    story = ev.Story(film, ev.build_features(film, ev.FEATURES, ffmpeg), ev.build_montage(film, ev.MONTAGE, ffmpeg), args)
    return SimpleNamespace(film=film, story=story)


class ScaleChapter:
    """The 32-VM Windows QA wall, two zoomed fixes, how the agents reach the VMs, eight more programs and the
    finished wall."""

    number = 6
    nav = False
    finale_length, result_hold = 5.5, 2.0

    def __init__(self, look, fleet):
        self.look = look
        story, film = fleet.story, fleet.film
        self.story = story
        self.final = None
        # Calc and VS Code both show a finding, the fix and the guest check that proves it.
        calc, vscode = story.features[0], story.features[2]
        wall_from = ev.INTRO + .6
        self.shots = [
            (story.open_length - wall_from, lambda t: story.opening(wall_from + t), True),
            (1.35, story.push_in, True),
            (calc.duration, lambda t: film.feature_frame(calc, t), True),
            (.6, lambda t: story.slide(calc, vscode, t), True),
            (vscode.duration, lambda t: film.feature_frame(vscode, t), True),
            (.7, lambda t: story.pull_out(t, last=vscode), True),
            (6.6, story.how, True),
            (4.2, lambda t: story.quad(story.montage[0], t), False),
            (4.2, lambda t: story.quad(story.montage[1], t), False),
            (self.finale_length + self.result_hold, self.final_wall, True),
        ]
        self.dissolves = {7, 9}  # Into the first montage and into the finale, which share no camera move.
        self.duration = sum(length for length, _, _ in self.shots)

    def final_wall(self, t):
        """The wall finishing its time-lapse. The last frame holds so the final counts can be read."""
        if t < self.finale_length:
            return self.story.finale(t)
        if self.final is None:
            final = self.story.finale(self.finale_length)
            # Time stops here, so the time-lapse label under the clock gives way to a hold label.
            label = (W - 300, 964, W - 40, 998)
            final.paste(self.story.film.background.crop(label), label[:2])
            text(final, (W - 48, 970), "RESULT HELD", self.look.fonts("mono", 18), MINT, 1.0, "ra")
            self.final = final
        return self.final.copy()

    def frame(self, t):
        start = 0.0
        for index, (length, render, nav) in enumerate(self.shots):
            if t < start + length or index == len(self.shots) - 1:
                local = t - start
                canvas = render(min(local, length))
                if index in self.dissolves and local < .4:
                    previous_length, previous, _ = self.shots[index - 1]
                    canvas = dissolve(previous(previous_length), canvas, local / .4)
                if nav:
                    self.look.nav(canvas, self.number - 1, t / self.duration)
                return canvas
            start += length
        return self.shots[-1][1](self.shots[-1][0])


# The film ---------------------------------------------------------------------------------------


class Intro:
    overlap = .3  # Seconds in which consecutive chapters dissolve into each other.

    def __init__(self, look, chapters):
        self.look = look
        self.chapters = chapters
        self.starts = []
        total = 0.0
        for chapter in chapters:
            self.starts.append(total)
            total += chapter.duration - self.overlap
        self.duration = total + self.overlap

    def chapter_frame(self, index, t):
        chapter = self.chapters[index]
        local = clamp(t - self.starts[index], 0, chapter.duration)
        canvas = chapter.frame(local)
        if chapter.nav:
            brand(canvas, self.look.fonts, 48, 42, 26)
            self.look.nav(canvas, chapter.number - 1, local / chapter.duration)
        return canvas

    def frame(self, t):
        index = max(0, bisect_right(self.starts, t) - 1)
        canvas = self.chapter_frame(index, t)
        into = t - self.starts[index]
        if index and into < self.overlap:
            canvas = Image.blend(self.chapter_frame(index - 1, t), canvas, ease(into / self.overlap))
        return canvas


def render(film, path, ffmpeg, crf):
    encoder = subprocess.Popen([
        ffmpeg, "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
        "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(path)], stdin=subprocess.PIPE)
    try:
        total = round(film.duration * FPS)
        for index in range(total):
            encoder.stdin.write(film.frame(index / FPS).tobytes())
            if index % (FPS * 10) == 0:
                print(f"{index / FPS:6.1f} s", flush=True)
        encoder.stdin.close()
        if encoder.wait():
            raise RuntimeError("Video encoding failed")
    finally:
        if encoder.poll() is None:
            encoder.kill()
            encoder.wait()


def close_readers(fleet, chapters):
    """Stop the ffmpeg decoders behind every recording."""
    readers = list(fleet.film.tiles.values()) + [feature.reader for feature in fleet.story.features]
    readers += [clip.reader for group in fleet.story.montage for clip in group]
    readers += [clip.reader for chapter in chapters for clip in getattr(chapter, "clips", [])]
    for reader in readers:
        reader.close()


def recording(meta):
    fps = meta.get("fps", FPS)
    # Recordings assembled at a constant rate may leave out the frame count.
    return {"fps": fps, "frames": meta.get("frames") or round(meta["seconds"] * fps), "seconds": round(meta["seconds"], 3)}


def run_record(folder):
    """The run behind a capture folder, as its run.json reports it."""
    run = load_json(folder / "run.json")
    details = run.get("details", {})
    started, completed = (datetime.fromisoformat(run[key]).timestamp() for key in ("startedAt", "completedAt"))
    return {"run_id": run["runId"], "scenario": run["scenarioId"], "status": run["status"],
            "assertions": details.get("assertions"), "vm_destroyed": details.get("vm", {}).get("destroyed"),
            "run_seconds": round(completed - started, 1)}


def write_receipt(captures, fleet_dir, video, path):
    """Record the runs, the agent session and the recordings that the film shows, without VM IDs or lab host
    names."""
    cli, dashboard, agent = captures / "cli", captures / "dashboard", captures / "agent"
    progress = Progress(cli / "progress.jsonl")
    session = load_json(agent / "calls.json")
    calls_by_tool = {}
    for call in session["calls"]:
        calls_by_tool[call["tool"]] = calls_by_tool.get(call["tool"], 0) + 1
    cases = ev.load_cases(fleet_dir)
    data = Path(video).read_bytes()
    receipt = {
        "schema_version": 1,
        "title": "OSLab introduction film",
        "cli_run": {
            **run_record(cli),
            "steps": [{"name": name, "seconds": round(progress.at(done) - progress.at(begin), 1)}
                      for name, begin, done in STEPS],
            "console_recording": recording(load_json(cli / "console.json")),
            "report_recording": recording(load_json(cli / "report.json")),
        },
        "dashboard_run": {**run_record(dashboard), "browser_recording": recording(load_json(dashboard / "dashboard.json"))},
        "agent_session": {
            "client": session.get("agent"),
            "prompt": session["prompt"],
            "mcp_calls": len(session["calls"]),
            "calls_by_tool": calls_by_tool,
            "guest_checks": [{"name": row["name"], "passed": row["passed"]} for row in load_json(agent / "checks.json")],
            "console_recording": recording(load_json(agent / "console.json")),
        },
        "windows_fleet": {
            "programs": len(cases),
            "checks_passed": sum(row["passed"] is True for case in cases for row in case.checks),
            "record": "oslab-windows-product-qa-attestation.json",
        },
        "edits": [
            "Chapters 02 and 03 show one CLI run, chapter 04 a separate run that a Playwright script launched from the "
            "dashboard, and chapter 05 a separate Codex session. The opening and chapter 06 reuse the 32-VM Windows QA "
            "recordings.",
            "Waits play faster, and each recorded chapter shows its playback speed.",
            "The YAML and terminal panels are typeset from the scenario file and the recorded CLI output. Command "
            "typing is animated.",
            "Local host names, user folders and private variable names are replaced in the terminal text, the HTML "
            "report and the dashboard.",
            "The editor draws the cursors at the recorded pointer positions and interpolates the movement between them.",
            "The 32-VM wall aligns recordings made in waves of up to 8 at each run's start, and the finished wall "
            "is held for 2 seconds.",
        ],
        "video": {"file": Path(video).name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "width": W, "height": H, "fps": FPS},
    }
    Path(path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--captures", type=Path, required=True, help="Folder with the cli, dashboard and agent captures")
    parser.add_argument("--fleet", type=Path, required=True, help="Output folder of windows-product-qa/fleet.py")
    parser.add_argument("--fonts", type=Path, required=True, help="Folder with the Geist and Geist Mono fonts")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--scenario", type=Path, default=HERE.parents[2] / "scenarios/windows/demo-powershell-system.example.yaml")
    parser.add_argument("--preview", nargs="*", type=float, help="Render these seconds to PNG files and a contact sheet")
    parser.add_argument("--crf", type=int, default=16)
    parser.add_argument("--receipt", type=Path,
                        help="Write the JSON record of the runs and recordings in this encoded film next to it, then exit")
    args = parser.parse_args()
    if args.receipt:
        write_receipt(args.captures, args.fleet, args.receipt, args.receipt.with_name(f"{args.receipt.stem}-attestation.json"))
        return 0
    args.out.mkdir(parents=True, exist_ok=True)
    look = Look(ev.Fonts(args.fonts))
    fleet = load_fleet(args.fleet, args.fonts, args.ffmpeg, args.out)
    label = args.scenario.resolve().relative_to(HERE.parents[2]).as_posix()
    chapters = []
    try:
        captured = []
        for chapter, folder, needed in ((RunChapter, "cli", "terminal.json"), (EvidenceChapter, "cli", "report.json"),
                                        (DashboardChapter, "dashboard", "dashboard.json"),
                                        (AgentChapter, "agent", "calls.json")):
            if (args.captures / folder / needed).exists():
                captured.append(chapter(look, args.captures / folder, args.ffmpeg))
            elif args.preview is None:
                raise FileNotFoundError(f"The film needs {folder}/{needed} under {args.captures}")
            else:
                print(f"Preview without {chapter.__name__}: {folder}/{needed} is missing", flush=True)
        chapters = [ColdOpen(look, fleet), ScenarioChapter(look, args.scenario, label), *captured,
                    ScaleChapter(look, fleet), EndCard(look, fleet)]
        film = Intro(look, chapters)
        print(f"{film.duration:.1f} s: " + ", ".join(f"{type(c).__name__} {c.duration:.1f}" for c in chapters),
              flush=True)
        if args.preview is not None:
            moments = args.preview or [start + chapter.duration / 2 for start, chapter in zip(film.starts, chapters)]
            sheet = Image.new("RGB", (960 * 2, 540 * math.ceil(len(moments) / 2)), "black")
            for index, moment in enumerate(moments):
                frame = film.frame(moment)
                frame.save(args.out / f"preview-{moment:06.2f}.png")
                sheet.paste(frame.resize((960, 540), Image.Resampling.LANCZOS), (index % 2 * 960, index // 2 * 540))
            sheet.save(args.out / "preview.png")
            return 0
        master = args.out / "oslab-intro-film.mp4"
        # Encode to a separate file so that a failed render keeps the previous master.
        partial = args.out / "oslab-intro-film.partial.mp4"
        render(film, partial, args.ffmpeg, args.crf)
        partial.replace(master)
        print(master, flush=True)
        return 0
    finally:
        close_readers(fleet, chapters)


if __name__ == "__main__":
    raise SystemExit(main())
