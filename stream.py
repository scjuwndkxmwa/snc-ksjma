import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = os.environ.get("TIKTOK_URL", "https://www.tiktok.com/@abdullahal3085/live")
YOUTUBE_RTMP = os.environ.get("YOUTUBE_RTMP", "rtmp://a.rtmp.youtube.com/live2/r77y-h37m-x6xr-x0dj-0g6q")

streamlink_process = None
ffmpeg_process = None


def stop_process(process):
    if process and process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=5)
        except Exception:
            try:
                process.kill()
                process.wait(timeout=3)
            except Exception:
                pass


def cleanup():
    global streamlink_process, ffmpeg_process
    stop_process(ffmpeg_process)
    stop_process(streamlink_process)


def signal_handler(sig, frame):
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",
    "--retry-streams", "2",
    "--retry-max", "2",
    "--stream-segment-attempts", "5",
    "--stream-segment-timeout", "15",
    "--stream-timeout", "30",
    "--stdout",
    TIKTOK_URL,
    "best"
]

FFMPEG_CMD = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel", "warning",
    "-stats",

    "-dts_delta_threshold", "1",
    "-fflags", "+genpts+discardcorrupt",
    "-err_detect", "ignore_err",

    "-thread_queue_size", "1024",
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
    "-rtmp_live", "live",

    "-f", "flv",
    YOUTUBE_RTMP
]

try:
    print(f"[{time.strftime('%H:%M:%S')}] [STREAMER] Restreaming to YouTube...")

    streamlink_process = subprocess.Popen(
        STREAMLINK_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )

    time.sleep(2)

    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdin=streamlink_process.stdout,
        stdout=None,
        stderr=None,
        bufsize=0
    )

    streamlink_process.stdout.close()

    ffmpeg_return = ffmpeg_process.wait()
    print(f"[{time.strftime('%H:%M:%S')}] [STREAMER] Stream finished (Exit code: {ffmpeg_return}).")

except Exception as e:
    print(f"[{time.strftime('%H:%M:%S')}] [STREAMER ERROR] {e}")

finally:
    cleanup()
    sys.exit(0)
