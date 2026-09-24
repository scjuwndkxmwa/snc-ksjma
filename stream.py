import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@abdullahal3085/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/3jdh-9t5f-u7tc-89qv-2zms"

CHECK_EVERY = 6
CHECK_WINDOW = 60
OFFLINE_SLEEP = 180

streamlink_process = None
ffmpeg_process = None

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

    "-thread_queue_size", "1024",
    "-i", "-",

    "-c:v", "libx264",
    "-preset", "ultrafast",
    "-tune", "zerolatency",
    "-g", "60",
    "-keyint_min", "60",
    "-sc_threshold", "0",
    "-pix_fmt", "yuv420p",

    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    "-flvflags", "no_duration_filesize",
    "-f", "flv",
    YOUTUBE_RTMP
]


def stop_process(process, name):
    if process and process.poll() is None:
        print(f"[SYSTEM] Stopping {name}...", flush=True)
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
    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")
    ffmpeg_process = None
    streamlink_process = None


def signal_handler(sig, frame):
    print("\n[SYSTEM] Shutdown requested.", flush=True)
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def is_live():
    cmd = [
        "streamlink",
        "--stream-url",
        TIKTOK_URL,
        "best"
    ]
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15
        )
        url = result.stdout.strip()
        if result.returncode == 0 and url.startswith("http"):
            return True
    except Exception:
        pass
    return False


def wait_for_live():
    print("\n========================================", flush=True)
    print("LIVE MONITOR STARTED", flush=True)
    print(f"Checking every {CHECK_EVERY} seconds for 60 seconds", flush=True)
    print("========================================", flush=True)

    start_time = time.time()

    while time.time() - start_time < CHECK_WINDOW:
        remaining = int(CHECK_WINDOW - (time.time() - start_time))
        print(f"[MONITOR] Checking TikTok... {remaining}s remaining", flush=True)

        if is_live():
            print("\n[MONITOR] TikTok LIVE detected!", flush=True)
            return True

        time.sleep(CHECK_EVERY)

    print("\n[MONITOR] No LIVE detected during the 60-second window.", flush=True)
    return False


def start_restream():
    global streamlink_process, ffmpeg_process

    cleanup()

    print("\n========================================", flush=True)
    print("TIKTOK LIVE DETECTED -> STARTING RESTREAM", flush=True)
    print("========================================\n", flush=True)

    streamlink_process = subprocess.Popen(
        STREAMLINK_CMD,
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=0
    )

    time.sleep(3)

    if streamlink_process.poll() is not None:
        print("[ERROR] Streamlink failed to start.", flush=True)
        cleanup()
        return False

    ffmpeg_process = subprocess.Popen(
        FFMPEG_CMD,
        stdin=streamlink_process.stdout,
        stdout=subprocess.DEVNULL,
        stderr=None,
        bufsize=0
    )

    streamlink_process.stdout.close()
    print("[SYSTEM] Restream is now running.", flush=True)
    return True


print("========================================", flush=True)
print("TikTok -> YouTube Auto Restreamer", flush=True)
print(f"Monitor: {CHECK_EVERY} seconds (10 times / min)", flush=True)
print("Search window: 60 seconds", flush=True)
print("Offline sleep: 180 seconds", flush=True)
print("========================================\n", flush=True)


while True:
    try:
        live_found = wait_for_live()

        if live_found:
            if not start_restream():
                print("[SYSTEM] Failed to start restream.", flush=True)
                time.sleep(5)
                continue

            while True:
                time.sleep(2)

                if streamlink_process is None or ffmpeg_process is None:
                    break

                if streamlink_process.poll() is not None or ffmpeg_process.poll() is not None:
                    print("\n[SYSTEM] TikTok LIVE ended or streaming process stopped.", flush=True)
                    cleanup()
                    print("[SYSTEM] Waiting 15s for YouTube to reset session...", flush=True)
                    time.sleep(15)
                    break

            print("[SYSTEM] Returning to LIVE monitor...", flush=True)
            continue

        cleanup()

        print("\n========================================", flush=True)
        print("TIKTOK OFFLINE -> SLEEPING FOR 3 MINUTES", flush=True)
        print("========================================\n", flush=True)

        time.sleep(OFFLINE_SLEEP)

        print("\n[SYSTEM] 3-minute sleep finished. Starting another LIVE search...", flush=True)

    except KeyboardInterrupt:
        print("\n[SYSTEM] Stopping...", flush=True)
        cleanup()
        break

    except Exception as e:
        print(f"\n[ERROR] {e}", flush=True)
        cleanup()
        print("[SYSTEM] Retrying monitor in 10 seconds...", flush=True)
        time.sleep(10)
