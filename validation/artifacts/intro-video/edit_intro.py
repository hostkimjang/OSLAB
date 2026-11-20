"""Edit the OSLab introduction film from real captures.

The film walks through OSLab in six chapters between a cold open and an end card:

1. Scenario: the YAML file of a public demo scenario.
2. Run: the terminal output of a real `oslab suite-run`, replayed next to the Windows fresh-install VM.
   The environment interlude shows all four consoles and follows the Ubuntu upgrade.
3. Evidence: the files and browser-recorded HTML report from that same Ubuntu upgrade.
4. Dashboard: a browser recording of the web dashboard launching a run on the lab.
5. AI agents: the console recording of a VM that an AI agent operated through the OSLab MCP
   server, next to the agent's tool calls.
6. Scale: the 32-VM Windows QA fleet edited by windows-product-qa/edit_video.py.

capture_suite.py, capture_dashboard.mjs and capture_agent.py record chapters 2 to 5.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import subprocess
import sys
import tempfile
from bisect import bisect_right
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
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
# Position and size of the OSLab logo on the end card, as brand() takes them. The 32 agents of chapter 6 land on it.
LOGO = (W / 2 - 250, 250, 100)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fit_rect(size, rect):
    """The largest rectangle with the image's aspect ratio centered in rect."""
    x, y, w, h = rect
    scale = min(w / size[0], h / size[1])
    return x + (w - size[0] * scale) / 2, y + (h - size[1] * scale) / 2, size[0] * scale, size[1] * scale


def dissolve(first, second, amount):
    return Image.blend(first, second, clamp(amount)) if amount > 0 else first


def piecewise(keys, t):
    """The value at t of the polyline through (t, value) keys and its slope there. Past the last key the value holds."""
    for (start, value), (end, next_value) in zip(keys, keys[1:]):
        if t <= end:
            rate = (next_value - value) / (end - start)
            return value + (t - start) * rate, rate
    return keys[-1][1], 0.0


def finale_timing(durations, opening, beats, finish):
    # When several runs finish together, they light up on the same beat.
    ends = sorted(set(durations))[-len(beats):]
    start = min(opening, max(0, ends[0] - .5))
    return [(0.0, start), *zip(beats[-len(ends):], ends), (finish, ends[-1] + 1.5)]


def crossing(keys, value):
    """First output second at which a nondecreasing source timeline reaches value."""
    if value < keys[0][1]:
        return -math.inf
    for (start, first), (end, last) in zip(keys, keys[1:]):
        if first <= value <= last:
            return start if last == first else mix(start, end, (value - first) / (last - first))
    return math.inf


def logo_center():
    x, y, size = LOGO
    unit = size / 28
    return x + 15 * unit, y + 10 * unit


def mark_point(rank, count):
    """A point inside one of the two slanted bars that brand() draws for the OSLab mark at LOGO."""
    x, y, size = LOGO
    unit = size / 28
    jitter = random.Random(rank)
    # The first bar is wider, so it takes a larger share of the agents.
    offset, width = (0, 9) if rank < count * .56 else (13, 7)
    along, across = jitter.uniform(.12, .88), jitter.uniform(.15, .85)
    bottom = (x + (offset + across * width) * unit, y + 20 * unit)
    top = (x + (offset + 10 + across * width) * unit, y)
    return mix(bottom[0], top[0], along), mix(bottom[1], top[1], along)


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

    def __init__(self, look, fleet, suite=False):
        self.look, self.fleet = look, fleet
        self.suite = suite
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
            title = "Every test gets a fresh VM." if self.suite else "Every test gets a fresh Windows VM."
            text(canvas, (48, 104), title, fonts("semibold", 68), INK)
            text(canvas, (50, 198), "OSLab clones a disposable VM, runs the test inside it, keeps the evidence "
                 "and removes the VM.", fonts("regular", 29), MUTED)
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
        guests = "Windows and Linux" if self.suite else "Windows"
        text(canvas, (W / 2, 668), f"{guests} on Proxmox  ·  CLI, web dashboard and MCP", fonts("mono", 24), MINT, c, "mm")
        return canvas


def look_copy(look):
    return look.background.copy()


class EndCard:
    duration = 4.0
    nav = False

    def __init__(self, look, fleet):
        self.look, self.fleet = look, fleet
        self.base = None

    def frame(self, t):
        fonts = self.look.fonts
        if self.base is None:
            self.base = self.fleet.story.diagram_background()
        canvas = self.base.copy()
        # The agents of chapter 6 have already formed the logo, so it stays in place from the first frame.
        brand(canvas, fonts, *LOGO)
        text(canvas, (W / 2, 470), "github.com/hostkimjang/OSLAB", fonts("semibold", 46), INK, ease_out(t / .5), "mm")
        return canvas


# 1. Scenario -----------------------------------------------------------------------------------

SECTIONS = [
    (("provider", "isolation"), "Clone a fresh VM from a Windows template"),
    (("guest",), "Reach the guest through QEMU Guest Agent"),
    (("artifact", "product"), "Upload the build and run the product checks"),
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
        self.bands = []
        for keys, title in SECTIONS:
            present = [spans[key] for key in keys if key in spans]
            if present:
                self.bands.append((min(start for start, _ in present), max(end for _, end in present), title))
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
                         "A scenario names the VM template, the build, the commands to run and the results to check.",
                         width=520)
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
        return canvas


# 2. Run ----------------------------------------------------------------------------------------

