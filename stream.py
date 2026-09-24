import os
import subprocess
import time
import signal
import sys
import streamlink

TIKTOK_URL = "https://www.tiktok.com/@abdullahal3085/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/r77y-h37m-x6xr-x0dj-0g6q"

CHECK_INTERVAL_OFFLINE = 15

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",
    "--retry-streams", "0",
    "--retry-max", "0",
    "--stream-timeout", "10",
    "--stdout",
    TIKTOK_URL,
    "best"
]

FFMPEG_CMD = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "warning",
    "-stats",

    "-fflags", "+genpts+discardcorrupt+igndts",
    "-err_detect", "ignore_err",

    "-thread_queue_size", "2048",
    "-analyzeduration", "10000000",
    "-probesize", "10000000",
    "-i", "-",

    "-map", "0:v:0",
    "-c:v", "copy",

    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",
    "-af", "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

    "-fps_mode", "passthrough",
    "-flush_packets", "1",

    "-flvflags", "no_duration_filesize",

    "-f", "flv",
    YOUTUBE_RTMP
]

streamlink_process = None
ffmpeg_process = None


def stop_process(process):
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=1)
            except Exception:
                pass


def cleanup():
    global streamlink_process, ffmpeg_process
    stop_process(ffmpeg_process)
    stop_process(streamlink_process)
    streamlink_process = None
    ffmpeg_process = None


def signal_handler(sig, frame):
    cleanup()
    os._exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def is_tiktok_online():
    try:
        session = streamlink.Streamlink()
        streams = session.streams(TIKTOK_URL)
        return len(streams) > 0
    except Exception:
        return False


print("========================================")
print("TikTok Live Monitor & Restreamer")
print("========================================\n")

while True:
    cleanup()
    print(f"[{time.strftime('%H:%M:%S')}] Checking TikTok status...")

    if not is_tiktok_online():
        print(f"[{time.strftime('%H:%M:%S')}] Stream OFFLINE. Checking again in {CHECK_INTERVAL_OFFLINE}s...")
        time.sleep(CHECK_INTERVAL_OFFLINE)
        continue

    print(f"\n[{time.strftime('%H:%M:%S')}] TikTok LIVE Detected!")
    print(f"[{time.strftime('%H:%M:%S')}] Exiting process NOW to force Railway Restart...")
    
    os._exit(1)
