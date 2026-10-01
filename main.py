import os
import sys
import time
import signal
import subprocess
import base64
import tempfile
import shutil

# ============================================================

# SETTINGS

# ============================================================

RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

RESTREAM_URL = (
"rtmp://live.restream.io/live/"
+ RESTREAM_STREAM_KEY
)

# 8 VIDEOS - EXACT ORDER

VIDEOS = [
"https://youtu.be/pNd2amw7ZAo",
"https://youtu.be/tFA3mH8kTJ0",
"https://youtu.be/UWzGxlZWimE",
"https://youtu.be/iCnj6QwmtwA",
"https://youtu.be/03cpj3iwNnY",
"https://youtu.be/RHnm5zuprrk",
"https://youtu.be/UfiLhGZ9J-A",
"https://youtu.be/6Pc97lWbxN8",
]

QUALITY = "best"

# Low memory settings

HLS_LIVE_EDGE = "3"
SEGMENT_THREADS = "2"

# Time between retry attempts

RECONNECT_DELAY = 5

# Cookie environment variable

COOKIES_B64 = os.getenv("YOUTUBE_COOKIES_B64", "").strip()

COOKIE_FILE = "/tmp/youtube_cookies.txt"

ffmpeg_process = None
current_streamlink = None
shutdown_requested = False

# ============================================================

# LOGGING

# ============================================================

def log(message):
print(message, flush=True)

# ============================================================

# SIGNAL HANDLING

# ============================================================

def shutdown_handler(signum, frame):
global shutdown_requested

```
if shutdown_requested:
    return

shutdown_requested = True

log("")
log("[SYSTEM] Shutdown requested...")

stop_streamlink()

if ffmpeg_process:
    try:
        ffmpeg_process.stdin.close()
    except Exception:
        pass

    try:
        ffmpeg_process.terminate()
    except Exception:
        pass
```

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ============================================================

# COOKIES

# ============================================================

def prepare_cookies():
if not COOKIES_B64:
log("[SYSTEM] YouTube Cookies: OFF")
return None

```
try:
    cookie_data = base64.b64decode(COOKIES_B64)

    with open(COOKIE_FILE, "wb") as f:
        f.write(cookie_data)

    log("[SYSTEM] YouTube Cookies: ON")
    log("[SYSTEM] Cookie file prepared.")

    return COOKIE_FILE

except Exception as e:
    log(f"[ERROR] Could not prepare cookies: {e}")
    return None
```

# ============================================================

# FIND STREAMLINK

# ============================================================

def find_executable(name):
path = shutil.which(name)

```
if path:
    return path

possible = [
    f"/usr/local/bin/{name}",
    f"/usr/bin/{name}",
    f"/opt/venv/bin/{name}",
]

for item in possible:
    if os.path.exists(item):
        return item

return None
```

STREAMLINK = find_executable("streamlink")
FFMPEG = find_executable("ffmpeg")

# ============================================================

# START PERSISTENT FFMPEG

# ============================================================

def start_ffmpeg():
global ffmpeg_process

```
if not FFMPEG:
    log("[ERROR] ffmpeg was not found.")
    return False

log("")
log("[SYSTEM] Starting persistent FFmpeg...")
log("[SYSTEM] This FFmpeg process stays alive for the whole playlist.")
log("[SYSTEM] No video files are saved to Railway.")
log("[SYSTEM] Video: COPY")
log("[SYSTEM] Audio: COPY")
log("[SYSTEM] Destination: Restream")
log("")

command = [
    FFMPEG,

    # Read MPEG-TS directly from Streamlink
    "-hide_banner",
    "-loglevel",
    "warning",

    "-fflags",
    "+genpts+discardcorrupt",

    "-f",
    "mpegts",

    "-i",
    "pipe:0",

    # Keep original codecs
    "-map",
    "0:v:0?",
    "-map",
    "0:a:0?",

    "-c:v",
    "copy",

    "-c:a",
    "copy",

    # Helps timestamp continuity between videos
    "-avoid_negative_ts",
    "make_zero",

    "-flvflags",
    "no_duration_filesize",

    # RTMP
    "-f",
    "flv",

    RESTREAM_URL,
]

try:
    ffmpeg_process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

    log("[SYSTEM] FFmpeg started.")
    log("[SYSTEM] FFmpeg -> Restream connected.")
    return True

except Exception as e:
    log(f"[ERROR] Could not start FFmpeg: {e}")
    return False
```

# ============================================================

# STOP STREAMLINK

# ============================================================

def stop_streamlink():
global current_streamlink

```
if current_streamlink:
    try:
        if current_streamlink.poll() is None:
            current_streamlink.terminate()

            try:
                current_streamlink.wait(timeout=3)
            except subprocess.TimeoutExpired:
                current_streamlink.kill()

    except Exception:
        pass

    current_streamlink = None
```

# ============================================================

# START ONE VIDEO

# ============================================================

def stream_one_video(index, url, cookie_file):
global current_streamlink