# Lifecycle steps with the phases that may start and finish them. A run with product steps reports them where a run
# with a single command reports the command, and only Windows runs that sign in to the desktop have a Sign in step.
STEPS = [
    ("Clone", ("vm.clone.start",), ("vm.clone.done",)),
    ("Boot", ("vm.start.start",), ("vm.boot.done",)),
    ("Guest agent", ("guest.ready.wait",), ("guest.ready.done",)),
    ("Sign in", ("desktop.signin.start",), ("desktop.signin.done",)),
    ("Preflight", ("preflight.start",), ("preflight.done",)),
    ("Upload", ("artifact.prepare.start",), ("artifact.upload.done",)),
    ("Run", ("product.command.start", "product.step.start"), ("product.command.done", "product.steps.write.done")),
    ("Assert", ("output.collect.start",), ("assertions.done",)),
    ("Destroy", ("vm.stop.start",), ("vm.destroy.done",)),
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

    def moment(self, *phases, default=None):
        return next((self.at(phase) for phase in phases if phase in self.first), default)

    @property
    def completed(self):
        return self.moment("run.done", "run.failed", default=self.events[-1]["epoch"])

    def vm_running(self, epoch):
        started = self.moment("vm.start.done", "vm.boot.done", default=math.inf)
        stopped = self.moment("vm.stop.done", "vm.destroy.done", default=math.inf)
        return started <= epoch < stopped

    def console_visible(self, clip, epoch):
        # Use the runner's confirmed final state: VNC's first "powered off" reading may be a transient reboot.
        stopped = self.moment("vm.stop.done", "vm.destroy.done", default=clip.end)
        return clip.t0 <= epoch < stopped

    def lifecycle(self):
        """The lifecycle steps this run went through, as (name, start phase, finish phase)."""
        steps = []
        for name, starts, finishes in STEPS:
            start = next((phase for phase in starts if phase in self.first), None)
            finish = next((phase for phase in finishes if phase in self.first), None)
            if start and finish:
                steps.append((name, start, finish))
        return steps

    def product_steps(self):
        """Product step timings and outcomes, including interrupted steps."""
        steps, pending = [], {}
        for event in self.events:
            phase = event["phase"]
            step_id = event.get("details", {}).get("stepId")
            if not step_id:
                continue
            if phase == "product.step.start":
                step = [step_id, event["epoch"], self.completed, "interrupted"]
                steps.append(step)
                pending[step_id] = step
            elif phase in ("product.step.done", "product.step.failed") and step_id in pending:
                step = pending.pop(step_id)
                step[2:] = [event["epoch"], "passed" if phase.endswith(".done") else "failed"]
        return steps


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
    terminal_rect = (48, 206, 800, 830)
    console_rect = (872, 206, 1000, 650)
    lifecycle_rect = (872, 876, 1000, 160)
    row_height = 26

    def __init__(self, look, folder, ffmpeg, suite=None):
        self.look = look
        terminal_folder = suite.folder if suite else folder
        self.terminal = load_json(terminal_folder / "terminal.json")
        self.aliases = load_json(terminal_folder / "aliases.json")
        self.suite = suite
        self.progress = Progress(folder / "progress.jsonl")
        self.steps = self.progress.lifecycle()
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
        done = self.progress.completed
        events = [self.progress.at(finish) for _, _, finish in self.steps] + [done]
        # Console windows on the desktop play near real time, so the viewer can read each step.
        events += [event["epoch"] for event in self.progress.events if event["phase"].startswith("desktop.console.")]
        # Play on until the last line the CLI printed, which can come after run.done.
        end = max(done + .4, lines[-1]["t"] + .2) if lines and not suite else done + .4
        self.remap = Remap(self.terminal["started"], end, events,
                           self.duration - self.typing - self.hold, before=.6, after=.9, cap=6.0)
        self.command = aliased(self.terminal["command"], self.aliases)
        self.font = look.fonts("mono", 19)
        self.limit = int((self.terminal_rect[2] - 42) / look.width("M", self.font))
        # Wrap the recorded output once. Each frame shows the rows printed by its source time.
        self.rows = []
        for row in lines:
            for piece_row in wrap_pieces(terminal_pieces(aliased(row["text"].rstrip(), self.aliases)), self.limit):
                self.rows.append((row["t"], piece_row))
        self.row_times = [moment for moment, _ in self.rows]
        # While the product steps run in console windows on the desktop, the console view closes in on those windows.
        windows = [event for event in self.progress.events if event["phase"] == "desktop.console.start"]
        self.push = None
        if windows and all(key in windows[0]["details"] for key in ("width", "height", "top", "left")):
            window = windows[0]["details"]
            width, height = self.console.size
            # The window and a margin, widened to the screen's aspect ratio so the view keeps its size.
            crop_w = min(width, window["width"] + 40)
            crop_h = crop_w * height / width
            left = clamp(window["left"] - 20, 0, width - crop_w)
            top = clamp(window["top"] + window["height"] / 2 - crop_h / 2, 0, height - crop_h)
            first = windows[0]["epoch"]
            last = max((event["epoch"] for event in self.progress.events if event["phase"] == "desktop.console.done"),
                       default=self.progress.completed)
            self.push = ((left, top, crop_w, crop_h), self.typing + self.remap.output(first),
                         self.typing + self.remap.output(last))

    def console_crop(self, t):
        """The part of the VM screen the console view shows at film time t."""
        width, height = self.console.size
        if self.push is None:
            return 0, 0, width, height
        window, closer, back = self.push
        amount = ease(clamp((t - closer + .7) / .7)) * (1 - ease(clamp((t - back - .5) / .7)))
        return tuple(mix(whole, part, amount) for whole, part in zip((0, 0, width, height), window))

    def epoch(self, t):
        return self.remap.source(t - self.typing) if t >= self.typing else self.terminal["started"]

    def draw_terminal(self, canvas, t, a):
        look, font = self.look, self.font
        title = "oslab suite-run" if self.suite else "oslab run"
        content = look.window(canvas, self.terminal_rect, "Windows PowerShell", title, a, fill=TERMINAL)
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

    def draw_console(self, canvas, t, epoch, rect, a):
        look = self.look
        title = "Windows 11  ·  Fresh install" if self.suite else "Disposable VM  ·  Windows 11 console"
        content = look.window(canvas, rect, title, "Proxmox console", a, fill=(0, 0, 0))
        clone = self.progress.moment("vm.clone.done", default=self.console.t0)
        destroyed = self.progress.moment("vm.destroy.done")
        if self.progress.console_visible(self.console, epoch):
            crop = self.console_crop(t)
            place(canvas, self.console.at(epoch), fit_rect(self.console.size, content), crop, alpha=a)
            return
        if epoch < clone:
            message = "Cloning a VM from the template…"
        elif epoch < self.console.t0:
            message = "Starting the VM…"
        elif self.finished(epoch):
            return
        elif destroyed is not None and epoch >= destroyed:
            message = "VM destroyed"
        elif self.progress.moment("vm.stop.done") is not None and epoch >= self.progress.at("vm.stop.done"):
            message = "VM stopped"
        else:
            message = "Console recording ended"
        text(canvas, (content[0] + content[2] / 2, content[1] + content[3] / 2), message,
             look.fonts("mono", 24), MUTED, a, "mm")

    def finished(self, epoch):
        return epoch >= self.progress.completed

    def draw_lifecycle(self, canvas, t, epoch, rect, a):
        fonts = self.look.fonts
        x, y, w, h = rect
        box(canvas, rect, 14, fill=PANEL, outline=EDGE, alpha=a)
        started = self.progress.at("run.created")
        elapsed = max(0.0, min(epoch, self.progress.completed) - started) if t >= self.typing else 0.0
        text(canvas, (x + 22, y + 26), "LIFECYCLE  ·  REAL DURATIONS", fonts("mono", 17), DIM, a, "lm")
        text(canvas, (x + w - 22, y + 26), f"T+{int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}", fonts("mono", 17),
             MUTED, a, "rm")
        track_y = y + 84
        gap = (w - 80) / max(len(self.steps) - 1, 1)
        if len(self.steps) > 1:
            box(canvas, (x + 40, track_y - 2, w - 80, 4), 2, fill=EDGE, alpha=a)
        for index, (name, begin, done) in enumerate(self.steps):
            cx = x + w / 2 if len(self.steps) == 1 else x + 40 + index * gap
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
        caption = "A fresh Windows guest installs and checks the build on its desktop." if self.suite else (
            "One command clones the VM, runs the build, checks it and destroys the VM.")
        text(canvas, (640, 150), caption, fonts("regular", 26), MUTED, ease_out((t - .2) / .5), "lm")
        epoch = self.epoch(t)
        self.draw_terminal(canvas, t, a)
        self.draw_console(canvas, t, epoch if t >= self.typing else 0.0, self.console_rect, a)
        self.draw_lifecycle(canvas, t, epoch, self.lifecycle_rect, a)
        done = self.progress.completed
        if self.finished(epoch):
            age = t - self.typing - self.remap.output(done)
            x, y, w, h = self.console_rect
            look.stamp(canvas, (x + w / 2, y + h / 2), "PASS" if self.passed else "FAIL", self.verdict, age,
                       MINT if self.passed else CORAL)
        return canvas


# Environments between chapters 2 and 3 ------------------------------------------------------------

# The suite entries in tile order, left to right and top to bottom, with the system and the install path they test.
ENVIRONMENTS = {
    "windows-fresh": ("WINDOWS 11", "Fresh install", SKY),
    "windows-upgrade": ("WINDOWS 11", "Upgrade from 2.3", SKY),
    "ubuntu-fresh": ("UBUNTU 24.04", "Fresh install", AMBER),
    "ubuntu-upgrade": ("UBUNTU 24.04", "Upgrade from 2.3", AMBER),
}
FOCUS = "ubuntu-upgrade"  # The entry the chapter zooms into and whose evidence chapter 3 shows.
WINDOWS_RUN = "windows-fresh"
# What a tile's header names from the moment each phase starts. A running product step names itself instead.
STAGES = [
    ("Cloning", "vm.clone.start"), ("Booting", "vm.start.start"), ("Guest agent", "guest.ready.wait"),
    ("Signing in", "desktop.signin.start"), ("Preflight", "preflight.start"), ("Uploading", "artifact.prepare.start"),
    ("Checking", "output.collect.start"), ("Destroying the VM", "vm.stop.start"),
]


class SuiteCapture:
    """Match every recording and progress log to one child of the recorded suite."""

    def __init__(self, folder):
        self.folder = folder
        self.result = load_json(folder / "suite.json")
        self.run_id = self.result["runId"]
        terminal = load_json(folder / "terminal.json")
        if terminal.get("runId") != self.run_id:
            raise ValueError("The terminal recording belongs to a different suite run")
        self.entries = {row["id"]: row for row in load_json(folder / "entries.json")}
        results = {row["id"]: row for row in self.result["entries"]}
        if self.entries.keys() != ENVIRONMENTS.keys() or self.entries.keys() != results.keys():
            raise ValueError("The recorded suite must contain the four expected Windows and Ubuntu entries")
        self.progress = {}
        for entry_id, row in self.entries.items():
            if row["folder"] != entry_id:
                raise ValueError(f"Unexpected capture folder for {entry_id}")
            source = self.child(entry_id)
            child = load_json(source / "run.json")
            for field in ("runId", "scenarioId", "status"):
                if row[field] != child[field] or row[field] != results[entry_id][field]:
                    raise ValueError(f"The {field} for {entry_id} does not match its suite and child result")
            progress = Progress(source / "progress.jsonl")
            if progress.first["run.created"].get("details", {}).get("runId") != child["runId"]:
                raise ValueError(f"The progress log for {entry_id} belongs to a different run")
            self.progress[entry_id] = progress
            self.media(entry_id, "console")

    def child(self, entry_id):
        return self.folder / self.entries[entry_id]["folder"]

    def media(self, entry_id, kind):
        meta = load_json(self.child(entry_id) / f"{kind}.json")
        if meta.get("runId") != self.entries[entry_id]["runId"] or meta.get("suiteRunId", self.run_id) != self.run_id:
            raise ValueError(f"The {kind} recording for {entry_id} belongs to a different run")
        return meta

    def scenario_path(self, override=None):
        entry = self.entries[WINDOWS_RUN]
        path = (REPO / entry["scenario"]).resolve()
        if not path.is_relative_to(REPO):
            raise ValueError("The recorded Windows fresh-install scenario must be inside the repository")
        if override is not None and override.resolve() != path:
            raise ValueError("--scenario must match the recorded suite's Windows fresh-install scenario")
        if hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest() != entry["scenarioSha256"]:
            raise ValueError("The Windows fresh-install scenario has changed since it was recorded")
        return path


class Environment:
    """One suite entry: the console recording of its VM, its product steps and its result."""

    def __init__(self, suite, entry_id, ffmpeg):
        self.id = entry_id
        self.system, self.path, self.color = ENVIRONMENTS[entry_id]
        self.progress = suite.progress[entry_id]
        folder = suite.child(entry_id)
        run = load_json(folder / "run.json")
        assertions = run.get("details", {}).get("assertions", {})
        # The tile reports what the run recorded, so a failed run can never show PASS.
        self.passed = run.get("status") == "passed" and assertions.get("failed") == 0
        self.assertions = assertions.get("total", 0)
        meta = suite.media(entry_id, "console")
        self.console = Clip(ffmpeg, folder / "console.mkv", folder / "console.json") if meta.get("status") == "complete" else None
        if self.passed and self.console is None:
            raise ValueError(f"The passed {entry_id} run needs a complete console recording")
        self.stages = [(name, self.progress.at(phase)) for name, phase in STAGES if phase in self.progress.first]
        self.start = self.progress.at("run.created")
        self.done = self.progress.completed
        self.destroyed = self.progress.moment("vm.destroy.done", default=math.inf)
        self.steps = self.progress.product_steps()

    def stage(self, epoch):
        current = "Starting"
        for name, moment in self.stages:
            if epoch >= moment:
                current = name
        for step, begin, end, _ in self.steps:
            if begin <= epoch < end:
                current = step
        return current

def concurrent_testing(steps_by_entry):
    """A common instant must fall inside a real product step of every entry."""
    starts = {begin for steps in steps_by_entry for _, begin, _, _ in steps}
    return any(all(any(begin <= moment < end for _, begin, end, _ in steps) for steps in steps_by_entry)
               for moment in starts)


class EnvironmentsChapter:
    """The same agent checks as four entries of one `oslab suite-run`: Windows 11 and Ubuntu 24.04, each as a fresh
    install and as an upgrade from 2.3. The four consoles play side by side, the Ubuntu upgrade fills the screen
    while its steps run, and every tile shows its run's result."""

    duration = 24.0
    nav = False
    grid = (72, 196, 876, 410, 24)  # Left, top, tile width, tile height and gap of the 2x2 grid.
    zoom_in, zoom_out, settle, zoom_scale = 9.4, 15.6, 21.0, 1.45

    def __init__(self, look, suite, ffmpeg):
        self.look = look
        self.envs = [Environment(suite, key, ffmpeg) for key in ENVIRONMENTS]
        self.clips = [env.console for env in self.envs if env.console is not None]
        self.focus = next(env for env in self.envs if env.id == FOCUS)
        self.parallel = concurrent_testing([env.steps for env in self.envs])
        start, end = min(env.start for env in self.envs), max(env.done for env in self.envs)
        # Source time runs fast up to the zoom, near real time while the focused upgrade runs its steps, fast again
        # until the last run finishes, and holds on the results.
        self.keys = [(0.0, start), (self.settle, end), (self.duration, end)]
        if self.focus.steps and self.focus.console is not None:
            first, last = self.focus.steps[0][1], self.focus.steps[-1][2]
            self.keys[1:1] = [(self.zoom_in + .7, max(start, first - 1.0)), (self.zoom_out, min(end, last + 1.0))]
        else:
            self.zoom_in = self.zoom_out = self.duration
        self.outcome_times = {env.id: crossing(self.keys, env.done) for env in self.envs}

    def tile_rect(self, index):
        left, top, width, height, gap = self.grid
        return left + index % 2 * (width + gap), top + index // 2 * (height + gap), width, height

    def zoom_rect(self):
        left, top, width, height, gap = self.grid
        return left, top, 2 * width + gap, 2 * height + gap

    def draw_tile(self, canvas, env, rect, epoch, t, scale=1.0, alpha=1.0, highlight=0.0):
        """A console with the entry's name, its current stage, its product steps and, once finished, its result."""
        look, fonts = self.look, self.look.fonts
        x, y, w, h = rect
        finished = epoch >= env.done
        edge = MINT if finished and env.passed else CORAL if finished else EDGE
        box(canvas, rect, 14, fill=PANEL, outline=edge, width=2 if finished else 1, alpha=alpha)
        if highlight > .01:
            box(canvas, (x - 5, y - 5, w + 10, h + 10), 18, outline=MINT, width=3, alpha=alpha * highlight)
        header = 44 * scale
        system = fonts("mono-bold", round(16 * scale))
        text(canvas, (x + 18 * scale, y + header / 2), env.system, system, env.color, alpha, "lm")
        text(canvas, (x + 30 * scale + look.width(env.system, system), y + header / 2), env.path,
             fonts("medium", round(20 * scale)), INK, alpha, "lm")
        if not finished:
            stage = env.stage(epoch)
            font = fonts("mono", round(16 * scale))
            right = x + w - 18 * scale
            text(canvas, (right, y + header / 2), stage, font, MUTED, alpha, "rm")
            dot = 4 * scale
            pulse = .55 + .45 * math.sin(t * 6)
            box(canvas, (right - look.width(stage, font) - 14 * scale, y + header / 2 - dot, 2 * dot, 2 * dot), dot,
                fill=AMBER, alpha=alpha * pulse)
        box(canvas, (x + 1, y + header, w - 2, 1), 0, fill=EDGE, alpha=alpha)
        # The console on the left, the steps and the result on the right.
        pad = 12 * scale
        height = h - header - 2 * pad
        size = env.console.size if env.console else (1280, 800)
        width = min(height * size[0] / size[1], w - 245 * scale)
        screen = (x + pad, y + header + pad, width, height)
        box(canvas, screen, 8 * scale, fill=(0, 0, 0), alpha=alpha)
        if env.console and env.progress.console_visible(env.console, epoch):
            place(canvas, env.console.at(epoch), fit_rect(size, screen), radius=round(8 * scale), alpha=alpha)
        else:
            if epoch >= env.destroyed:
                message = "VM removed"
                if env.console and env.steps:
                    frame = env.console.at(env.steps[-1][2])
                    place(canvas, frame, fit_rect(size, screen), radius=round(8 * scale), alpha=.30 * alpha)
            elif env.console and epoch < env.console.t0:
                message = env.stage(epoch)
            elif env.progress.vm_running(epoch):
                message = "Console unavailable"
            elif finished:
                message = "No console recording"
            else:
                message = env.stage(epoch)
            if epoch >= env.destroyed:
                middle = screen[0] + screen[2] / 2, screen[1] + screen[3] / 2
                box(canvas, (middle[0] - 82 * scale, middle[1] - 18 * scale, 164 * scale, 36 * scale), 7 * scale,
                    fill=TERMINAL, outline=EDGE, alpha=alpha)
            text(canvas, (screen[0] + screen[2] / 2, screen[1] + screen[3] / 2), message,
                 fonts("mono", round(18 * scale)), MUTED, alpha, "mm")
        column = screen[0] + screen[2] + 20 * scale
        yy = screen[1] + 4 * scale
        text(canvas, (column, yy), "STEPS", fonts("mono", round(14 * scale)), DIM, alpha)
        yy += 34 * scale
        for step, begin, end, status in env.steps:
            done, running = epoch >= end, begin <= epoch < end
            color = MINT if done and status == "passed" else CORAL if done else AMBER if running else DIM
            radius = 9 * scale
            box(canvas, (column, yy - radius, 2 * radius, 2 * radius), radius,
                fill=color if done or running else None, outline=color, width=max(1, round(2 * scale)), alpha=alpha)
            if done:
                if status == "passed":
                    points = ((column + 5 * scale, yy), (column + 8 * scale, yy + 3.5 * scale),
                              (column + 13.5 * scale, yy - 3.5 * scale))
                    ImageDraw.Draw(canvas).line(points, fill=(6, 30, 28), width=max(2, round(2.4 * scale)))
                else:
                    text(canvas, (column + radius, yy), "×", fonts("medium", round(14 * scale)), (6, 30, 28), alpha, "mm")
            text(canvas, (column + 30 * scale, yy), step, fonts("mono", round(19 * scale)),
                 INK if done or running else DIM, alpha, "lm")
            yy += 38 * scale
        bottom = screen[1] + screen[3]
        if finished:
            age = t - self.outcome_times[env.id]
            pop = 1 + .3 * (1 - ease_out(clamp(age / .3)))
            label = "PASS" if env.passed else "FAIL"
            pill = (column, bottom - 74 * scale, 92 * scale * pop, 34 * scale * pop)
            box(canvas, pill, 8 * scale, fill=MINT if env.passed else CORAL, alpha=alpha)
            text(canvas, (pill[0] + pill[2] / 2, pill[1] + pill[3] / 2), label, fonts("mono-bold", round(19 * scale * pop)),
                 (6, 30, 28), alpha, "mm")
            text(canvas, (column, bottom - 18 * scale), f"{env.assertions} assertions", fonts("regular", round(19 * scale)),
                 MUTED, alpha, "ls")
        else:
            elapsed = max(0.0, epoch - env.start)
            text(canvas, (column, bottom - 18 * scale), f"T+{int(elapsed) // 60:02d}:{int(elapsed) % 60:02d}",
                 fonts("mono", round(18 * scale)), MUTED, alpha, "ls")

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        epoch, _ = piecewise(self.keys, t)
        brand(canvas, fonts, 48, 42, 26)
        a = ease_out(t / .5)
        label = "SUITE  ·  4 ENVIRONMENTS IN PARALLEL" if self.parallel else "SUITE  ·  4 ENVIRONMENTS"
        text(canvas, (48, 100), label, fonts("mono", 18), MINT, a)
        text(canvas, (48, 128 + 10 * (1 - a)), "When the OS or the build changes, run every path again.",
             fonts("semibold", 44), INK, a)
        running = sum(env.progress.vm_running(epoch) for env in self.envs)
        passed = sum(epoch >= env.done and env.passed for env in self.envs)
        x = W - 48
        for title, value, color in (("PASSED", f"{passed}/{len(self.envs)}", MINT), ("VMS RUNNING", str(running), INK)):
            text(canvas, (x, 92), title, fonts("mono", 16), MUTED, a, "ra")
            text(canvas, (x, 116), value, fonts("mono-bold", 36), color, a, "ra")
            x -= 200
        zoom = ease(clamp((t - self.zoom_in) / .7)) * (1 - ease(clamp((t - self.zoom_out) / .7)))
        ending = ease(clamp((t - self.settle) / .6))
        for index, env in enumerate(self.envs):
            if env is self.focus and zoom > 0:
                continue
            appear = ease_out(clamp((t - .15 - index * .12) / .45))
            dim = 1 - .25 * ending if env is not self.focus else 1.0
            x, y, w, h = self.tile_rect(index)
            grow = mix(.94, 1.0, appear)
            rect = (x + w * (1 - grow) / 2, y + h * (1 - grow) / 2, w * grow, h * grow)
            self.draw_tile(canvas, env, rect, epoch, t, alpha=appear * dim,
                           highlight=ending if env is self.focus else 0.0)
        if zoom > 0:
            small = self.tile_rect(self.envs.index(self.focus))
            rect = tuple(mix(start, end, zoom) for start, end in zip(small, self.zoom_rect()))
            self.draw_tile(canvas, self.focus, rect, epoch, t, mix(1.0, self.zoom_scale, zoom))
        return canvas


# 3. Evidence ------------------------------------------------------------------------------------

FILE_NOTES = {
    "run.json": "status, timings and file index",
    "logs/progress.jsonl": "every lifecycle step",
    "raw/actual-output.json": "what the build wrote",
    "normalized/command-result.json": "what the assertions read",
    "normalized/inventory.json": "what the assertions read",
    "reports/result.json": "for tools",
    "reports/result.junit.xml": "for CI",
    "reports/result.html": "for people",
}


class EvidenceChapter:
    number = 3
    duration = 13.5
    nav = True

    def __init__(self, look, folder, ffmpeg, suite=None):
        self.look = look
        # One row per file, with a row for each folder before its first file.
        self.rows = []
        folders = set()
        for line in (folder / "runtree.txt").read_text(encoding="utf-8").splitlines():
            parts = line.rsplit(None, 1)
            if len(parts) != 2 or not parts[1].isdigit():
                continue
            path = parts[0].replace("\\", "/").lstrip("/")
            if suite and path not in FILE_NOTES:
                continue
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
        run_id = load_json(folder / "run.json")["runId"]
        self.run_path = f"scenarios/{run_id}/" if suite else f"runs/{run_id}/"
        self.caption = "The Ubuntu upgrade leaves logs, inventory output, and JSON, JUnit and HTML reports." if suite else (
            "Logs, raw and normalized output, and JSON, JUnit and HTML reports land in one folder.")

    def frame(self, t):
        look, fonts = self.look, self.look.fonts
        canvas = look_copy(look)
        y = look.heading(canvas, t, 3, "Every run leaves evidence.", self.caption)
        y += 26
        text(canvas, (48, y), self.run_path, fonts("mono-bold", 18), INK, ease_out((t - .5) / .4))
        y += 40
        for index, (path, name, depth) in enumerate(self.rows):
            if y + 33 > H - 44:
                break
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
        return canvas


# 6. Scale -----------------------------------------------------------------------------------------


def load_fleet(fleet_dir, fonts, ffmpeg, work):
    args = SimpleNamespace(fonts=fonts, ffmpeg=ffmpeg, open_tau=20.0)
    cases = ev.load_cases(fleet_dir)
    ev.make_proxies(cases, ffmpeg, work / "proxies")
    film = ev.Film(args, cases)
    # The intro film keeps the screen clean. docs/intro-video.md explains how the wall was recorded.
    film.disclosures = False
    story = ev.Story(film, ev.build_features(film, ev.FEATURES, ffmpeg), ev.build_montage(film, ev.MONTAGE, ffmpeg), args)
    return SimpleNamespace(film=film, story=story)


class ScaleChapter:
    """The 32-VM Windows QA wall, two zoomed fixes, how the agents reach the VMs, eight more programs and the
    finished wall. A wave of light runs over the passed tiles, the result comes up, and the agents leave their VMs
    to form the OSLab logo of the end card."""

    number = 6
    nav = False
    finale_length, victory_length, swarm_length = 5.5, 3.0, 2.8
    score_from = 3.4  # Seconds before the end of the finale when the running score takes the middle of the screen.
    # Seconds into the finale at which the fourth-to-last program has just passed and the last three programs pass.
    # The score comes up on 29/32 and counts to 32/32 one program at a time, in the order the runs really finished.
    last_passes = (2.0, 2.75, 3.45, 4.25)

    def __init__(self, look, fleet):
        self.look = look
        story, film = fleet.story, fleet.film
        self.story, self.film = story, film
        self.finished = None
        self.background = None
        # A soft shadow behind the result so the numbers stay legible over the wall.
        shade = Image.new("L", (W, H), 0)
        ImageDraw.Draw(shade).ellipse((W / 2 - 800, 230, W / 2 + 800, 910), fill=245)
        self.shade = shade.filter(ImageFilter.GaussianBlur(80))
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
            (self.finale_length, self.finale, True),
            (self.victory_length, self.victory, True),
            (self.swarm_length, self.swarm, False),
        ]
        self.dissolves = {7, 8}  # Into the montage and into the finale, which share no camera move.
        self.duration = sum(length for length, _, _ in self.shots)
        # The finale plays the end of the wall at an uneven pace. Between these keys the wall time runs linearly.
        self.finale_keys = finale_timing((case.duration for case in film.cases), story.final_tau, self.last_passes,
                                         self.finale_length)
        self.pass_moments = {case.id: crossing(self.finale_keys, case.duration) for case in film.cases}
        # Where each agent rests on the finished wall and where it lands in the logo. The agents farthest from the
        # logo leave first, so the whole swarm arrives within about a second.
        self.rests, self.targets = {}, {}
        for index, case in enumerate(film.cases):
            x, y, w, h = film.tile_rect(index)
            px, py = film.tracks[case.id].position(case.start + case.duration, .45 * story.final_rate)
            self.rests[case.id] = (x + px * w / ev.VM_W, y + py * h / ev.VM_H)
        self.order = sorted(film.cases, key=lambda case: -math.dist(self.rests[case.id], logo_center()))
        for rank, case in enumerate(self.order):
            self.targets[case.id] = mark_point(rank, len(film.cases))

    def finished_wall(self):
        """The last frame of the finale without its cursors, which the ending draws itself."""
        if self.finished is None:
            story, film = self.story, self.film
            canvas = film.background.copy()
            tau = self.final_tau()
            film.wall(canvas, tau, rate=story.final_rate, cursors=0)
            text(canvas, (48, 104), "Every run checked inside its own guest.", film.fonts("semibold", 64), INK)
            brand(canvas, film.fonts, 48, 40, 30)
            film.counters(canvas, tau, rate=story.final_rate)
            # Time stops from here, so the time-lapse label under the clock goes away.
            label = (W - 300, 964, W - 40, 998)
            canvas.paste(film.background.crop(label), label[:2])
            self.finished = canvas
        return self.finished

    def end_background(self):
        if self.background is None:
            self.background = self.story.diagram_background()
        return self.background

    def arrow(self, canvas, case_id, point, alpha=1.0):
        """An agent's arrow without its name tag."""
        sprite, tip, _, _ = self.film.pointers[case_id, "wall"]
        sprite = ev.faded(sprite, alpha)
        canvas.paste(sprite, (round(point[0]) - tip, round(point[1]) - tip), sprite)

    def score(self, canvas, tau, alpha=1.0, size=1.0, t=None):
        """The programs and their checks that have passed by this point in the recording."""
        if alpha <= .01:
            return
        fonts, film = self.look.fonts, self.film
        passed = [case for case in film.cases if tau >= case.duration]
        checks = sum(len(case.checks) for case in passed)
        if t is not None and passed:
            age = t - max(self.pass_moments[case.id] for case in passed)
            size *= 1 + .1 * (1 - ease_out(clamp(age / .35)))
        canvas.paste((4, 7, 12), (0, 0), self.shade.point(lambda value: round(value * alpha)))
        text(canvas, (W / 2, 420), f"{len(passed)}/{len(film.cases)}", fonts("mono-bold", round(170 * size)), MINT, alpha,
             "mm")
        text(canvas, (W / 2, 548), "Windows programs passed", fonts("medium", 36), INK, alpha, "mm")
        text(canvas, (W / 2, 668), str(checks), fonts("mono-bold", 64), INK, alpha, "mm")
        text(canvas, (W / 2, 728), "guest checks passed", fonts("regular", 28), MUTED, alpha, "mm")

    def finale(self, t):
        story, film = self.story, self.film
        tau, rate = piecewise(self.finale_keys, t)
        canvas = story.finale(t, tau=tau, rate=rate)
        # Each program that finishes now lights its tile, in the order the runs really finished.
        for index, case in enumerate(film.cases):
            age = t - self.pass_moments[case.id]
            if 0 <= age < .6:
                x, y, w, h = film.tile_rect(index, (mix(1.06, 1.0, ease(t / self.finale_length)), W / 2, H / 2))
                glow = 1 - age / .6
                box(canvas, (x - 4, y - 4, w + 8, h + 8), 8, fill=MINT, alpha=.18 * glow)
                box(canvas, (x - 4, y - 4, w + 8, h + 8), 8, outline=MINT, width=3, alpha=glow)
        self.score(canvas, tau, ease_out((t - self.finale_length + self.score_from) / .4), t=t)
        return canvas

    def victory(self, t):
        film = self.film
        # The wall settles into the end card's background while the result comes up.
        canvas = Image.blend(self.finished_wall(), self.end_background(), .86 * ease((t - .3) / .8))
        resting = mix(.35, .18, ease((t - .3) / .8))
        for case in film.cases:
            self.arrow(canvas, case.id, self.rests[case.id], resting)
        # The final count stays as it is and only grows a little, so it reads as the result.
        self.score(canvas, self.final_tau(), size=mix(1.0, 1.12, ease_out(t / .4)))
        return canvas

    def final_tau(self):
        return self.finale_keys[-1][1]

    def swarm(self, t):
        film, fonts = self.film, self.look.fonts
        canvas = self.end_background().copy()
        self.score(canvas, self.final_tau(), 1 - ease(t / .35), 1.12)
        trails = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        trail = ImageDraw.Draw(trails)
        flying, arrived = [], 0
        for rank, case in enumerate(self.order):
            launch = .15 + rank * .028
            landing = launch + .85
            start, target = self.rests[case.id], self.targets[case.id]
            if t < launch:
                self.arrow(canvas, case.id, start, mix(.18, 1.0, ease((t - launch + .3) / .3)))
                continue
            if t >= landing:
                arrived += 1
                film.ripple(canvas, target, film.colors[case.id], t - landing, .35, 14)
                continue
            swing = 1 if rank % 2 else -1
            path = (start, (start[0] + 90 * swing, start[1] - 170), (target[0] - 220 * swing, target[1] + 260), target)
            progress = ease((t - launch) / (landing - launch))
            color = film.colors[case.id]
            for step in range(1, 9):
                tx, ty = ev.bezier(path, max(0.0, progress - step * .025))
                radius = 3.2 * (1 - step / 9)
                trail.ellipse((tx - radius, ty - radius, tx + radius, ty + radius), fill=(*color, round(160 * (1 - step / 9))))
            flying.append((case.id, ev.bezier(path, progress)))
        canvas.paste(trails, (0, 0), trails)
        # The logo fills in as the agents land on it.
        brand(canvas, fonts, *LOGO, clamp((arrived / len(self.order) - .3) / .7))
        for case_id, point in flying:
            self.arrow(canvas, case_id, point)
        return canvas

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


