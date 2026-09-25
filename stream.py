import os
import subprocess
import time
import signal
import sys

YOUTUBE_VIDEO_URL = "https://youtu.be/mtKF4rn6SLM"
YOUTUBE_STREAM_KEY = "r77y-h37m-x6xr-x0dj-0g6q"

YOUTUBE_RTMP_DESTINATION = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

YTDLP_CMD = [
    "yt-dlp",
    "-f", "b/bv*+ba",
    "--extractor-args", "youtube:player_client=mweb,tv",
    "--no-check-certificates",
    "-o", "-",
    YOUTUBE_VIDEO_URL
]

FFMPEG_CMD = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "warning",
    "-re",
    "-i", "pipe:0",
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

ytdlp_process = None
ffmpeg_process = None

def kill_forcefully(p):
    if p is not None:
        try:
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=2)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass

def cleanup():
    global ytdlp_process, ffmpeg_process
    kill_forcefully(ffmpeg_process)
    kill_forcefully(ytdlp_process)
    ytdlp_process = None
    ffmpeg_process = None

def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("[INFO] Starting continuous restream loop...")

while True:
    try:
        ytdlp_process = subprocess.Popen(
            YTDLP_CMD,
            stdout=subprocess.PIPE,
            stderr=sys.stderr
        )

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=ytdlp_process.stdout,
            stdout=sys.stdout,
            stderr=sys.stderr
        )

        ytdlp_process.stdout.close()
        ffmpeg_process.wait()

        print("[INFO] Stream ended or restarted. Re-linking in 5 seconds...")
        time.sleep(5)

    except Exception as e:
        print(f"[ERROR] Loop error: {e}")
        time.sleep(5)
    finally:
        cleanup()
