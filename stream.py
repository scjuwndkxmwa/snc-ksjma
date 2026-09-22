import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@mo_3la/live"
YOUTUBE_STREAM_KEY = "p11k-zgfe-3j9c-ps6b-7tgu"
YOUTUBE_RTMP = f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",
    "--stream-segment-attempts", "3",
    "--stream-segment-timeout", "10",
    "--stream-timeout", "15",
    "--stdout",
    TIKTOK_URL,
    "best"
]

FFMPEG_CMD = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "warning",
    "-stats",
    "-thread_queue_size", "2048",
    "-avoid_negative_ts", "make_zero",
    "-copytb", "1",
    "-fflags", "+genpts+discardcorrupt",
    "-err_detect", "ignore_err",
    "-i", "-",
    "-map", "0:v:0",
    "-c:v", "copy",
    "-fps_mode", "passthrough",
    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",
    "-af", "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",
    "-flush_packets", "1",
    "-flvflags", "no_duration_filesize",
    "-f", "flv",
    YOUTUBE_RTMP
]

streamlink_process = None
ffmpeg_process = None
stopping = False

def cleanup():
    global streamlink_process, ffmpeg_process
    print("Cleaning up processes...")
    for proc, name in [(ffmpeg_process, "FFmpeg"), (streamlink_process, "Streamlink")]:
        if proc is not None:
            if proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except Exception:
                        pass
    ffmpeg_process = None
    streamlink_process = None

def signal_handler(sig, frame):
    global stopping
    stopping = True
    print("\nStopping script completely...")
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

print("Starting TikTok to YouTube Persistent Relay Loop...")

while not stopping:
    try:
        print("\n========================================")
        print("Checking for TikTok LIVE...")
        print("========================================\n")

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        streamlink_process.stdout.close()

        while not stopping:
            sl_code = streamlink_process.poll()
            ff_code = ffmpeg_process.poll()

            if sl_code is not None or ff_code is not None:
                print(f"\nStream ended or process exited (Streamlink: {sl_code}, FFmpeg: {ff_code})")
                break

            time.sleep(2)

    except Exception as e:
        print(f"\nUnexpected error in relay loop: {e}")

    finally:
        cleanup()

    if not stopping:
        print("\nWaiting 120 seconds before checking for the next LIVE...")
        time.sleep(120)
