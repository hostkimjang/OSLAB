import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const repositoryDirectory = fileURLToPath(new URL("../../../", import.meta.url));
const mediaDirectory = join(repositoryDirectory, "docs", "media");
const reviewDirectory = join(repositoryDirectory, "output", "readme-media");
const dashboardPath = join(mediaDirectory, "oslab-dashboard-demo.mp4");
const workflowPath = join(mediaDirectory, "oslab-run-workflow.mp4");
const liveLabPath = join(mediaDirectory, "oslab-live-lab.mp4");
const liveAttestationPath = join(mediaDirectory, "oslab-live-lab-attestation.json");
const outputMp4Path = join(mediaDirectory, "oslab-step-by-step-demo.mp4");
const outputGifPath = join(mediaDirectory, "oslab-step-by-step-demo.gif");
const outputPosterPath = join(mediaDirectory, "oslab-step-by-step-demo-poster.png");
const outputAttestationPath = join(mediaDirectory, "oslab-step-by-step-demo-attestation.json");
const contactSheetPath = join(reviewDirectory, "oslab-step-by-step-demo-contact-sheet.png");

const sourceContracts = {
  dashboard: {
    path: dashboardPath,
    sha256: "206a2ddaa0de2fa72454364073f618a4dc552c6722292a9e1629bcff3f1f9517",
    bytes: 1725633,
    width: 1280,
    height: 800,
    minimumDuration: 27.4,
    provenance: "Actual Dashboard UI driven by fixed fixture data; external network access is blocked and Proxmox is not contacted.",
  },
  workflow: {
    path: workflowPath,
    sha256: "5a7b97ddd133c31125bfc779898b57e30d10b369af5c67c71a9f92afa577ac7a",
    bytes: 1589077,
    width: 1280,
    height: 720,
    minimumDuration: 22.9,
    provenance: "Deterministic ten-step explainer rendered from fixed data; it is not live execution and does not contact Proxmox.",
  },
  liveLab: {
    path: liveLabPath,
    sha256: "b92f184e1151a5b529e186bfd7c9af8513afb06d0906f7119ca1b2ae0dcff031",
    bytes: 1979438,
    width: 1280,
    height: 720,
    minimumDuration: 24.8,
    provenance: "Separately captured sanitized real-lab footage with passing privacy, public-alias, and cleanup attestation gates.",
  },
};

