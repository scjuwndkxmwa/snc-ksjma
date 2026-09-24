import os
import subprocess
import time
import signal
import sys
import streamlink

TIKTOK_URL = "https://www.tiktok.com/@abdullahal3085/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/r77y-h37m-x6xr-x0dj-0g6q"

CHECK_INTERVAL_OFFLINE = 10

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "1",
    "--ringbuffer-size", "128M",
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

    "-fflags", "+genpts+discardcorrupt+igndts+nobuffer",
    "-flags", "+low_delay",
    "-err_detect", "ignore_err",

    "-thread_queue_size", "4096",
    "-analyzeduration", "1000000",
    "-probesize", "1000000",
    "-i", "-",

    "-map", "0:v:0",
    "-c:v", "copy",

    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

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
    sys.exit(0)


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
    try:
        cleanup()
        print(f"[{time.strftime('%H:%M:%S')}] Checking TikTok status...")

        if not is_tiktok_online():
            print(f"[{time.strftime('%H:%M:%S')}] Stream OFFLINE. Checking again in {CHECK_INTERVAL_OFFLINE}s...")
            time.sleep(CHECK_INTERVAL_OFFLINE)
            continue

        print(f"\n[{time.strftime('%H:%M:%S')}] TikTok LIVE Detected! Starting Pipe to YouTube...")
        
        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
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
        ffmpeg_process.wait()

        print(f"[{time.strftime('%H:%M:%S')}] Stream ended. Back to monitoring...")

    except KeyboardInterrupt:
        cleanup()
        break
    except Exception as e:
        print(f"[ERROR] {e}")
    finally:
        cleanup()

    time.sleep(CHECK_INTERVAL_OFFLINE)
