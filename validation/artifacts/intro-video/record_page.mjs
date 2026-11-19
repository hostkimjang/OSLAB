// Record an HTML page in headless Chromium for the OSLab introduction film.
//
// The page opens at a fixed viewport, and the aliases replace private names in its text. The
// recording holds at the top, scrolls slowly to the bottom and holds again. Frames come from the
// DevTools screencast as PNG images with their capture times. ffmpeg assembles them at a constant
// frame rate and repeats each image until the next one was captured, so text stays sharp and the
// motion keeps its real timing. The recording's metadata goes to a JSON file next to the video.
//
//   node validation/artifacts/intro-video/record_page.mjs --page <file.html> --output <video.mkv>
//     [--screenshot <full-page.png>] [--aliases <aliases.json>] [--markers <blocklist.txt>]
//     [--ffmpeg <ffmpeg>] [--chromium <executable>] [--width 1600] [--height 1000]
//     [--hold 1.5] [--scroll 8] [--tail 1.5] [--fps 30]
//
// --aliases takes [{"find", "replace"}] as written by capture_cli.py. With --markers, the script
// stops before recording if a marker still appears in the page text, without printing the marker.
// --chromium (or OSLAB_CHROMIUM) selects a Chromium executable when Playwright's own download for
// its version is not installed.

import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

import { chromium } from "@playwright/test";

const { values: options } = parseArgs({
  options: {
    page: { type: "string" },
    output: { type: "string" },
    screenshot: { type: "string" },
    aliases: { type: "string" },
    markers: { type: "string" },
    ffmpeg: { type: "string", default: process.env.OSLAB_FFMPEG ?? "ffmpeg" },
    chromium: { type: "string", default: process.env.OSLAB_CHROMIUM },
    width: { type: "string", default: "1600" },
    height: { type: "string", default: "1000" },
    hold: { type: "string", default: "1.5" },
    scroll: { type: "string", default: "8" },
    tail: { type: "string", default: "1.5" },
    fps: { type: "string", default: "30" },
  },
});

// Runs in the page: rewrite every text node, including the title, with the aliases in order.
function replaceText(aliases) {
  const walker = document.createTreeWalker(document.documentElement, NodeFilter.SHOW_TEXT);
  let changed = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    let value = node.nodeValue;
    for (const { find, replace } of aliases) {
      value = value.split(find).join(replace);
    }
    if (value !== node.nodeValue) {
      node.nodeValue = value;
      changed += 1;
    }
  }
  return changed;
}

// Runs in the page: the indexes of the markers that appear in its text, compared without case.
function findMarkers(markers) {
  const text = document.documentElement.textContent.toLowerCase();
  return markers.flatMap((marker, index) => (text.includes(marker.toLowerCase()) ? [index] : []));
}

// Runs in the page: scroll to the bottom with a sine ease, so the motion starts and stops gently.
function scrollToBottom(seconds) {
  return new Promise((done) => {
    const distance = document.documentElement.scrollHeight - window.innerHeight;
    const start = performance.now();
    function step(now) {
      const progress = Math.min(1, (now - start) / (seconds * 1000));
      window.scrollTo(0, (distance * (1 - Math.cos(Math.PI * progress))) / 2);
      if (progress < 1) {
        requestAnimationFrame(step);
      } else {
        done(distance);
      }
    }
    requestAnimationFrame(step);
  });
}

