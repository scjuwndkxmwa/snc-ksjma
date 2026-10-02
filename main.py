import os
import sys
import time
import signal
import subprocess
import base64
import shutil
import threading

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
RECONNECT_DELAY = 5

ffmpeg_process = None
current_streamlink = None
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
    stop_streamlink()
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

STREAMLINK = find_executable("streamlink")
FFMPEG = find_executable("ffmpeg")

# ============================================================
# FFMPEG MANAGEMENT
# ============================================================

def start_ffmpeg():
    global ffmpeg_process
    if not FFMPEG:
        log("[ERROR] FFmpeg executable not found!")
        return False

    log("\n[SYSTEM] Initializing FFmpeg Process...")
    log(f"[SYSTEM] Target Resolution: {TARGET_WIDTH}x{TARGET_HEIGHT} @ {TARGET_FPS}fps")
    log("[SYSTEM] Target Destination: Restream RTMP")

    command = [
        FFMPEG,
        "-loglevel", "warning",
        "-re",
        "-i", "pipe:0",
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
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            bufsize=1024 * 1024
        )
        log("[SYSTEM] FFmpeg process running successfully.")
        return True
    except Exception as e:
        log(f"[ERROR] Failed to start FFmpeg: {e}")
        return False

def stop_ffmpeg():
    global ffmpeg_process
    if ffmpeg_process:
        try:
            ffmpeg_process.stdin.close()
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=3)
        except Exception:
            try:
                ffmpeg_process.kill()
            except Exception:
                pass
        ffmpeg_process = None

def stop_streamlink():
    global current_streamlink
    if current_streamlink:
        try:
            current_streamlink.terminate()
            current_streamlink.wait(timeout=3)
        except Exception:
            try:
                current_streamlink.kill()
            except Exception:
                pass
        current_streamlink = None

# ============================================================
# STREAMING LOGIC
# ============================================================

def stream_one_video(index, url, cookie_file):
    global current_streamlink
    if shutdown_requested:
        return False

    log("\n" + "=" * 60)
    log(f"[PLAYLIST] Playing Video {index}/{len(VIDEOS)}")
    log(f"[PLAYLIST] URL: {url}")
    log("=" * 60)

    cmd = [
        STREAMLINK,
        "--stdout",
        "--loglevel", "info",
        "--hls-live-edge", "3",
        "--stream-segment-threads", "2",
        "--stream-timeout", "60",
        "--retry-streams", "5",
        "--retry-max", "10"
    ]

    if cookie_file:
        cmd.extend(["--http-cookie", f"cookie-file={cookie_file}"])

    # اختيارات الجودة الصحيحة بدون خيارات غير مدعومة
    cmd.extend([url, "best,1080p,720p,worst"])

    try:
        current_streamlink = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1024 * 1024
        )
    except Exception as e:
        log(f"[ERROR] Failed to launch Streamlink: {e}")
        return False

    def read_stderr():
        try:
            for line in iter(current_streamlink.stderr.readline, b""):
                if shutdown_requested:
                    break
                msg = line.decode("utf-8", errors="ignore").strip()
                if msg:
                    log(f"[STREAMLINK] {msg}")
        except Exception:
            pass

    threading.Thread(target=read_stderr, daemon=True).start()

    bytes_sent = 0
    last_log_time = time.time()

    try:
        while not shutdown_requested:
            chunk = current_streamlink.stdout.read(64 * 1024)
            if not chunk:
                break

            if not ffmpeg_process or ffmpeg_process.poll() is not None:
                log("[ERROR] FFmpeg pipeline closed unexpectedly.")
                return False

            ffmpeg_process.stdin.write(chunk)
            ffmpeg_process.stdin.flush()

            bytes_sent += len(chunk)
            if time.time() - last_log_time > 30:
                mb_sent = round(bytes_sent / (1024 * 1024), 2)
                log(f"[STREAMING...] Active -> Sent ~{mb_sent} MB to Restream")
                last_log_time = time.time()

    except BrokenPipeError:
        log("[WARNING] Pipe broken, restarting stream pipeline...")
        return False
    except Exception as e:
        log(f"[ERROR] Data routing error: {e}")
        return False
    finally:
        stop_streamlink()

    log(f"[PLAYLIST] Finished Video {index}. Proceeding to next...")
    return True

# ============================================================
# MAIN LOOP
# ============================================================

def main():
    log("=" * 60)
    log("   YouTube 24/7 Relay -> Restream -> TikTok")
    log("=" * 60)

    if not STREAMLINK or not FFMPEG:
        log("[CRITICAL] Missing dependencies! Ensure streamlink & ffmpeg are installed.")
        sys.exit(1)

    cookie_file = prepare_cookies()
    cycle = 1

    while not shutdown_requested:
        log(f"\n[SYSTEM] STARTING PLAYLIST CYCLE #{cycle}")
        
        if not ffmpeg_process or ffmpeg_process.poll() is not None:
            if not start_ffmpeg():
                time.sleep(RECONNECT_DELAY)
                continue

        for idx, video_url in enumerate(VIDEOS, start=1):
            if shutdown_requested:
                break

            success = stream_one_video(idx, video_url, cookie_file)
            if not success and not shutdown_requested:
                log(f"[WARNING] Problem streaming video {idx}. Retrying in {RECONNECT_DELAY}s...")
                time.sleep(RECONNECT_DELAY)

        cycle += 1

    stop_streamlink()
    stop_ffmpeg()
    log("[SYSTEM] Relay process terminated gracefully.")

if __name__ == "__main__":
    main()
