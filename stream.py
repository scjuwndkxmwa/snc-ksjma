import os
import subprocess
import threading
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@.31342257/live"

YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/8yjs-eb3y-wt8s-y45e-ezsu"

COPY_AUDIO = False

STALL_TIMEOUT = 25
WATCHDOG_INTERVAL = 5
MAX_MUXING_QUEUE_SIZE = 4096

STREAMLINK_CMD = [
    "streamlink",
    "--hls-live-edge", "3",
    "--ringbuffer-size", "512M",
    "--retry-streams", "10",
    "--retry-max", "0",
    "--stream-segment-attempts", "10",
    "--stream-segment-timeout", "30",
    "--stream-timeout", "60",
    "--stdout",
    TIKTOK_URL,
    "best"
]


def build_ffmpeg_cmd(copy_audio: bool):
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel", "warning",
        "-stats",
        "-nostdin",

        "-threads", "1",

        # Rebuild timestamps from wall-clock arrival time -- the actual fix
        # for the non-monotonic DTS jumps from TikTok segment hiccups.
        # (+nobuffer does NOT fix this -- it only reduces latency.)
        "-use_wallclock_as_timestamps", "1",
        "-fflags", "+genpts+discardcorrupt+igndts",
        "-err_detect", "ignore_err",
        "-avoid_negative_ts", "make_zero",

        "-thread_queue_size", "4096",
        "-i", "-",

        "-map", "0:v:0",
        "-c:v", "copy",

        "-map", "0:a:0?",
    ]

    if copy_audio:
        cmd += ["-c:a", "copy", "-bsf:a", "aac_adtstoasc"]
    else:
        cmd += [
            "-c:a", "aac",
            "-aac_coder", "fast",
            "-b:a", "128k",
            "-ar", "44100",
            "-ac", "2",
            # Moderate tolerance: aggressive values (async=10000,
            # min_hard_comp=0.01) force a hard resync on every ~10ms of
            # drift, which sounds like constant audio cutting/skipping.
            "-af", "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",
        ]

    cmd += [
        "-fps_mode", "passthrough",
        "-flush_packets", "1",
        "-max_interleave_delta", "100000",

        "-max_muxing_queue_size", str(MAX_MUXING_QUEUE_SIZE),
        "-flvflags", "no_duration_filesize",

        "-f", "flv",
        YOUTUBE_RTMP
    ]

    return cmd


streamlink_process = None
ffmpeg_process = None

_last_progress_lock = threading.Lock()
_last_progress_time = [0.0]
_watchdog_stop = threading.Event()


def _mark_progress():
    with _last_progress_lock:
        _last_progress_time[0] = time.time()


def _seconds_since_progress():
    with _last_progress_lock:
        return time.time() - _last_progress_time[0]


def stderr_reader(proc):
    try:
        for raw_line in iter(proc.stderr.readline, b""):
            if not raw_line:
                break
            line = raw_line.decode(errors="replace").rstrip()
            if line:
                print(line, file=sys.stderr, flush=True)
                _mark_progress()
    except Exception:
        pass


def watchdog(proc):
    while not _watchdog_stop.is_set():
        if proc.poll() is not None:
            return
        if _seconds_since_progress() > STALL_TIMEOUT:
            print(
                f"\nNo progress for over {STALL_TIMEOUT}s — pipeline looks "
                f"frozen, forcing restart...",
                flush=True,
            )
            stop_process(proc)
            return
        _watchdog_stop.wait(WATCHDOG_INTERVAL)


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
    print("\nStopping processes...")
    stop_process(ffmpeg_process)
    stop_process(streamlink_process)
    streamlink_process = None
    ffmpeg_process = None


def signal_handler(sig, frame):
    print("\nStopped by user.")
    _watchdog_stop.set()
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

restart_delay = 1

while True:
    try:
        ffmpeg_cmd = build_ffmpeg_cmd(COPY_AUDIO)

        print("\n========================================")
        print("Starting TikTok -> YouTube stream...")
        print("Quality: BEST")
        print("Video: COPY (NO RE-ENCODE)")
        print(f"Audio: {'COPY' if COPY_AUDIO else 'AAC RE-ENCODE (moderate sync)'}")
        print(f"Stall watchdog: {STALL_TIMEOUT}s")
        print("========================================\n")

        _watchdog_stop.clear()
        _mark_progress()

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

        ffmpeg_process = subprocess.Popen(
            ffmpeg_cmd,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=subprocess.PIPE,
            bufsize=0
        )

        streamlink_process.stdout.close()

        reader_thread = threading.Thread(
            target=stderr_reader, args=(ffmpeg_process,), daemon=True
        )
        reader_thread.start()

        watchdog_thread = threading.Thread(
            target=watchdog, args=(ffmpeg_process,), daemon=True
        )
        watchdog_thread.start()

        ffmpeg_return = ffmpeg_process.wait()
        _watchdog_stop.set()

        if streamlink_process and streamlink_process.poll() is None:
            stop_process(streamlink_process)

        streamlink_return = (
            streamlink_process.poll()
            if streamlink_process
            else "N/A"
        )

        print("\n========================================")
        print("Stream stopped.")
        print(f"FFmpeg exit code: {ffmpeg_return}")
        print(f"Streamlink exit code: {streamlink_return}")
        print(f"Restarting in {restart_delay} second(s)...")
        print("========================================\n")

        restart_delay = 1

    except KeyboardInterrupt:
        _watchdog_stop.set()
        cleanup()
        break

    except BrokenPipeError:
        print("\nBroken pipe detected.")

    except OSError as e:
        print(f"\nOS error: {e}")

    except Exception as e:
        print(f"\nError: {e}")

    finally:
        _watchdog_stop.set()
        cleanup()

    time.sleep(restart_delay)
    restart_delay = min(restart_delay * 2, 30)
