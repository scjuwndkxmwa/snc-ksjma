import os
import sys
import time
import signal
import subprocess
import base64
import shutil

# ============================================================
# SETTINGS & CONFIGURATION
# ============================================================

RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
RESTREAM_URL = f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"

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

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
TARGET_FPS = 30
VIDEO_BITRATE = "3000k"
AUDIO_BITRATE = "128k"

COOKIES_B64 = os.getenv("YOUTUBE_COOKIES_B64", "").strip()
COOKIE_FILE = "/tmp/youtube_cookies.txt"
RECONNECT_DELAY = 10

ffmpeg_process = None
shutdown_requested = False

# ============================================================
# LOGGING & SIGNALS
# ============================================================

def log(message):
    print(message, flush=True)

def shutdown_handler(signum, frame):
    global shutdown_requested
    if shutdown_requested:
        return
    shutdown_requested = True
    log("\n[SYSTEM] Shutdown initiated...")
    stop_ffmpeg()

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# ============================================================
# UTILITIES
# ============================================================

def prepare_cookies():
    if not COOKIES_B64:
        log("[SYSTEM] YouTube Cookies: OFF")
        return None
    try:
        cookie_data = base64.b64decode(COOKIES_B64)
        with open(COOKIE_FILE, "wb") as f:
            f.write(cookie_data)
        log("[SYSTEM] YouTube Cookies: Loaded successfully.")
        return COOKIE_FILE
    except Exception as e:
        log(f"[ERROR] Failed to write cookies: {e}")
        return None

def find_executable(name):
    path = shutil.which(name)
    if path:
        return path
    for p in [f"/usr/local/bin/{name}", f"/usr/bin/{name}", f"/opt/venv/bin/{name}"]:
        if os.path.exists(p):
            return p
    return None

YTDLP = find_executable("yt-dlp")
FFMPEG = find_executable("ffmpeg")

# ============================================================
# DIRECT STREAM EXTRACTION (Android API Client Bypass)
# ============================================================

def get_direct_stream_url(youtube_url, cookie_file):
    if not YTDLP:
        log("[CRITICAL] yt-dlp executable not found!")
        return None

    log("[ENGINE] Extracting stream via Android Client API...")
    cmd = [
        YTDLP,
        "-g",
        "-f", "best[height<=720]/bestvideo[height<=720]+bestaudio/best",
        "--extractor-args", "youtube:player_client=android,ios",
        "--no-warnings",
        "--no-playlist"
    ]

    if cookie_file:
        cmd.extend(["--cookies", cookie_file])

    cmd.append(youtube_url)

    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
        if res.returncode == 0 and res.stdout.strip():
            urls = res.stdout.strip().split("\n")
            log("[ENGINE] Direct stream URL fetched successfully.")
            return urls[0]
        else:
            log(f"[ERROR] yt-dlp extraction failed: {res.stderr.strip()}")
    except Exception as e:
        log(f"[ERROR] Exception during yt-dlp extraction: {e}")

    return None

# ============================================================
# FFMPEG STREAMING PIPELINE
# ============================================================

def stream_video_with_ffmpeg(direct_url, index):
    global ffmpeg_process
    if shutdown_requested:
        return False

    log(f"[SYSTEM] Starting FFmpeg broadcast for Video #{index}...")

    command = [
        FFMPEG,
        "-loglevel", "warning",
        "-re",
        "-i", direct_url,
        "-vf", f"scale={TARGET_WIDTH}:{TARGET_HEIGHT}:force_original_aspect_ratio=decrease,pad={TARGET_WIDTH}:{TARGET_HEIGHT}:(ow-iw)/2:(oh-ih)/2,fps={TARGET_FPS}",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-tune", "zerolatency",
        "-b:v", VIDEO_BITRATE,
        "-maxrate", VIDEO_BITRATE,
        "-bufsize", "6000k",
        "-g", str(TARGET_FPS * 2),
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
        "-ar", "44100",
        "-ac", "2",
        "-f", "flv",
        RESTREAM_URL
    ]

    try:
        ffmpeg_process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        last_log_time = time.time()
        while not shutdown_requested:
            if ffmpeg_process.poll() is not None:
                break
            
            line = ffmpeg_process.stdout.readline()
            if not line and ffmpeg_process.poll() is not None:
                break

            if time.time() - last_log_time > 30:
                log(f"[BROADCASTING] Video #{index} active and streaming to Restream...")
                last_log_time = time.time()

        ffmpeg_process.wait()
        log(f"[PLAYLIST] Finished Video #{index}. Proceeding to next...")
        return True
    except Exception as e:
        log(f"[ERROR] FFmpeg process crashed: {e}")
        return False
    finally:
        stop_ffmpeg()

def stop_ffmpeg():
    global ffmpeg_process
    if ffmpeg_process:
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=3)
        except Exception:
            try:
                ffmpeg_process.kill()
            except Exception:
                pass
        ffmpeg_process = None

# ============================================================
# MAIN LOOP
# ============================================================

def main():
    log("=" * 60)
    log("   YouTube 24/7 Relay -> Restream -> TikTok")
    log("=" * 60)

    if not FFMPEG or not YTDLP:
        log("[CRITICAL] Missing dependencies! Ensure yt-dlp & ffmpeg are installed.")
        sys.exit(1)

    cookie_file = prepare_cookies()
    cycle = 1

    while not shutdown_requested:
        log(f"\n[SYSTEM] STARTING PLAYLIST CYCLE #{cycle}")

        for idx, video_url in enumerate(VIDEOS, start=1):
            if shutdown_requested:
                break

            log("\n" + "=" * 60)
            log(f"[PLAYLIST] Playing Video {idx}/{len(VIDEOS)}")
            log(f"[PLAYLIST] URL: {video_url}")
            log("=" * 60)

            direct_url = get_direct_stream_url(video_url, cookie_file)

            if direct_url:
                stream_video_with_ffmpeg(direct_url, idx)
            else:
                log(f"[WARNING] Skipping Video #{idx} due to URL extraction failure. Waiting {RECONNECT_DELAY}s...")
                time.sleep(RECONNECT_DELAY)

            time.sleep(2)

        cycle += 1

    log("[SYSTEM] Relay process terminated gracefully.")

if __name__ == "__main__":
    main()
