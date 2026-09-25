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
    "-loglevel", "error",
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

try:
    ytdlp_process = subprocess.Popen(
        YTDLP_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL
    )

    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdin=ytdlp_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    ytdlp_process.stdout.close()
    ffmpeg_process.wait()

except Exception:
    pass
finally:
    cleanup()