```
if shutdown_requested:
    return False

log("")
log("============================================================")
log(f"[PLAYLIST] Video {index}/{len(VIDEOS)}")
log(f"[PLAYLIST] {url}")
log("============================================================")

if not STREAMLINK:
    log("[ERROR] Streamlink was not found.")
    return False

command = [
    STREAMLINK,

    "--stdout",

    "--loglevel",
    "info",

    "--hls-live-edge",
    HLS_LIVE_EDGE,

    "--stream-segment-threads",
    SEGMENT_THREADS,

    "--stream-segment-attempts",
    "5",

    "--stream-segment-timeout",
    "20",

    "--stream-timeout",
    "60",

    "--http-timeout",
    "60",

    "--retry-streams",
    "5",

    "--retry-max",
    "10",
]

if cookie_file:
    command.extend([
        "--http-cookie",
        f"cookie-file={cookie_file}",
    ])

command.extend([
    url,
    QUALITY,
])

log("[SYSTEM] Starting Streamlink...")
log("[SYSTEM] Quality: BEST")
log("[SYSTEM] Output: direct pipe")
log("[SYSTEM] Disk download: OFF")

try:
    current_streamlink = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )

except Exception as e:
    log(f"[ERROR] Could not start Streamlink: {e}")
    return False

log("[SYSTEM] Streamlink started.")

# Forward Streamlink's stderr without blocking the video pipe
def read_errors():
    try:
        for raw in iter(current_streamlink.stderr.readline, b""):
            if shutdown_requested:
                break

            try:
                text = raw.decode("utf-8", errors="replace").strip()

                if text:
                    print(f"[STREAMLINK] {text}", flush=True)

            except Exception:
                pass

    except Exception:
        pass

import threading

error_thread = threading.Thread(
    target=read_errors,
    daemon=True,
)

error_thread.start()

try:
    while not shutdown_requested:

        data = current_streamlink.stdout.read(64 * 1024)

        if not data:
            break

        if not ffmpeg_process:
            break

        if ffmpeg_process.poll() is not None:
            log("[ERROR] FFmpeg stopped.")
            return False

        try:
            ffmpeg_process.stdin.write(data)
            ffmpeg_process.stdin.flush()

        except BrokenPipeError:
            log("[ERROR] FFmpeg pipe closed.")
            return False

        except Exception as e:
            log(f"[ERROR] Pipe error: {e}")
            return False

except Exception as e:
    log(f"[ERROR] Stream transfer error: {e}")
    return False

finally:
    stop_streamlink()

if shutdown_requested:
    return False

log("")
log(f"[PLAYLIST] Video {index} finished.")
log("[PLAYLIST] Moving directly to the next video...")

return True
```

# ============================================================

# CHECK FFMPEG

# ============================================================

def ffmpeg_alive():
if not ffmpeg_process:
return False

```
return ffmpeg_process.poll() is None
```

# ============================================================

# MAIN

# ============================================================

def main():

```
log("============================================================")
log("       YouTube Playlist 24/7 -> Restream -> TikTok")
log("============================================================")
log(f"Videos         : {len(VIDEOS)}")
log("Mode           : CONTINUOUS")
log("Disk download  : OFF")
log("Video          : COPY")
log("Video Encode   : OFF")
log("Audio          : COPY")
log("Quality        : BEST AVAILABLE")
log("Memory Mode    : LOW")
log("Auto-Reconnect : ON")
log("============================================================")

if not VIDEOS:
    log("[ERROR] Playlist is empty.")
    sys.exit(1)

if not STREAMLINK:
    log("[ERROR] Streamlink is not installed.")
    sys.exit(1)

if not FFMPEG:
    log("[ERROR] FFmpeg is not installed.")
    sys.exit(1)

cookie_file = prepare_cookies()

if not start_ffmpeg():
    sys.exit(1)

log("")
log("[SYSTEM] 24/7 playlist relay is starting...")
log("[SYSTEM] Nothing will be downloaded to disk.")
log("[SYSTEM] One persistent RTMP connection will be used.")
log("")

cycle = 1

while not shutdown_requested:

    log("")
    log("============================================================")
    log(f"[SYSTEM] PLAYLIST CYCLE #{cycle}")
    log("============================================================")

    for index, url in enumerate(VIDEOS, start=1):

        if shutdown_requested:
            break

        # If FFmpeg died, restart it before continuing
        if not ffmpeg_alive():

            log("")
            log("[WARNING] FFmpeg is not running.")
            log("[SYSTEM] Restarting FFmpeg...")

            if not start_ffmpeg():

                log(
                    f"[SYSTEM] FFmpeg restart failed. "
                    f"Retrying in {RECONNECT_DELAY} seconds..."
                )

                time.sleep(RECONNECT_DELAY)
                continue

        success = stream_one_video(
            index,
            url,
            cookie_file,
        )

        if shutdown_requested:
            break

        if not success:

            log("")
            log("[WARNING] Current video stopped unexpectedly.")
            log("[SYSTEM] Keeping the same RTMP session.")
            log(
                f"[SYSTEM] Retrying in {RECONNECT_DELAY} seconds..."
            )

            time.sleep(RECONNECT_DELAY)

            # Retry the same video
            continue

    cycle += 1

    log("")
    log("============================================================")
    log(f"[SYSTEM] Playlist cycle #{cycle - 1} completed.")
    log("[SYSTEM] Restarting from video #1.")
    log("============================================================")

# ========================================================
# CLEAN SHUTDOWN
# ========================================================

stop_streamlink()

if ffmpeg_process:

    try:
        ffmpeg_process.stdin.close()
    except Exception:
        pass

    try:
        ffmpeg_process.terminate()
    except Exception:
        pass

    try:
        ffmpeg_process.wait(timeout=5)
    except Exception:
        try:
            ffmpeg_process.kill()
        except Exception:
            pass

log("[SYSTEM] Relay stopped.")
```

if **name** == "**main**":
main()