def lifecycle_record(progress):
    return [{"name": name, "start_phase": begin, "finish_phase": done,
             "seconds": round(progress.at(done) - progress.at(begin), 1)}
            for name, begin, done in progress.lifecycle()]


def suite_record(suite):
    children = []
    steps_by_entry = []
    for entry_id in ENVIRONMENTS:
        entry = suite.entries[entry_id]
        child = suite.child(entry_id)
        progress = suite.progress[entry_id]
        steps = progress.product_steps()
        steps_by_entry.append(steps)
        console = suite.media(entry_id, "console")
        record = {
            "entry_id": entry_id,
            "scenario_file": entry["scenario"],
            "scenario_sha256": entry["scenarioSha256"],
            **run_record(child),
            "lifecycle": lifecycle_record(progress),
            "product_steps": [{"id": step, "status": status, "seconds": round(end - begin, 3)}
                              for step, begin, end, status in steps],
            "console_recording": recording(console) if console.get("status") == "complete" else None,
        }
        if entry_id == FOCUS:
            record["report_recording"] = recording(suite.media(entry_id, "report"))
        children.append(record)
    return {"run_id": suite.run_id, "suite_id": suite.result["suiteId"], "status": suite.result["status"],
            "summary": suite.result["summary"], "run_chapter_entry": WINDOWS_RUN, "evidence_chapter_entry": FOCUS,
            "all_product_checks_overlapped": concurrent_testing(steps_by_entry), "children": children}


