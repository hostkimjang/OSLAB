"""Desktop QA for OBS Studio, VLC, Audacity and Shotcut."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import math
import struct
import uuid
import wave

from PIL import Image, ImageDraw, ImageFont

ROOT = r"C:\OSLabWall"
CLIP_WIDTH, CLIP_HEIGHT = 1280, 720
OBS_COLOR = (74, 211, 187)
SHOTCUT_INTRO = (104, 179, 233)
SHOTCUT_PROOF = (248, 154, 179)
CASES = {
    "03": {
        "title": "OBS Studio",
        "kicker": "RELEASE VIDEO / LOCAL RECORDING",
        "scenario": "Record a release evidence scene and check the playable H.264/AAC container.",
        "steps": ["Inspect the staged evidence scene", "Start a software-encoded recording", "Stop and verify the output"],
        "package": "obs",
    },
    "10": {
        "title": "VLC media player",
        "kicker": "PLAYBACK / SEEK QA",
        "scenario": "Play a fixed-length release clip, seek to the check point, and verify the player's actual position.",
        "steps": ["Load and play the local clip", "Jump to the 12-second marker", "Pause and verify duration"],
        "package": "vlc",
    },
    "11": {
        "title": "Audacity",
        "kicker": "AUDIO / EXPORT CONTRACT",
        "scenario": "Remove the two-second test slate and export an exact three-second mono WAV.",
        "steps": ["Import the raw audio fixture", "Remove the test slate", "Export WAV and check PCM"],
        "package": "audacity",
    },
    "15": {
        "title": "Shotcut",
        "kicker": "VIDEO / EDIT AND EXPORT",
        "scenario": "Export a verified two-shot edit and check the encoder output dimensions and duration.",
        "steps": ["Open the release timeline", "Review the second shot", "Export MP4 and check the result"],
        "package": "shotcut",
    },
}


def check(name, expected, observed):
    return {"name": name, "expected": expected, "observed": observed, "passed": expected == observed}


async def snapshot(d, name, delay=.6):
    await asyncio.sleep(delay)
    return await d.screenshot(name)


async def click_named(d, process, text, label, *, fallback=None,
                      preferred=("ControlType.Button", "ControlType.MenuItem")):
    controls = await d.inspect(process, text)
    frame, _ = await d.screenshot(label)
    usable = [
        row for row in controls
        if 0 <= row["x"] < frame["width"] and 0 <= row["y"] < frame["height"]
    ]
    if usable:
        candidate = min(usable, key=lambda row: (
            row.get("kind") not in preferred,
            row.get("width", 100) * row.get("height", 100),
        ))
        point = (candidate["x"], candidate["y"])
    elif fallback:
        point = (round(frame["width"] * fallback[0]), round(frame["height"] * fallback[1]))
    else:
        raise RuntimeError(f"The app did not expose the required {label} control")
    await d.click(frame, *point)
    return point


def slate(title, sequence, theme=OBS_COLOR, *, media_format="1280 × 720 / 30 fps", resolution="720p"):
    """Create an offline release slate without logos or production identifiers."""
    image = Image.new("RGB", (CLIP_WIDTH, CLIP_HEIGHT), "#101925")
    draw = ImageDraw.Draw(image)

    def font(size, family):
        try:
            return ImageFont.truetype(family, size)
        except OSError:
            return ImageFont.load_default()

    for y in range(20, CLIP_HEIGHT, 32):
        for x in range(20, CLIP_WIDTH, 32):
            draw.ellipse((x, y, x + 2, y + 2), fill="#26384b")
    draw.line((72, 117, 1208, 117), fill="#42566d", width=2)
    draw.text((72, 70), "WINDOWS RELEASE QA   /   MEDIA CONTRACT", fill=theme, font=font(25, "consola.ttf"))
    draw.rectangle((1040, 70, 1208, 104), fill=theme)
    draw.text((72, 180), title, fill="#eef4fa", font=font(80, "segoeuib.ttf"))
    draw.text((75, 290), f"Synthetic release fixture   |   {media_format}",
              fill="#bccde0", font=font(29, "segoeui.ttf"))
    for index, (x, name, value) in enumerate((
        (72, "BUILD", "RC-042"), (460, "RESOLUTION", resolution), (848, "SEQUENCE", sequence),
    )):
        draw.rounded_rectangle((x, 415, x + 350, 580), radius=13, fill="#1d3048", outline=theme, width=2)
        draw.text((x + 20, 446), name, fill=theme, font=font(20, "consola.ttf"))
        draw.text((x + 20, 487), value, fill="#ffffff", font=font(48, "segoeuib.ttf"))
        draw.rectangle((x + 20, 551, x + 40 + 55 * index, 555), fill=theme)
    draw.text((75, 644), "LOCAL FIXTURE  /  EXPECTED OUTPUT MEASURED IN THE GUEST",
              fill="#99abc0", font=font(20, "consola.ttf"))
    target = io.BytesIO()
    image.save(target, "PNG", optimize=True)
    return target.getvalue()


def pcm_fixture(seconds, rate, segment):
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setparams((1, 2, rate, 0, "NONE", "PCM"))
        values = []
        for sample in range(round(seconds * rate)):
            frequency, magnitude = segment(sample / rate)
            values.append(round(magnitude * math.sin(2 * math.pi * frequency * sample / rate)))
        output.writeframes(struct.pack(f"<{len(values)}h", *values))
    return target.getvalue()


async def ps_json(d, body):
    command = (
        "$json=(& {\n" + body + "\n} | ConvertTo-Json -Compress -Depth 8); "
        "[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($json))"
    )
    result = await d.ps(command)
    return json.loads(base64.b64decode(result.stdout.strip(), validate=True))


def boxes(contents):
    """Yield the complete, bounded MP4 boxes from a byte range."""
    start, size = 0, len(contents)
    while start + 8 <= size:
        length, identity = struct.unpack_from(">I4s", contents, start)
        header = 8
        if length == 1 and start + 16 <= size:
            length = struct.unpack_from(">Q", contents, start + 8)[0]
            header = 16
        elif length == 0:
            length = size - start
        if length < header or start + length > size:
            return
        yield identity, contents[start + header:start + length]
        start += length


def descendants(contents, *path):
    if not path:
        yield contents
        return
    for identity, child in boxes(contents):
        if identity == path[0]:
            yield from descendants(child, *path[1:])


def mp4_summary(head, tail):
    # OBS and Shotcut may put the movie box at the beginning or the end.
    movies = [part for key, part in boxes(head) if key == b"moov"]
    if not movies:
        for index in range(4, len(tail) - 4):
            if tail[index:index + 4] != b"moov":
                continue
            candidate = list(boxes(tail[index - 4:]))
            if candidate and candidate[0][0] == b"moov":
                movies.append(candidate[0][1])
    if head[4:8] != b"ftyp" or not movies:
        raise RuntimeError("The exported file does not contain a complete MP4 movie header")
    movie = movies[-1]
    header = next(descendants(movie, b"mvhd"))
    if header[0] == 0:
        scale, duration = struct.unpack_from(">II", header, 12)
    else:
        scale, duration = struct.unpack_from(">IQ", header, 20)
    tracks = []
    for track in descendants(movie, b"trak"):
        handler = next(descendants(track, b"mdia", b"hdlr"))
        sample_table = next(descendants(track, b"mdia", b"minf", b"stbl", b"stsd"))
        sample = list(boxes(sample_table[8:]))[0]
        sample_count = next(descendants(track, b"mdia", b"minf", b"stbl", b"stsz"), None)
        frames = struct.unpack_from(">I", sample_count, 8)[0] if sample_count is not None else 0
        kind = handler[8:12].decode("ascii")
        result = {"kind": kind, "codec": sample[0].decode("ascii"), "samples": frames}
        if kind == "vide":
            result["size"] = list(struct.unpack_from(">HH", sample[1], 24))
        tracks.append(result)
    return {"seconds": duration / scale, "tracks": tracks}


async def read_window(d, path, *, at_end=False, count=24576):
    body = rf"""
      $stream=[IO.File]::OpenRead('{path}')
      try {{
        if ({'$true' if at_end else '$false'}) {{ $stream.Position=[Math]::Max(0,$stream.Length-{count}) }}
        $buffer=New-Object byte[] {count}
        $n=$stream.Read($buffer,0,$buffer.Length)
        [Convert]::ToBase64String($buffer,0,$n)
      }} finally {{ $stream.Dispose() }}
    """
    return base64.b64decode((await d.ps(body)).stdout.strip(), validate=True)


def find_guest_decoder(name):
    return rf"""
      $decoder=(Get-Command {name}.exe -ErrorAction SilentlyContinue).Source
      if (!$decoder) {{
        $folders=@('{ROOT}\apps\shotcut', (Join-Path $env:ProgramFiles 'Shotcut'))
        $decoder=$folders | Where-Object {{ Test-Path -LiteralPath $_ }} |
          ForEach-Object {{ Get-ChildItem -LiteralPath $_ -File -Filter {name}.exe -Recurse -ErrorAction SilentlyContinue }} |
          Select-Object -First 1 -ExpandProperty FullName
      }}
    """


async def probe_video(d, path):
    read = rf"""
      if (!$decoder) {{ @{{available=$false}}; return }}
      $output = & $decoder -v error -count_packets -show_entries 'format=format_name,duration:stream=codec_type,codec_tag_string,width,height,nb_read_packets' -of json '{path}'
      if ($LASTEXITCODE -ne 0) {{ throw 'FFprobe could not read the finished MP4' }}
      @{{available=$true;details=(($output -join [Environment]::NewLine) | ConvertFrom-Json)}}
    """
    answer = await ps_json(d, find_guest_decoder("ffprobe") + read)
    if not answer["available"]:
        return None
    details = answer["details"]
    container = details["format"]
    if "mp4" not in container["format_name"].split(","):
        raise ValueError("The exported video is not MP4")
    tracks = []
    for stream in details["streams"]:
        kind = {"video": "vide", "audio": "soun"}.get(stream["codec_type"])
        if not kind:
            continue
        entry = {"kind": kind, "codec": stream["codec_tag_string"],
                 "samples": int(stream.get("nb_read_packets", 0))}
        if kind == "vide":
            entry["size"] = [stream["width"], stream["height"]]
        tracks.append(entry)
    return {"seconds": float(container["duration"]), "tracks": tracks}


async def check_recording(d, path, *, min_seconds, max_seconds, requires_audio):
    problem = None
    for _ in range(4):
        try:
            metadata = await probe_video(d, path)
            if metadata is None:
                head = await read_window(d, path)
                tail = await read_window(d, path, at_end=True)
                metadata = mp4_summary(head, tail)
            break
        except (RuntimeError, ValueError, struct.error, StopIteration) as error:
            problem = error
            await asyncio.sleep(1)
    else:
        raise RuntimeError(f"The exported video could not be verified: {problem}") from problem
    video = next((track for track in metadata["tracks"] if track["kind"] == "vide"), {})
    audio = next((track for track in metadata["tracks"] if track["kind"] == "soun"), {})
    return [
        check("Recording includes an H.264 video track", "avc1", video.get("codec")),
        check("Recording resolution matches the release contract", [1280, 720], video.get("size")),
        {**check(f"Container duration is within {min_seconds:g}–{max_seconds:g} seconds", True,
                 min_seconds <= metadata["seconds"] <= max_seconds),
         "measured_seconds": round(metadata["seconds"], 3)},
        check("Encoded video contains at least 60 timed samples", True, video.get("samples", 0) >= 60),
        *([check("Recording includes an AAC audio track", "mp4a", audio.get("codec"))] if requires_audio else []),
    ]


def optical_match(image, color):
    colors = image.convert("RGB").getdata()
    return sum(all(abs(value - target) <= 12 for value, target in zip(sample, color))
               for sample in colors) >= 180


async def decoded_color(d, path, seconds, target):
    """Check a patch from an encoded frame if the guest has the Shotcut decoder."""
    read = rf"""
      if (!$decoder) {{ @{{available=$false}}; return }}
      $target='{ROOT}\media-patch.rgb'
      & $decoder -hide_banner -nostdin -loglevel error -y -ss '{seconds:g}' -i '{path}' -frames:v 1 -vf 'crop=48:20:1080:74,scale=1:1:flags=area,format=rgb24' -f rawvideo $target
      if ($LASTEXITCODE -ne 0) {{ throw 'Decoder did not produce a video frame' }}
      @{{available=$true;color=@([IO.File]::ReadAllBytes($target) | ForEach-Object {{ [int]$_ }})}}
    """
    answer = await ps_json(d, find_guest_decoder("ffmpeg") + read)
    if not answer["available"]:
        return None
    color = answer["color"]
    return check(f"The frame at {seconds:g}s contains the expected release slate", True,
                 len(color) == 3 and all(abs(got - want) <= 15 for got, want in zip(color, target)))


OBS_INI = """[General]
Name=OSLab Release QA