const disclosureText = {
  title: "EDITED WALKTHROUGH · FIXTURE UI + SEPARATE REAL LAB CAPTURE",
  dashboardStart: "FIXTURE DASHBOARD",
  workflow: "WORKFLOW EXPLAINER · FIXTURE DATA",
  liveLab: "REAL LAB · SEPARATE CAPTURE",
  dashboardResult: "FIXTURE RESULTS",
};
const segments = [
  { key: "title", generated: true, source: "generated-title-card", duration: 2.2, disclosure: "title", role: "Opening title that states the edited fixture and separate-capture provenance model" },
  { key: "dashboardStart", input: 0, source: "oslab-dashboard-demo.mp4", start: 2.92, end: 18.6, disclosure: "dashboardStart", caption: "SETUP  |  Select the scenario and launch the run", role: "Actual Dashboard scenario preparation and Run Launcher driven by fixed fixture data" },
  { key: "workflowClone", input: 1, source: "oslab-run-workflow.mp4", start: 0.18, end: 8.46, speed: 0.75, disclosure: "workflow", caption: "STEPS 1-4  |  Validate  >  Clone VM 9102  >  Boot", role: "Fixed-data explainer: request, preflight, clone, and boot orchestration" },
  { key: "liveClone", input: 2, source: "oslab-live-lab.mp4", start: 2.4, end: 7.6, disclosure: "liveLab", caption: "REAL LAB  |  Proxmox Clone and Start completed", role: "Separately captured real-lab Proxmox clone and boot evidence" },
  { key: "workflowGuest", input: 1, source: "oslab-run-workflow.mp4", start: 8.98, end: 15.06, speed: 0.75, disclosure: "workflow", caption: "STEPS 5-7  |  QGA  >  Fixtures  >  Artifact transfer", role: "Fixed-data explainer: QGA readiness, fixture preparation, and artifact transfer" },
  { key: "liveGuest", input: 2, source: "oslab-live-lab.mp4", start: 8.16, end: 13.12, disclosure: "liveLab", caption: "REAL LAB  |  Windows console and QGA trace", role: "Separately captured Windows console with evidence-derived QGA trace" },
  { key: "workflowTest", input: 1, source: "oslab-run-workflow.mp4", start: 15.58, end: 19.46, speed: 0.75, disclosure: "workflow", caption: "STEPS 8-9  |  Execute  >  Assert  >  Write evidence", role: "Fixed-data explainer: test execution, assertions, and evidence writing" },
  { key: "livePowerShell", input: 2, source: "oslab-live-lab.mp4", start: 13.68, end: 19.6, disclosure: "liveLab", caption: "REAL VM  |  PowerShell completed with exit code 0", role: "Separately captured actual guest PowerShell and verified evidence footage" },
  { key: "workflowCleanup", input: 1, source: "oslab-run-workflow.mp4", start: 20.02, end: 22.96, speed: 0.75, disclosure: "workflow", caption: "STEP 10  |  Destroy the clone and keep the evidence", role: "Fixed-data explainer: cleanup and VMID return" },
  { key: "liveSummary", input: 2, source: "oslab-live-lab.mp4", start: 20.2, end: 22.5, hold: 1, disclosure: "liveLab", caption: "VERIFIED  |  Test passed and capture VMs removed", role: "Separately captured real-lab summary with cleanup attestation inherited from the live source" },
  { key: "dashboardResult", input: 0, source: "oslab-dashboard-demo.mp4", start: 22.6, end: 27.52, hold: 1.5, disclosure: "dashboardResult", caption: "RESULTS  |  Inspect JSON, JUnit, HTML, and logs", role: "Dashboard Results Explorer driven by fixture data; not the result record from the real-lab footage" },
];
const crossfadeSeconds = 0.55;
const segmentDuration = (segment) => Number((
  segment.generated
    ? segment.duration
    : ((segment.end - segment.start) / (segment.speed || 1)) + (segment.hold || 0)
).toFixed(4));
const crossfadeOffsets = [];
let combinedDuration = segmentDuration(segments[0]);
for (const segment of segments.slice(1)) {
  crossfadeOffsets.push(Number((combinedDuration - crossfadeSeconds).toFixed(2)));
  combinedDuration = Number((combinedDuration + segmentDuration(segment) - crossfadeSeconds).toFixed(2));
}
if (Math.abs(combinedDuration - 66.42) > 0.02) {
  throw new Error(`Unexpected step-by-step EDL duration: ${combinedDuration.toFixed(2)}s.`);
}
const forbiddenCompositionMarkers = ["192.168.", "C:\\Users\\", "/Users/", "@pam", "root@"];
const introducedText = Object.values(disclosureText).join("\n");
if (forbiddenCompositionMarkers.some((marker) => introducedText.includes(marker))) {
  throw new Error("Step-by-step disclosure text contains a forbidden private marker.");
}

const fontPath = [
  process.env.OSLAB_README_FONT,
  "C:/Windows/Fonts/consolab.ttf",
  "C:/Windows/Fonts/segoeuib.ttf",
  "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
  "/System/Library/Fonts/Menlo.ttc",
].find((candidate) => candidate && existsSync(candidate));
if (!fontPath) throw new Error("Set OSLAB_README_FONT to a readable TTF/TTC font for ffmpeg labels.");
const filterFontPath = fontPath.replaceAll("\\", "/").replaceAll(":", "\\:");

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
  "-show_entries", "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,r_frame_rate",
  "-of", "json",
  path,
], { capture: true }));
const outputRecord = async (path) => {
  const contents = await readFile(path);
  return { bytes: contents.length, sha256: sha256(contents) };
};
const disclosure = (text, enable) => `drawtext=fontfile='${filterFontPath}':text='${text}':fontcolor=white:fontsize=18:borderw=1:bordercolor=black@0.95:shadowx=1:shadowy=1:shadowcolor=black@0.9:x=w-text_w-22:y=(40-text_h)/2:enable='${enable}'`;
const disclosureEnable = (key) => segments
  .map((segment, index) => {
    if (segment.disclosure !== key) return null;
    const start = index === 0 ? 0 : crossfadeOffsets[index - 1];
    const end = index === segments.length - 1 ? null : crossfadeOffsets[index];
    if (start === 0) return `lt(t,${end})`;
    if (end === null) return `gte(t,${start})`;
    return `gte(t,${start})*lt(t,${end})`;
  })
  .filter(Boolean)
  .join("+");
