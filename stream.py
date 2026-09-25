import os
import subprocess
import time
import signal
import sys

YOUTUBE_VIDEO_URL = "https://youtu.be/mtKF4rn6SLM"
YOUTUBE_STREAM_KEY = "r77y-h37m-x6xr-x0dj-0g6q"
YOUTUBE_RTMP_DESTINATION = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

COOKIES_ENV = os.getenv("YOUTUBE_COOKIES")
COOKIES_PATH = "/tmp/cookies.txt"

if COOKIES_ENV:
    with open(COOKIES_PATH, "w") as f:
        f.write(COOKIES_ENV)

def get_direct_url():
    print("[INFO] Extracting Video URL via yt-dlp...")
    cmd = [
        "yt-dlp",
        "-g",
        "-f", "best[ext=mp4]/best",
        "--extractor-args", "youtube:player_client=ios,mweb,android",
        "--no-check-certificates",
        YOUTUBE_VIDEO_URL
    ]
    
    if COOKIES_ENV and os.path.exists(COOKIES_PATH):
        cmd.extend(["--cookies", COOKIES_PATH])

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode == 0 and result.stdout.strip():
        urls = result.stdout.strip().split('\n')
        return urls[0]
    else:
        print(f"[ERROR] yt-dlp failed: {result.stderr.strip()}")
        return None

ffmpeg_process = None

def cleanup():
    global ffmpeg_process
    if ffmpeg_process and ffmpeg_process.poll() is None:
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=2)
        except Exception:
            ffmpeg_process.kill()
    ffmpeg_process = None

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("[INFO] Starting Restreamer Service...")

while True:
    stream_url = get_direct_url()
    
    if not stream_url:
        print("[WARNING] Could not get stream link. Retrying in 10 seconds...")
        time.sleep(10)
        continue

    print("[INFO] Stream URL obtained! Launching FFmpeg...")

    FFMPEG_CMD = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-re",
        "-i", stream_url,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-maxrate", "3000k",
        "-bufsize", "6000k",
        "-pix_fmt", "yuv420p",
        "-g", "60",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-f", "flv",
        YOUTUBE_RTMP_DESTINATION
    ]

    try:
        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        ffmpeg_process.wait()
    except Exception as e:
        print(f"[ERROR] FFmpeg exception: {e}")
    finally:
        cleanup()

    print("[INFO] Stream session ended. Restarting in 5 seconds...")
    time.sleep(5)
