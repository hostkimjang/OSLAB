import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repositoryDirectory = fileURLToPath(new URL("../../../", import.meta.url));
const mediaDirectory = join(repositoryDirectory, "docs", "media");
const outputDirectory = join(repositoryDirectory, "output", "readme-media");
const dashboardPath = join(mediaDirectory, "oslab-dashboard-demo.mp4");
const liveLabPath = join(mediaDirectory, "oslab-live-lab.mp4");
const liveAttestationPath = join(mediaDirectory, "oslab-live-lab-attestation.json");
const outputMp4Path = join(mediaDirectory, "oslab-end-to-end-demo.mp4");
const outputGifPath = join(mediaDirectory, "oslab-end-to-end-demo.gif");
const outputPosterPath = join(mediaDirectory, "oslab-end-to-end-demo-poster.png");
const contactSheetPath = join(outputDirectory, "oslab-end-to-end-demo-contact-sheet.png");

const sourceContracts = {
  dashboard: {
    path: dashboardPath,
    sha256: "206a2ddaa0de2fa72454364073f618a4dc552c6722292a9e1629bcff3f1f9517",
    width: 1280,
    height: 800,
    minimumDuration: 27.4,
  },
  liveLab: {
    path: liveLabPath,
    sha256: "b92f184e1151a5b529e186bfd7c9af8513afb06d0906f7119ca1b2ae0dcff031",
    width: 1280,
    height: 720,
    minimumDuration: 24.8,
  },
};

const clips = {
  dashboardStart: { start: 0, end: 13.2 },
  liveLab: { start: 0, end: 22.4 },
  dashboardResult: { start: 22.6, end: 27.52 },
};
const crossfadeSeconds = 0.32;
const dashboardDuration = clips.dashboardStart.end - clips.dashboardStart.start;
const liveLabDuration = clips.liveLab.end - clips.liveLab.start;
const resultDuration = clips.dashboardResult.end - clips.dashboardResult.start;
const firstCrossfadeOffset = dashboardDuration - crossfadeSeconds;
const firstCompositionDuration = dashboardDuration + liveLabDuration - crossfadeSeconds;
const secondCrossfadeOffset = firstCompositionDuration - crossfadeSeconds;
const combinedDuration = firstCompositionDuration + resultDuration - crossfadeSeconds;
const fontPath = [
  process.env.OSLAB_README_FONT,
  "C:/Windows/Fonts/consolab.ttf",
  "C:/Windows/Fonts/segoeuib.ttf",
  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
  "/System/Library/Fonts/Menlo.ttc",
].find((candidate) => candidate && existsSync(candidate));
if (!fontPath) throw new Error("Set OSLAB_README_FONT to a readable TTF/TTC font for ffmpeg labels.");
const filterFontPath = fontPath.replaceAll("\\", "/").replaceAll(":", "\\:");
const dashboardDisclosureText = "ACTUAL DASHBOARD UI · FIXTURE DATA · NO PROXMOX CONTACTED";
const liveDisclosureText = "SEPARATELY CAPTURED LIVE LAB FOOTAGE · NOT ONE CONTINUOUS RUN";
const forbiddenCompositionMarkers = ["192.168.", "C:\\Users\\", "/Users/", "@pam"];
if (forbiddenCompositionMarkers.some((marker) => `${dashboardDisclosureText}\n${liveDisclosureText}`.includes(marker))) {
  throw new Error("Combined README disclosure text contains a forbidden private marker.");
}
const disclosureBar = "drawbox=x=0:y=0:w=iw:h=40:color=0x0d1114@0.96:t=fill";
const dashboardDisclosure = `drawtext=fontfile='${filterFontPath}':text='${dashboardDisclosureText}':fontcolor=white:fontsize=20:borderw=1:bordercolor=black@0.95:shadowx=1:shadowy=1:shadowcolor=black@0.9:x=(w-text_w)/2:y=(40-text_h)/2:enable='lt(t,${firstCrossfadeOffset})+gte(t,${firstCompositionDuration})'`;
const liveDisclosure = `drawtext=fontfile='${filterFontPath}':text='${liveDisclosureText}':fontcolor=white:fontsize=20:borderw=1:bordercolor=black@0.95:shadowx=1:shadowy=1:shadowcolor=black@0.9:x=(w-text_w)/2:y=(40-text_h)/2:enable='gte(t,${firstCrossfadeOffset})*lt(t,${firstCompositionDuration})'`;