const segmentFilter = (segment, index) => {
  if (segment.generated) {
    return `color=c=0x0d1114:s=1280x800:r=25:d=${segment.duration},drawgrid=w=80:h=80:t=1:c=0x263139@0.35,drawbox=x=94:y=222:w=7:h=248:color=0x45d483:t=fill,drawtext=fontfile='${filterFontPath}':text='OSLAB':fontcolor=0x45d483:fontsize=24:x=130:y=224,drawtext=fontfile='${filterFontPath}':text='DASHBOARD TO':fontcolor=white:fontsize=58:x=130:y=278,drawtext=fontfile='${filterFontPath}':text='REVIEWABLE EVIDENCE':fontcolor=white:fontsize=58:x=130:y=346,drawtext=fontfile='${filterFontPath}':text='Setup  ·  Proxmox  ·  Windows  ·  Test  ·  Cleanup  ·  Results':fontcolor=0xb6c2ca:fontsize=22:x=132:y=438,fade=t=in:st=0:d=0.25,settb=AVTB,setsar=1,format=yuv420p[segment_${index}]`;
  }
  const contain = segment.input === 0 ? "" : "scale=1280:720,pad=1280:800:0:40:color=0x101214,";
  const playback = segment.speed ? `setpts=(PTS-STARTPTS)/${segment.speed},` : "setpts=PTS-STARTPTS,";
  const hold = segment.hold ? `tpad=stop_mode=clone:stop_duration=${segment.hold},` : "";
  return `[${segment.input}:v]trim=start=${segment.start}:end=${segment.end},${playback}${contain}fps=25,${hold}settb=AVTB,setsar=1,format=yuv420p[segment_${index}]`;
};
const crossfadeFilter = (_, index) => {
  const incomingIndex = index + 1;
  const previous = incomingIndex === 1 ? "segment_0" : `join_${incomingIndex - 1}`;
  const output = incomingIndex === segments.length - 1 ? "joined" : `join_${incomingIndex}`;
  return `[${previous}][segment_${incomingIndex}]xfade=transition=fadeblack:duration=${crossfadeSeconds}:offset=${crossfadeOffsets[index]}[${output}]`;
};
const chapter = (segment, index) => {
  if (!segment.caption) return null;
  const incomingStart = index === 0 ? 0 : crossfadeOffsets[index - 1];
  const start = Number((incomingStart + crossfadeSeconds).toFixed(2));
  const end = Number((Math.min(start + 2.65, incomingStart + segmentDuration(segment) - 0.25)).toFixed(2));
  return `drawtext=fontfile='${filterFontPath}':text='${segment.caption}':fontcolor=white:fontsize=27:box=1:boxcolor=0x0d1114@0.90:boxborderw=14:x=38:y=h-text_h-38:enable='gte(t,${start})*lt(t,${end})'`;
};

await Promise.all([
  mkdir(mediaDirectory, { recursive: true }),
  mkdir(reviewDirectory, { recursive: true }),
]);

for (const [label, contract] of Object.entries(sourceContracts)) {
  const source = await readFile(contract.path);
  if (source.length !== contract.bytes || sha256(source) !== contract.sha256) {
    throw new Error(`${label} source does not match the reviewed byte and SHA-256 contract.`);
  }
  const metadata = probe(contract.path);
  const video = metadata.streams?.find((stream) => stream.codec_type === "video");
  const audio = metadata.streams?.filter((stream) => stream.codec_type === "audio") || [];
  if (
    video?.codec_name !== "h264"
    || video?.width !== contract.width
    || video?.height !== contract.height
    || video?.pix_fmt !== "yuv420p"
    || video?.r_frame_rate !== "25/1"
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
  ...segments.map(segmentFilter),
  ...segments.slice(1).map(crossfadeFilter),
  `[joined]drawbox=x=0:y=0:w=iw:h=40:color=0x0d1114@0.96:t=fill,${disclosure(disclosureText.title, disclosureEnable("title"))},${disclosure(disclosureText.dashboardStart, disclosureEnable("dashboardStart"))},${disclosure(disclosureText.workflow, disclosureEnable("workflow"))},${disclosure(disclosureText.liveLab, disclosureEnable("liveLab"))},${disclosure(disclosureText.dashboardResult, disclosureEnable("dashboardResult"))},${segments.map(chapter).filter(Boolean).join(",")},format=yuv420p[video]`,
].join(";");

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", dashboardPath,
  "-i", workflowPath,
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
  "-i", outputMp4Path,
  "-ss", (combinedDuration - 0.7).toFixed(2),
  "-frames:v", "1",
  "-update", "1",
  outputPosterPath,
]);

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", outputMp4Path,
  "-vf", "fps=6,scale=720:-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=64:stats_mode=diff[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
  "-loop", "0",
  outputGifPath,
]);