[Output]
Mode=Simple
FilenameFormatting=oslab-local-evidence

[SimpleOutput]
FilePath=C:/OSLabWall
RecFormat=mp4
RecFormat2=mp4
RecQuality=Small
RecEncoder=x264
VBitrate=1500
ABitrate=128

[Video]
BaseCX=1280
BaseCY=720
OutputCX=1280
OutputCY=720
FPSType=0
FPSCommon=30

[Audio]
SampleRate=48000
ChannelSetup=Stereo
"""

OBS_USER = """[General]
FirstRun=true
EnableAutoUpdates=false

[Basic]
Profile=OSLab Release QA
ProfileDir=OSLab-Release-QA
SceneCollection=OSLab Release QA
SceneCollectionFile=OSLab-Release-QA

[BasicWindow]
PreviewEnabled=true
WarnBeforeStoppingRecord=false
"""


def obs_collection():
    scene_name, image_name, audio_name = "01 / Release evidence", "QA build slate", "Reference audio"
    identities = [str(uuid.uuid5(uuid.NAMESPACE_DNS, name)) for name in (scene_name, image_name, audio_name)]

    def source(name, plugin, settings, identity):
        return {"name": name, "id": plugin, "versioned_id": plugin, "uuid": identity,
                "enabled": True, "muted": False, "volume": 1.0, "mixers": 255, "flags": 0,
                "hotkeys": {}, "private_settings": {}, "settings": settings}

    def scene_item(name, identity, item_id):
        return {"name": name, "source_uuid": identity, "id": item_id, "visible": True,
                "locked": True, "align": 5, "rot": 0.0, "pos": {"x": 0.0, "y": 0.0},
                "scale": {"x": 1.0, "y": 1.0}, "bounds_type": 0}

    items = [scene_item(image_name, identities[1], 1), scene_item(audio_name, identities[2], 2)]
    scene = source(scene_name, "scene", {"id_counter": 2, "items": items}, identities[0])
    image = source(image_name, "image_source", {"file": ROOT + r"\obs-release-slate.png"}, identities[1])
    audio = source(audio_name, "ffmpeg_source",
                   {"is_local_file": True, "local_file": ROOT + r"\obs-reference.wav",
                    "looping": True, "restart_on_activate": True}, identities[2])
    return json.dumps({
        "name": "OSLab Release QA", "current_scene": scene_name, "current_program_scene": scene_name,
        "current_scene_uuid": identities[0], "current_program_scene_uuid": identities[0],
        "scene_order": [{"name": scene_name, "uuid": identities[0]}],
        "sources": [image, audio, scene], "transitions": [], "groups": [], "current_transition": "Cut",
        "transition_duration": 300, "quick_transitions": [], "saved_projectors": [],
    }).encode()


async def obs(d):
    for name, content in (
        ("obs-release-slate.png", slate("Capture validation", "01 / LOCAL")),
        ("obs-reference.wav", pcm_fixture(1, 16000, lambda _time: (440, 6000))),
        ("obs-scene.json", obs_collection()),
        ("obs-profile.ini", OBS_INI.encode()),
        ("obs-user.ini", OBS_USER.encode()),
    ):
        await d.upload(name, content)
    await d.task("OSLabObsFixture", rf"""
        $homePath=Join-Path $env:APPDATA 'obs-studio'
        $profile=Join-Path $homePath 'basic\profiles\OSLab-Release-QA'
        $scenes=Join-Path $homePath 'basic\scenes'
        New-Item -ItemType Directory -Path $profile,$scenes -Force | Out-Null
        Copy-Item -LiteralPath '{ROOT}\obs-profile.ini' -Destination (Join-Path $profile 'basic.ini') -Force
        Copy-Item -LiteralPath '{ROOT}\obs-user.ini' -Destination (Join-Path $homePath 'user.ini') -Force
        Copy-Item -LiteralPath '{ROOT}\obs-scene.json' -Destination (Join-Path $scenes 'OSLab-Release-QA.json') -Force
        [IO.File]::WriteAllText('{ROOT}\obs-fixture-ready','yes')
    """)
    await d.wait(rf"Test-Path -LiteralPath '{ROOT}\obs-fixture-ready'")
    await d.launch("obs", ["--disable-updater", "--disable-missing-files-check",
                           "--collection", "OSLab Release QA", "--profile", "OSLab Release QA"])
    await snapshot(d, "obs-launch", 6)
    await d.key("Win", "Up")
    # A busy guest can draw the preview a few seconds after the window appears.
    _, preview = await snapshot(d, "obs-preview", 1.5)
    for _ in range(10):
        if optical_match(preview, OBS_COLOR):
            break
        _, preview = await snapshot(d, "obs-preview", 1.2)
    _, preview = await snapshot(d, "stage-0", .2)
    process = r"^(obs64|obs32)$"
    record_button = await click_named(d, process, r"^Start Recording$|^녹화 시작$", "obs-start-button")
    await snapshot(d, "stage-1", 1)
    frame, _ = await snapshot(d, "stage-2", 4.8)
    await d.click(frame, *record_button)
    await d.wait(rf"Test-Path -LiteralPath '{ROOT}\oslab-local-evidence.mp4'", seconds=20)
    await snapshot(d, "stage-3", 1.2)
    output = ROOT + r"\oslab-local-evidence.mp4"
    results = await check_recording(d, output, min_seconds=5, max_seconds=18, requires_audio=True)
    results.append(check("OBS preview rendered the reference color patch", True, optical_match(preview, OBS_COLOR)))
    if frame_result := await decoded_color(d, output, 1, OBS_COLOR):
        results.append(frame_result)
    return results


def avi_fixture():
    """Generate a local motion-JPEG clip with a frame-accurate QA ruler."""
    width, height, fps, length = 480, 270, 2, 24
    frames = fps * length
    card = slate("Playback seek", "12 SEC", (244, 172, 91),
                 media_format=f"{width} × {height} / {fps} fps", resolution=f"{height}p")
    still = Image.open(io.BytesIO(card))
    still = still.resize((width, height), Image.Resampling.LANCZOS)

    def chunk(kind, data):
        return kind + struct.pack("<I", len(data)) + data + (b"\x00" if len(data) % 2 else b"")

    def collection(kind, data):
        return chunk(b"LIST", kind + data)

    sequence = []
    for index in range(frames):
        image = still.copy()
        draw = ImageDraw.Draw(image)
        draw.rectangle((27, 228, 453, 252), fill="#192c43")
        draw.rectangle((27, 248, 27 + round(426 * index / frames), 252), fill="#f2ae5e")
        draw.text((33, 231), f"PLAYHEAD  00:{index // fps:02d} / 00:{length:02d}", fill="#f8f2de")
        encoded = io.BytesIO()
        image.save(encoded, "JPEG", quality=68)
        sequence.append(encoded.getvalue())

    largest = max(map(len, sequence))
    avi_header = struct.pack("<14I", int(1_000_000 / fps), largest * fps, 0, 0x10, frames, 0, 1,
                             largest, width, height, 0, 0, 0, 0)
    stream_header = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"MJPG", 0, 0, 0, 0, 1, fps,
                                0, frames, largest, 0xffffffff, 0, 0, 0, width, height)
    bitmap = struct.pack("<IiiHH4sIiiII", 40, width, height, 1, 24, b"MJPG", width * height * 3,
                         0, 0, 0, 0)
    headers = collection(b"hdrl", chunk(b"avih", avi_header) +
                         collection(b"strl", chunk(b"strh", stream_header) + chunk(b"strf", bitmap)))
    movie, indices, position = [], [], 4
    for jpeg in sequence:
        packet = chunk(b"00dc", jpeg)
        movie.append(packet)
        indices.append(struct.pack("<4sIII", b"00dc", 0x10, position, len(jpeg)))
        position += len(packet)
    content = b"AVI " + headers + collection(b"movi", b"".join(movie)) + chunk(b"idx1", b"".join(indices))
    return b"RIFF" + struct.pack("<I", len(content)) + content


async def vlc_duration(d):
    return await ps_json(d, r"""
        function Get-VlcAnswer([string]$Command) {
            $conn=[Net.Sockets.TcpClient]::new('127.0.0.1',27641)
            try {
                $stream=$conn.GetStream()
                $stream.ReadTimeout=350
                $commandBytes=[Text.Encoding]::ASCII.GetBytes($Command+[char]10)
                $stream.Write($commandBytes,0,$commandBytes.Length)
                $receive=New-Object byte[] 1024
                $reply=[Text.StringBuilder]::new()
                do {
                    try { $count=$stream.Read($receive,0,$receive.Length) }
                    catch [IO.IOException] { break }
                    if ($count -gt 0) { [void]$reply.Append([Text.Encoding]::ASCII.GetString($receive,0,$count)) }
                } while ($count -gt 0 -and $reply.Length -lt 4096)
                $lines=@([regex]::Matches($reply.ToString(),'(?m)^\s*>?\s*(-?\d+)\s*\r?$'))
                if (!$lines.Count) { throw "VLC did not answer $Command" }
                [int]$lines[-1].Groups[1].Value
            } finally { $conn.Dispose() }
        }
        Get-VlcAnswer 'get_length'
    """)


async def vlc(d):
    basename = "RC-042-270p-QA-seek.avi"
    filename = ROOT + "\\" + basename
    await d.upload(basename, avi_fixture())
    await d.launch("vlc", ["--extraintf=rc", "--rc-host=127.0.0.1:27641", "--rc-quiet",
                           "--no-qt-privacy-ask", "--no-video-title-show", "--no-one-instance",
                           "--start-paused", filename])
    await d.wait("(Get-NetTCPConnection -LocalAddress '127.0.0.1' -LocalPort 27641 -State Listen "
                 "-ErrorAction SilentlyContinue | Where-Object OwningProcess -In (Get-Process vlc).Id)",
                 seconds=65)
    observed = None
    deadline = asyncio.get_running_loop().time() + 45
    while asyncio.get_running_loop().time() < deadline:
        try:
            observed = await vlc_duration(d)
            if observed == 24:
                break
        except RuntimeError:
            pass
        await asyncio.sleep(1)
    if observed != 24:
        raise RuntimeError("VLC did not load the 24-second release clip")
    await d.screenshot("vlc-loaded")
    await d.key("Shift")
    await asyncio.sleep(1.5)
    await d.key("Win", "Up")
    return await finish_vlc(d)


async def finish_vlc(d):
    def scale(frame, x, y):
        return round(frame["width"] * x / 1280), round(frame["height"] * y / 800)

    def position(image, y, left, right, color):
        y = round(image.height * y / 800)
        left, right = (round(image.width * x / 1280) for x in (left, right))
        pixels = image.convert("RGB").load()
        matching = [x for x in range(left, right + 1) if color(*pixels[x, y])]
        if len(matching) < 8:
            raise RuntimeError("VLC's displayed position could not be read")
        return round(24 * (max(matching) - left) / (right - left), 2)

    def seek_bar_position(image):
        return position(image, 708, 54, 1227, lambda r, g, b: b > g + 35 and g > r + 45)

    frame, _ = await snapshot(d, "stage-0")
    await d.click(frame, *scale(frame, 19, 735))
    _, early = await snapshot(d, "stage-1", 2.2)
    duration = await vlc_duration(d)
    frame, playing = await snapshot(d, "vlc-playing", 1.1)
    await d.click(frame, *scale(frame, 19, 735))
    frame, _ = await snapshot(d, "stage-2")
    await d.click(frame, *scale(frame, 654, 709))
    _, review = await snapshot(d, "stage-3", 1.1)
    _, hold = await snapshot(d, "vlc-review-hold", 1.1)

    first = seek_bar_position(early)
    later = seek_bar_position(playing)
    seek = seek_bar_position(review)
    frame_mark = position(review, 653, 123, 1157, lambda r, g, b: r > 200 and 130 < g < 210 and b < 125)
    held = seek_bar_position(hold)
    return [
        check("VLC reported the exact fixture duration", 24, duration),
        {"name": "VLC's timeline advanced during playback", "expected": "Second position > first position",
         "observed": f"{first} s to {later} s", "passed": later > first},
        {"name": "The UI seek reached the 12-second marker", "expected": "12 s ± 1 s",
         "observed": f"{seek} s in VLC, {frame_mark} s in the decoded frame",
         "passed": 11 <= seek <= 13 and 11 <= frame_mark <= 13},
        check("VLC's displayed position stayed paused at the review point", seek, held),
    ]


def pcm_summary(buffer):
    if buffer[:4] != b"RIFF" or buffer[8:12] != b"WAVE":
        raise ValueError("The export is not a RIFF WAVE file")
    offset, format_info, payload = 12, None, None
    while offset + 8 <= len(buffer):
        kind, length = struct.unpack_from("<4sI", buffer, offset)
        start = offset + 8
        if kind == b"fmt ":
            format_info = struct.unpack_from("<HHIIHH", buffer, start)
        elif kind == b"data":
            payload = start, length
            break
        offset = start + length + (length % 2)
    if not format_info or not payload:
        raise ValueError("The WAV file lacks its PCM metadata")
    direct, channels, rate, _bandwidth, align, bits = format_info
    if direct not in (1, 65534) or bits != 16 or not align:
        raise ValueError("Expected uncompressed signed 16-bit PCM")
    start, length = payload
    samples_to_read = min((len(buffer) - start) // 2, length // 2, rate // 8)
    samples = struct.unpack_from(f"<{samples_to_read}h", buffer, start)
    transitions = sum(a <= 0 < b for a, b in zip(samples, samples[1:]))
    return {"channels": channels, "bits": bits, "seconds": length / align / rate,
            "peak": max(abs(sample) for sample in samples),
            "frequency": transitions / samples_to_read * rate}


def audacity_wizard_pixel(image):
    width, height = image.size
    checks = ((450, 167), (900, 171), (370, 583), (904, 592))
    return all(min(image.getpixel((round(x * width / 1280), round(y * height / 800)))) >= 238
               for x, y in checks)


def audacity_slate_position(image):
    width, height = image.size
    scan = image.load()
    clip_y, wave_y = round(height * .24), round(height * .267)
    clip = [x for x in range(round(width * .23), round(width * .96))
            if all(abs(pixel - expected) <= 5
                   for pixel, expected in zip(scan[x, clip_y], (236, 204, 115)))]
    if len(clip) < round(width * .5):
        raise RuntimeError("Audacity did not fit the complete test clip into the timeline")
    coarse = round(clip[0] + (clip[-1] - clip[0]) * 2 / 5)
    limit = max(5, round(width * .008))
    for edge in range(coarse - limit, coarse + limit):
        if all(max(scan[x, wave_y]) <= 70 for x in range(edge, edge + 4)):
            return edge + 1, round(height * .28)
    raise RuntimeError("Audacity's fitted waveform does not show the expected pre-roll boundary")


async def audacity(d):
    # The pre-roll is a low guide tone. Only the 880 Hz review tone may survive.
    audio = pcm_fixture(5, 16000, lambda value: (220, 3200) if value < 2 else (880, 12400))
    input_name, output_name = "qa-raw-with-test-slate.wav", "qa-trimmed-tone.wav"
    await d.upload(input_name, audio)
    await d.launch("audacity", [ROOT + "\\" + input_name])
    await d.screenshot("audacity-wake")
    await d.key("Shift")
    return await finish_audacity(d, output_name)


async def finish_audacity(d, output_name):
    frame, image = await snapshot(d, "audacity-launch", 5)
    for page in range(5):
        if not audacity_wizard_pixel(image):
            break
        await d.click(frame, round(frame["width"] * 842 / 1280), round(frame["height"] * 573 / 800))
        frame, image = await snapshot(d, f"audacity-onboarding-{page + 1}", .6)
    if audacity_wizard_pixel(image):
        raise RuntimeError("Audacity's first-launch setup did not close")
    for attempt in range(3):
        # Maximize through the system menu, which works even when the window lost its snap state.
        await d.key("Alt", "Space")
        await asyncio.sleep(.3)
        await d.key("x")
        await d.key("Ctrl", "f")
        frame, image = await snapshot(d, "stage-0", 1 + attempt)
        try:
            x, y = audacity_slate_position(image)
            break
        except RuntimeError:
            if attempt == 2:
                raise
    await d.click(frame, x, y)
    await d.key("Shift", "j")
    await snapshot(d, "stage-1", .7)
    await d.key("Ctrl", "Delete")
    await snapshot(d, "stage-2", 1)
    await d.key("Ctrl", "Shift", "e")
    frame, image = await snapshot(d, "audacity-export-open", .8)
    process = r"^Audacity(?:4)?$"
    first_time = await d.inspect(process, r"^Export to computer$|^Export to Computer$|컴퓨터로 내보내기")
    button = image.getpixel((round(frame["width"] * 690 / 1280), round(frame["height"] * 541 / 800)))
    chooser_visible = button[2] > button[0] + 25 and button[2] > button[1] + 25 and min(button) > 150
    if first_time or chooser_visible:
        await click_named(d, process, r"^Export to computer$|컴퓨터로 내보내기", "audacity-export-computer",
                          fallback=(742 / 1280, 545 / 800))
        await asyncio.sleep(.55)
    edits = ("ControlType.Edit", "ControlType.Custom")
    await click_named(d, process, r"^FileNameFieldBox$|^File name(?::|$)|^파일 이름(?::|$)",
                      "audacity-filename", preferred=edits, fallback=(642 / 1280, 238 / 800))
    await d.key("Ctrl", "a")
    await d.paste(output_name)
    await click_named(d, process, r"^FolderFieldBox$|^Folder(?::|$)|^폴더(?::|$)",
                      "audacity-output-folder", preferred=edits, fallback=(647 / 1280, 276 / 800))
    await d.key("Ctrl", "a")
    await d.paste(ROOT)
    await click_named(d, process, r"^Export$|^내보내기$", "audacity-save-export",
                      fallback=(829 / 1280, 622 / 800))
    output = ROOT + "\\" + output_name
    await d.wait(rf"Test-Path -LiteralPath '{output}'", seconds=20)
    await snapshot(d, "stage-3", .5)
    summary = pcm_summary(await read_window(d, output))
    return [
        check("Export is mono signed 16-bit PCM", [1, 16], [summary["channels"], summary["bits"]]),
        check("The two-second slate was removed from the five-second import", True,
              abs(summary["seconds"] - 3.0) <= .015),
        check("Original low guide tone is absent at the new start", True, 860 <= summary["frequency"] <= 900),
        check("The retained test tone preserved its amplitude", True, 11900 <= summary["peak"] <= 12900),
    ]


SHOTCUT_MLT = """<?xml version="1.0" encoding="utf-8"?>
<mlt LC_NUMERIC="C" producer="tractor" version="7.24.0" title="OSLab Release QA">
  <profile description="HD 720p30" width="1280" height="720" progressive="1" sample_aspect_num="1"
           sample_aspect_den="1" display_aspect_num="16" display_aspect_den="9" frame_rate_num="30"
           frame_rate_den="1" colorspace="709"/>
  <producer id="black" in="0" out="119">
    <property name="resource">0</property>
    <property name="mlt_service">color</property>
  </producer>
  <playlist id="background">
    <entry producer="black" in="0" out="119"/>
  </playlist>
  <producer id="intro" in="0" out="59">
    <property name="resource">C:/OSLabWall/shotcut-intro.png</property>
    <property name="mlt_service">qimage</property>
    <property name="length">60</property>
  </producer>
  <producer id="proof" in="0" out="59">
    <property name="resource">C:/OSLabWall/shotcut-proof.png</property>
    <property name="mlt_service">qimage</property>
    <property name="length">60</property>
  </producer>
  <playlist id="release">
    <property name="shotcut:name">Release proof</property>
    <property name="shotcut:video">1</property>
    <entry producer="intro" in="0" out="59"/>
    <entry producer="proof" in="0" out="59"/>
  </playlist>
  <tractor id="tractor" shotcut="1" in="0" out="119">
    <property name="shotcut">1</property>
    <property name="shotcut:projectAudioChannels">2</property>
    <track producer="background"/>
    <track producer="release"/>
  </tractor>