const sha256 = (value) => createHash("sha256").update(value).digest("hex");
const run = (command, args, { capture = false } = {}) => {
  const result = spawnSync(command, args, {
    cwd: repositoryDirectory,
    encoding: capture ? "utf8" : undefined,
    stdio: capture ? ["ignore", "pipe", "pipe"] : "inherit",
    windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) {
    const details = capture ? `\n${result.stderr || result.stdout || ""}` : "";
    throw new Error(`${command} exited with status ${result.status}.${details}`);
  }
  return capture ? result.stdout : "";
};

const probe = (path) => JSON.parse(run("ffprobe", [
  "-v", "error",
  "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,pix_fmt",
  "-of", "json",
  path,
], { capture: true }));

await mkdir(mediaDirectory, { recursive: true });
await mkdir(outputDirectory, { recursive: true });

for (const [label, contract] of Object.entries(sourceContracts)) {
  const source = await readFile(contract.path);
  if (sha256(source) !== contract.sha256) {
    throw new Error(`${label} source does not match the reviewed SHA-256 contract.`);
  }
  const metadata = probe(contract.path);
  const video = metadata.streams?.find((stream) => stream.codec_type === "video");
  const audio = metadata.streams?.filter((stream) => stream.codec_type === "audio") || [];
  if (
    video?.codec_name !== "h264"
    || video?.width !== contract.width
    || video?.height !== contract.height
    || video?.pix_fmt !== "yuv420p"
    || Number(metadata.format?.duration || 0) < contract.minimumDuration
    || audio.length !== 0
  ) {
    throw new Error(`${label} source does not match the reviewed media contract.`);
  }
}

const liveAttestation = JSON.parse(await readFile(liveAttestationPath, "utf8"));
if (
  liveAttestation?.outputs?.["oslab-live-lab.mp4"]?.sha256 !== sourceContracts.liveLab.sha256
  || liveAttestation?.privacy?.manualPublicFrameReview !== true
  || liveAttestation?.privacy?.taskIdentifiersReplacedWithPublicAliases !== true
  || liveAttestation?.cleanup?.resourceAbsent !== true
) {
  throw new Error("Live lab source has not passed the required privacy, alias, and cleanup attestation gates.");
}

const filter = [
  `[0:v]trim=start=${clips.dashboardStart.start}:end=${clips.dashboardStart.end},setpts=PTS-STARTPTS,fps=25,settb=AVTB,setsar=1,format=yuv420p[dashboard_start]`,
  `[1:v]trim=start=${clips.liveLab.start}:end=${clips.liveLab.end},setpts=PTS-STARTPTS,scale=1280:720,fps=25,settb=AVTB,setsar=1,pad=1280:800:0:40:color=0x101214,format=yuv420p[live_lab]`,
  `[0:v]trim=start=${clips.dashboardResult.start}:end=${clips.dashboardResult.end},setpts=PTS-STARTPTS,fps=25,settb=AVTB,setsar=1,format=yuv420p[dashboard_result]`,
  `[dashboard_start][live_lab]xfade=transition=fade:duration=${crossfadeSeconds}:offset=${firstCrossfadeOffset}[first_join]`,
  `[first_join][dashboard_result]xfade=transition=fade:duration=${crossfadeSeconds}:offset=${secondCrossfadeOffset}[joined]`,
  `[joined]${disclosureBar},${dashboardDisclosure},${liveDisclosure},format=yuv420p[video]`,
].join(";");

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", dashboardPath,
  "-i", liveLabPath,
  "-filter_complex", filter,
  "-map", "[video]",
  "-an",
  "-c:v", "libx264",
  "-preset", "slow",
  "-crf", "20",
  "-pix_fmt", "yuv420p",
  "-movflags", "+faststart",
  outputMp4Path,
]);

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-ss", (combinedDuration - 0.7).toFixed(2),
  "-i", outputMp4Path,
  "-frames:v", "1",
  "-update", "1",
  outputPosterPath,
]);

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", outputMp4Path,
  "-vf", "fps=8,scale=800:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
  "-loop", "0",
  outputGifPath,
]);

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", outputMp4Path,
  "-vf", "fps=1/3.4,scale=480:-2,tile=4x3:padding=8:margin=8:color=black",
  "-frames:v", "1",
  contactSheetPath,
]);

const outputMetadata = probe(outputMp4Path);
const outputVideo = outputMetadata.streams?.find((stream) => stream.codec_type === "video");
const outputAudio = outputMetadata.streams?.filter((stream) => stream.codec_type === "audio") || [];
if (
  outputVideo?.codec_name !== "h264"
  || outputVideo?.width !== 1280
  || outputVideo?.height !== 800
  || outputVideo?.pix_fmt !== "yuv420p"
  || outputAudio.length !== 0
) {
  throw new Error("Combined README media does not match the required public output contract.");
}

for (const path of [outputMp4Path, outputGifPath, outputPosterPath]) {
  const contents = await readFile(path);
  console.log(`${relative(repositoryDirectory, path)} bytes=${contents.length} sha256=${sha256(contents)}`);
}
console.log(`Combined duration: ${Number(outputMetadata.format.duration).toFixed(2)}s`);
console.log(`Contact sheet: ${relative(repositoryDirectory, contactSheetPath)}`);