async function recordScroll(page, folder, size, timing) {
  const devtools = await page.context().newCDPSession(page);
  const frames = [];
  devtools.on("Page.screencastFrame", ({ data, metadata, sessionId }) => {
    const file = join(folder, `frame-${String(frames.length).padStart(5, "0")}.png`);
    writeFileSync(file, Buffer.from(data, "base64"));
    frames.push({ file, time: metadata.timestamp ?? Date.now() / 1000 });
    devtools.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  await devtools.send("Page.startScreencast", { format: "png", maxWidth: size.width, maxHeight: size.height });
  while (!frames.length) {
    await page.waitForTimeout(20);
  }
  await page.waitForTimeout(timing.hold * 1000);
  const distance = await page.evaluate(scrollToBottom, timing.scroll);
  await page.waitForTimeout(timing.tail * 1000);
  const end = Date.now() / 1000;
  await devtools.send("Page.stopScreencast");
  await devtools.detach();
  return { frames, end, distance };
}

// Show, for each output frame, the latest screencast image captured by that frame's time.
function encode(frames, end, folder, output, fps, ffmpeg) {
  const t0 = frames[0].time;
  const total = Math.max(1, Math.round((end - t0) * fps));
  const runs = [];
  let index = 0;
  for (let frame = 0; frame < total; frame += 1) {
    while (index + 1 < frames.length && frames[index + 1].time <= t0 + frame / fps) {
      index += 1;
    }
    const last = runs.at(-1);
    if (last && last.index === index) {
      last.count += 1;
    } else {
      runs.push({ index, count: 1 });
    }
  }
  const lines = ["ffconcat version 1.0"];
  for (const run of runs) {
    lines.push(`file '${basename(frames[run.index].file)}'`, `duration ${(run.count / fps).toFixed(6)}`);
  }
  // The concat demuxer needs the last image once more to apply its duration.
  lines.push(`file '${basename(frames[runs.at(-1).index].file)}'`);
  const list = join(folder, "frames.ffconcat");
  writeFileSync(list, lines.join("\n") + "\n");
  const result = spawnSync(ffmpeg, [
    "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", list,
    "-vf", `fps=${fps},format=yuv444p`, "-frames:v", String(total), "-c:v", "libx264", "-preset", "slow",
    "-crf", "12", "-r", String(fps), "-f", "matroska", output,
  ], { stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error("ffmpeg could not assemble the screencast frames");
  }
  return { t0, total, used: runs.length };
}

function intervals(frames) {
  const gaps = frames.slice(1).map((frame, index) => frame.time - frames[index].time).sort((a, b) => a - b);
  return gaps.length ? { median: gaps[Math.floor(gaps.length / 2)], longest: gaps.at(-1) } : { median: 0, longest: 0 };
}

async function main() {
  if (!options.page || !options.output) {
    throw new Error("--page and --output are required");
  }
  const size = { width: Number(options.width), height: Number(options.height) };
  const timing = { hold: Number(options.hold), scroll: Number(options.scroll), tail: Number(options.tail) };
  const fps = Number(options.fps);
  const aliases = options.aliases ? JSON.parse(readFileSync(options.aliases, "utf8")) : [];
  const markers = options.markers
    ? readFileSync(options.markers, "utf8").split(/\r?\n/).map((line) => line.trim()).filter((line) => line && !line.startsWith("#"))
    : [];
  const browser = await chromium.launch({ executablePath: options.chromium });
  const folder = mkdtempSync(join(tmpdir(), "oslab-record-page-"));
  try {
    const context = await browser.newContext({ viewport: size, deviceScaleFactor: 1 });
    const page = await context.newPage();
    await page.goto(pathToFileURL(resolve(options.page)).href, { waitUntil: "load" });
    const replaced = await page.evaluate(replaceText, aliases);
    const remaining = await page.evaluate(findMarkers, markers);
    if (remaining.length) {
      throw new Error(`Private markers remain in the page text: ${remaining.map((index) => `#${index}`).join(", ")}`);
    }
    console.log(`Replaced text in ${replaced} text nodes; no private marker remains in the page text`);
    const { frames, end, distance } = await recordScroll(page, folder, size, timing);
    if (options.screenshot) {
      await page.screenshot({ path: options.screenshot, fullPage: true });
    }
    const first = readFileSync(frames[0].file);
    const width = first.readUInt32BE(16);
    const height = first.readUInt32BE(20);
    const { t0, total, used } = encode(frames, end, folder, resolve(options.output), fps, options.ffmpeg);
    const gaps = intervals(frames);
    const meta = {
      file: basename(options.output),
      page: basename(options.page),
      status: "complete",
      t0,
      width,
      height,
      fps,
      frames: total,
      seconds: Number((total / fps).toFixed(3)),
      hold_seconds: timing.hold,
      scroll_seconds: timing.scroll,
      tail_seconds: timing.tail,
      scroll_pixels: distance,
      screencast_frames: frames.length,
      screencast_median_interval: Number(gaps.median.toFixed(4)),
      screencast_longest_interval: Number(gaps.longest.toFixed(4)),
      replaced_text_nodes: replaced,
    };
    writeFileSync(resolve(options.output).replace(/\.[^.\\/]+$/, ".json"), JSON.stringify(meta, null, 2) + "\n");
    console.log(
      `Recorded ${meta.seconds} s at ${width}x${height} from ${frames.length} screencast frames (${used} used); ` +
        `median interval ${(gaps.median * 1000).toFixed(0)} ms, longest ${(gaps.longest * 1000).toFixed(0)} ms`,
    );
  } finally {
    await browser.close();
    rmSync(folder, { recursive: true, force: true });
  }
}

await main();