run("ffmpeg", [
  "-hide_banner", "-loglevel", "error", "-y",
  "-i", outputMp4Path,
  "-vf", `fps=1/${(combinedDuration / 15.1).toFixed(4)}:start_time=0,scale=400:-2,tile=4x4:padding=8:margin=8:color=black`,
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
  || outputVideo?.r_frame_rate !== "25/1"
  || Math.abs(Number(outputMetadata.format?.duration || 0) - combinedDuration) > 0.08
  || outputAudio.length !== 0
) {
  throw new Error("Step-by-step README media does not match the required public output contract.");
}

const [mp4, gif, poster, contactSheet] = await Promise.all([
  outputRecord(outputMp4Path),
  outputRecord(outputGifPath),
  outputRecord(outputPosterPath),
  outputRecord(contactSheetPath),
]);
const attestation = {
  schemaVersion: 1,
  compositionType: "paced-dashboard-fixture-bookends-with-interleaved-workflow-explainer-and-separately-captured-real-lab",
  generatedAt: new Date().toISOString(),
  sources: {
    "oslab-dashboard-demo.mp4": { bytes: sourceContracts.dashboard.bytes, sha256: sourceContracts.dashboard.sha256, contract: sourceContracts.dashboard.provenance },
    "oslab-run-workflow.mp4": { bytes: sourceContracts.workflow.bytes, sha256: sourceContracts.workflow.sha256, contract: sourceContracts.workflow.provenance },
    "oslab-live-lab.mp4": { bytes: sourceContracts.liveLab.bytes, sha256: sourceContracts.liveLab.sha256, contract: sourceContracts.liveLab.provenance, attestation: "oslab-live-lab-attestation.json" },
  },
  provenanceModel: "A generated title and ten paced source segments cross-cut fixed-fixture UI and explanation with separately captured real-lab footage. Short source badges describe provenance; adjacency does not assert one continuous run or shared result record.",
  editDecisionList: segments.map((segment, index) => ({
    segment: segment.key,
    source: segment.source,
    sourceStartSeconds: segment.generated ? 0 : segment.start,
    sourceEndSeconds: segment.generated ? segment.duration : segment.end,
    playbackSpeed: segment.speed || 1,
    endHoldSeconds: segment.hold || 0,
    chapterCaption: segment.caption || null,
    incomingDisclosureStartsAtOutputSeconds: index === 0 ? 0 : crossfadeOffsets[index - 1],
    transitionToNextStartsAtOutputSeconds: index === segments.length - 1 ? null : crossfadeOffsets[index],
    role: segment.role,
    ...(segment.generated || segment.input === 0 ? {} : { layout: "1280x720 contained in 1280x800 with 40-pixel top and bottom padding" }),
    disclosure: disclosureText[segment.disclosure],
  })),
  transitions: {
    type: "fade-through-black",
    durationSeconds: crossfadeSeconds,
    count: segments.length - 1,
    disclosureOverlayAppliedAfterCrossfade: true,
    incomingSegmentDisclosureCoversEachTransition: true,
  },
  privacy: {
    sourceSha256AndByteLengthPinned: true,
    liveLabAttestationRequired: true,
    liveLabPublicAliasGateRequired: true,
    liveLabCleanupGateRequired: true,
    compositorReadsOnlyReviewedPublicMp4Sources: true,
    newPrivateCaptureInputsRead: false,
    introducedDisclosureTextMarkerGatePassed: true,
    forbiddenCompositionMarkers,
  },
  review: {
    contactSheetGenerated: true,
    contactSheetPath: "output/readme-media/oslab-step-by-step-demo-contact-sheet.png",
    contactSheetSha256: contactSheet.sha256,
    sampledFrameReview: false,
    fullFrameReview: false,
    reviewer: null,
    requiredBeforeReadmeSwap: true,
  },
  media: {
    durationSeconds: Number(outputMetadata.format.duration),
    width: 1280,
    height: 800,
    frameRate: 25,
    codec: "h264",
    pixelFormat: "yuv420p",
    audioStreams: 0,
    gifPreview: { width: 720, height: 450, frameRate: 6, maximumPaletteColors: 64 },
  },
  outputs: {
    "oslab-step-by-step-demo.mp4": mp4,
    "oslab-step-by-step-demo.gif": gif,
    "oslab-step-by-step-demo-poster.png": poster,
  },
};
await writeFile(outputAttestationPath, `${JSON.stringify(attestation, null, 2)}\n`, "utf8");

for (const [name, record] of Object.entries(attestation.outputs)) {
  console.log(`docs/media/${name} bytes=${record.bytes} sha256=${record.sha256}`);
}
console.log(`Combined duration: ${Number(outputMetadata.format.duration).toFixed(2)}s`);
console.log(`Contact sheet: ${relative(repositoryDirectory, contactSheetPath)} sha256=${contactSheet.sha256}`);
console.log(`Attestation: ${relative(repositoryDirectory, outputAttestationPath)} (fullFrameReview=false)`);