def write_receipt(captures, fleet_dir, video, path, suite=None):
    """Record the runs, the agent session and the recordings that the film shows, without VM IDs or lab host
    names."""
    cli, dashboard, agent = captures / "cli", captures / "dashboard", captures / "agent"
    session = load_json(agent / "calls.json")
    calls_by_tool = {}
    for call in session["calls"]:
        calls_by_tool[call["tool"]] = calls_by_tool.get(call["tool"], 0) + 1
    cases = ev.load_cases(fleet_dir)
    data = Path(video).read_bytes()
    receipt = {
        "schema_version": 2 if suite else 1,
        "title": "OSLab introduction film",
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
            "Chapter 04 uses a separate dashboard run launched by Playwright. Chapter 05 uses a separate Codex session. "
            "The opening and chapter 06 reuse the 32-VM Windows QA recordings.",
            "The edit changes playback speed between events and holds on selected results.",
            "The YAML and terminal panels are typeset from the scenario file and the recorded CLI output. Command "
            "typing is animated.",
            "Local host names, user folders and private variable names are replaced in the terminal text, the HTML "
            "report and the dashboard.",
            "The editor draws the cursors at the recorded pointer positions and interpolates the movement between them.",
            "The 32-VM wall aligns recordings made in waves of up to eight at each run's start. The final cursor "
            "movement toward the logo is animated.",
        ],
        "video": {"file": Path(video).name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                  "width": W, "height": H, "fps": FPS},
    }
    if suite:
        receipt["suite_run"] = suite_record(suite)
        receipt["edits"].insert(0, "Chapter 02 follows the Windows fresh install from the recorded suite. The environment "
                                "interlude uses one source clock for all four consoles and holds the last product frames "
                                "under a VM removed label. Chapter 03 shows the same Ubuntu upgrade's report.")
    else:
        receipt["cli_run"] = {
            **run_record(cli),
            "steps": lifecycle_record(Progress(cli / "progress.jsonl")),
            "console_recording": recording(load_json(cli / "console.json")),
            "report_recording": recording(load_json(cli / "report.json")),
        }
        receipt["edits"].insert(0, "Chapters 02 and 03 show one CLI run.")
    Path(path).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--captures", type=Path, required=True, help="Folder with suite, dashboard and agent captures")
    parser.add_argument("--fleet", type=Path, required=True, help="Output folder of windows-product-qa/fleet.py")
    parser.add_argument("--fonts", type=Path, required=True, help="Folder with the Geist and Geist Mono fonts")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--scenario", type=Path, help="Scenario to show (default: the recorded Windows fresh-install scenario)")
    parser.add_argument("--legacy-cli", action="store_true", help="Use the single-run cli capture instead of the environment suite")
    parser.add_argument("--preview", nargs="*", type=float, help="Render these seconds to PNG files and a contact sheet")
    parser.add_argument("--crf", type=int, default=16)
    parser.add_argument("--receipt", type=Path,
                        help="Write the JSON record of the runs and recordings in this encoded film next to it, then exit")
    args = parser.parse_args()
    suite = None if args.legacy_cli else SuiteCapture(args.captures / "suite")
    if args.receipt:
        write_receipt(args.captures, args.fleet, args.receipt,
                      args.receipt.with_name(f"{args.receipt.stem}-attestation.json"), suite)
        return 0
    scenario = suite.scenario_path(args.scenario) if suite else (
        args.scenario or REPO / "scenarios/windows/demo-powershell-system.example.yaml")
    label = scenario.resolve().relative_to(REPO).as_posix()
    args.out.mkdir(parents=True, exist_ok=True)
    look = Look(ev.Fonts(args.fonts))
    fleet = load_fleet(args.fleet, args.fonts, args.ffmpeg, args.out)
    chapters = []
    try:
        chapters.extend((ColdOpen(look, fleet, suite is not None), ScenarioChapter(look, scenario, label)))
        if suite:
            suite.media(FOCUS, "report")
            chapters.append(RunChapter(look, suite.child(WINDOWS_RUN), args.ffmpeg, suite))
            chapters.append(EnvironmentsChapter(look, suite, args.ffmpeg))
            chapters.append(EvidenceChapter(look, suite.child(FOCUS), args.ffmpeg, suite))
            sources = []
        else:
            sources = [(RunChapter, "cli", "terminal.json"), (EvidenceChapter, "cli", "report.json")]
        sources.extend([(DashboardChapter, "dashboard", "dashboard.json"), (AgentChapter, "agent", "calls.json")])
        for chapter, folder, needed in sources:
            if (args.captures / folder / needed).exists():
                chapters.append(chapter(look, args.captures / folder, args.ffmpeg))
            elif args.preview is None:
                raise FileNotFoundError(f"The film needs {folder}/{needed} under {args.captures}")
            else:
                print(f"Preview without {chapter.__name__}: {folder}/{needed} is missing", flush=True)
        chapters.extend((ScaleChapter(look, fleet), EndCard(look, fleet)))
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
        # A failed render leaves the previous master in place and removes the partial encode.
        with tempfile.TemporaryDirectory(prefix="oslab-render-", dir=args.out) as work:
            partial = Path(work) / master.name
            render(film, partial, args.ffmpeg, args.crf)
            partial.replace(master)
        print(master, flush=True)
        return 0
    finally:
        close_readers(fleet, chapters)


if __name__ == "__main__":
    raise SystemExit(main())