</mlt>
"""


async def shotcut(d):
    await d.upload("shotcut-intro.png", slate("Packaging review", "01 / INTRO", SHOTCUT_INTRO))
    await d.upload("shotcut-proof.png", slate("Encoder validation", "02 / PROOF", SHOTCUT_PROOF))
    await d.upload("shotcut-release.mlt", SHOTCUT_MLT.encode())
    await d.launch("shotcut", [ROOT + r"\shotcut-release.mlt"])
    frame, preview = await snapshot(d, "shotcut-launch", 5)
    for attempt in range(6):
        if optical_match(preview, SHOTCUT_INTRO):
            break
        frame, preview = await snapshot(d, f"shotcut-init-{attempt}", 2)
    if not optical_match(preview, SHOTCUT_INTRO):
        raise RuntimeError("Shotcut did not load the release timeline")
    await d.key("Escape")
    await d.key("Alt", "Space")
    await asyncio.sleep(.3)
    await d.key("x")
    await d.key("Escape")
    frame, _ = await snapshot(d, "stage-0", 1.5)
    await d.click(frame, round(frame["width"] * 798 / 1280), round(frame["height"] * 354 / 800))
    _, proof = await snapshot(d, "stage-1", .7)
    if not optical_match(proof, SHOTCUT_PROOF):
        await d.key("Escape")
        await d.key("Home")
        await d.key("Space")
        _, proof = await snapshot(d, "shotcut-playing", 2.6)
        await d.key("Space")
        if not optical_match(proof, SHOTCUT_PROOF):
            raise RuntimeError("Shotcut did not play the proof segment")
        await snapshot(d, "stage-1", .2)
    await click_named(d, r"^shotcut$", r"^Export$|^Export Video$|^내보내기$|^출력$",
                      "shotcut-export-toolbar", fallback=(806 / 1280, 71 / 800))
    await snapshot(d, "stage-2", 1)
    await click_named(d, r"^shotcut$", r"^Export File$|^파일 내보내기$|^비디오/오디오 내보내기$",
                      "shotcut-export-file", fallback=(280 / 1280, 433 / 800))
    await snapshot(d, "shotcut-save-dialog", .7)
    output = ROOT + r"\qa-video-export.mp4"
    await d.key("Ctrl", "a")
    await d.paste(output)
    await d.key("Enter")
    await d.wait(rf"(Test-Path -LiteralPath '{output}') -and ((Get-Item -LiteralPath '{output}').Length -gt 16384)",
                 seconds=45)
    await snapshot(d, "stage-3", 2.5)
    results = await check_recording(d, output, min_seconds=3.95, max_seconds=4.10, requires_audio=False)
    for at, theme in ((1, SHOTCUT_INTRO), (3, SHOTCUT_PROOF)):
        if frame_result := await decoded_color(d, output, at, theme):
            results.append(frame_result)
    return results


async def execute(case_id, d):
    cases = {"03": obs, "10": vlc, "11": audacity, "15": shotcut}
    return await cases[str(case_id)](d)
