import os
import sys
import time
import base64
import subprocess
from pathlib import Path

# ============================================================

# SETTINGS

# ============================================================

YOUTUBE_URL = "https://youtu.be/c3YZbShLyBM"

# Restream Stream Key

RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

RESTREAM_RTMP = (
"rtmp://live.restream.io/live/"
+ RESTREAM_STREAM_KEY
)

VIDEO_FILE = "/tmp/video.mp4"
COOKIES_FILE = "/tmp/youtube_cookies.txt"

# ============================================================

# PRINT

# ============================================================

def log(message):
print(message, flush=True)

# ============================================================

# YOUTUBE COOKIES

# ============================================================

def prepare_cookies():
cookies_b64 = os.getenv("YOUTUBE_COOKIES_B64")

```
if not cookies_b64:
    log("[SYSTEM] YouTube cookies: OFF")
    return None

try:
    data = base64.b64decode(cookies_b64)

    with open(COOKIES_FILE, "wb") as f:
        f.write(data)

    log("[SYSTEM] YouTube cookies: ON")
    return COOKIES_FILE

except Exception as e:
    log(f"[WARN] Failed to prepare cookies: {e}")
    return None
```

# ============================================================

# DOWNLOAD VIDEO

# ============================================================

def download_video():

```
if os.path.exists(VIDEO_FILE):
    try:
        if os.path.getsize(VIDEO_FILE) > 10 * 1024 * 1024:
            log("[SYSTEM] Existing video found.")
            return True
    except Exception:
        pass

if os.path.exists(VIDEO_FILE):
    try:
        os.remove(VIDEO_FILE)
    except Exception:
        pass

log("")
log("============================================================")
log("[SYSTEM] Downloading YouTube video")
log("============================================================")
log(f"[SOURCE] {YOUTUBE_URL}")
log("")

cookies = prepare_cookies()

# Prefer:
# 1. H.264 / AVC video
# 2. Up to 1080p
# 3. Up to 60 FPS
# 4. Best available audio
#
# Fallbacks are included if the preferred format isn't available.

format_selector = (
    "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
    "bestaudio[ext=m4a]/"
    "best[height<=1080][fps<=60][vcodec^=avc1]/"
    "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
    "bestaudio/"
    "best[height<=1080][fps<=60]/"
    "best"
)

command = [
    "yt-dlp",
    "--no-playlist",
    "--format",
    format_selector,

    # Merge into MP4 without re-encoding the video.
    "--merge-output-format",
    "mp4",

    "--output",
    VIDEO_FILE,

    "--no-part",
    "--no-overwrites",

    "--retries",
    "10",

    "--fragment-retries",
    "10",

    "--socket-timeout",
    "60",

    "--concurrent-fragments",
    "4",

    YOUTUBE_URL,
]

if cookies:
    command.insert(-1, "--cookies")
    command.insert(-1, cookies)

log("[SYSTEM] Selecting best compatible quality...")
log("[SYSTEM] Target: H.264 / up to 1080p / up to 60 FPS")
log("")

result = subprocess.run(command)

if result.returncode != 0:
    log("")
    log("[ERROR] yt-dlp failed.")
    return False

if not os.path.exists(VIDEO_FILE):
    log("[ERROR] Video file was not created.")
    return False

size = os.path.getsize(VIDEO_FILE)

if size < 10 * 1024 * 1024:
    log("[ERROR] Downloaded file is too small.")
    return False

log("")
log("[SYSTEM] Download completed successfully.")
log(f"[SYSTEM] File size: {size / (1024 * 1024):.2f} MB")

return True
```

# ============================================================

# CHECK VIDEO INFORMATION

# ============================================================

def show_video_info():

```
log("")
log("============================================================")
log("[SYSTEM] Checking downloaded video")
log("============================================================")

command = [
    "ffprobe",
    "-v",
    "error",
    "-select_streams",
    "v:0",
    "-show_entries",
    "stream=codec_name,width,height,r_frame_rate",
    "-of",
    "default=noprint_wrappers=1",
    VIDEO_FILE,
]

try:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.stdout.strip():
        log(result.stdout.strip())

except Exception as e:
    log(f"[WARN] ffprobe failed: {e}")
```

# ============================================================

# START STREAM

# ============================================================

def start_stream():

```
log("")
log("============================================================")
log("[SYSTEM] Starting 24/7 relay")
log("============================================================")
log("[SOURCE] YouTube")
log("[DESTINATION] Restream")
log("[VIDEO] COPY - NO VIDEO ENCODING")
log("[AUDIO] AAC 128k / 44100 Hz / Stereo")
log("[LOOP] INFINITE")
log("============================================================")
log("")

command = [
    "ffmpeg",

    # Read file at real-time speed.
    "-re",

    # Repeat the MP4 forever.
    "-stream_loop",
    "-1",

    "-i",
    VIDEO_FILE,

    # Video: copy exactly as downloaded.
    "-map",
    "0:v:0",
    "-c:v",
    "copy",

    # Audio: AAC for RTMP/Restream compatibility.
    "-map",
    "0:a:0?",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-ar",
    "44100",
    "-ac",
    "2",

    # Timestamp handling.
    "-fflags",
    "+genpts",

    "-avoid_negative_ts",
    "make_zero",

    # FLV / RTMP output.
    "-flvflags",
    "no_duration_filesize",

    "-f",
    "flv",

    RESTREAM_RTMP,
]

while True:

    try:

        log("[SYSTEM] Connecting to Restream...")

        process = subprocess.Popen(command)

        return_code = process.wait()

        log("")
        log(f"[SYSTEM] FFmpeg stopped. Exit code: {return_code}")

    except KeyboardInterrupt:

        log("[SYSTEM] Stopping...")
        try:
            process.terminate()
        except Exception:
            pass
        sys.exit(0)

    except Exception as e:

        log(f"[ERROR] FFmpeg error: {e}")

    log("[SYSTEM] Reconnecting in 10 seconds...")
    time.sleep(10)
```

# ============================================================

# MAIN

# ============================================================

def main():

```
log("")
log("============================================================")
log(" YouTube -> Restream 24/7")
log("============================================================")
log("[SYSTEM] Single video infinite loop")
log("[SYSTEM] Maximum compatible quality")
log("============================================================")

if not download_video():
    log("[FATAL] Could not download the YouTube video.")
    sys.exit(1)

show_video_info()

start_stream()
```

if **name** == "**main**":
main()
