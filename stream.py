import os
import signal
import subprocess
import sys
import time

# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_RTMP = (
    "rtmp://live.restream.io/live/"
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

QUALITY = "best"

RECONNECT_DELAY = 5
STREAMLINK_TIMEOUT = 30

FFMPEG_AUDIO_BITRATE = "128k"

streamlink_process = None
ffmpeg_process = None
shutdown_requested = False


# ============================================================
# SIGNALS
# ============================================================

def signal_handler(signum, frame):
    global shutdown_requested
    shutdown_requested = True

    print()
    print("[SYSTEM] Shutdown requested...")

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    sys.exit(0)


signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)


# ============================================================
# PROCESS CONTROL
# ============================================================

def stop_process(process, name):
    if process is None:
        return

    if process.poll() is not None:
        return

    print(f"[SYSTEM] Stopping {name}...")

    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            print(f"[SYSTEM] Killing {name}...")
            process.kill()
        except Exception:
            pass


# ============================================================
# LOG
# ============================================================

def print_header():
    print("=" * 60)
    print("       YouTube LIVE -> Restream")
    print("=" * 60)
    print(f"YouTube        : {YOUTUBE_URL}")
    print("Destination     : Restream")
    print("Cookies         : OFF")
    print("Video           : COPY")
    print("Video Encode    : OFF")
    print("Crop            : OFF")
    print("Resize          : OFF")
    print("FPS Convert     : OFF")
    print(f"Audio           : AAC {FFMPEG_AUDIO_BITRATE}")
    print("Auto-Reconnect  : ON")
    print("============================================================")


# ============================================================
# STREAMLINK
# ============================================================

def start_streamlink():
    print("[SYSTEM] Starting Streamlink...")
    print("[SYSTEM] Cookies: OFF")
    print(f"[SYSTEM] Quality: {QUALITY.upper()}")
    print("[SYSTEM] Video source: COPY")
    print("[SYSTEM] Waiting for YouTube stream data...")

    cmd = [
        "streamlink",

        "--stdout",

        "--hls-live-edge", "3",

        "--hls-segment-attempts", "3",

        "--stream-segment-attempts", "3",

        "--stream-segment-timeout", "15",

        "--stream-timeout", str(STREAMLINK_TIMEOUT),

        "--retry-streams", "5",

        "--retry-max", "2",

        "--http-timeout", "20",

        "--http-header",
        "User-Agent=Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36",

        YOUTUBE_URL,
        QUALITY,
    ]

    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


# ============================================================
# FFMPEG
# ============================================================

def start_ffmpeg(streamlink_proc):
    print("[SYSTEM] Starting FFmpeg...")
    print("[SYSTEM] Video: COPY")
    print("[SYSTEM] Video Encode: OFF")
    print(f"[SYSTEM] Audio: AAC {FFMPEG_AUDIO_BITRATE}")
    print("[SYSTEM] Sending YouTube -> Restream.")

    cmd = [
        "ffmpeg",

        "-hide_banner",
        "-loglevel", "warning",
        "-stats",

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-thread_queue_size",
        "1024",

        "-i",
        "-",

        "-map",
        "0:v:0",

        "-map",
        "0:a:0?",

        # VIDEO COPY
        "-c:v",
        "copy",

        # AUDIO ENCODE
        "-c:a",
        "aac",

        "-b:a",
        FFMPEG_AUDIO_BITRATE,

        "-ar",
        "44100",

        "-ac",
        "2",

        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        "-avoid_negative_ts",
        "make_zero",

        "-f",
        "flv",

        RESTREAM_RTMP,
    ]

    return subprocess.Popen(
        cmd,
        stdin=streamlink_proc.stdout,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=0,
    )


# ============================================================
# PIPE LOG
# ============================================================

def read_streamlink_errors(process):
    if process is None or process.stderr is None:
        return []

    errors = []

    while True:
        try:
            line = process.stderr.readline()

            if not line:
                break

            text = line.decode(
                "utf-8",
                errors="replace"
            ).strip()

            if text:
                print(text)

                lower = text.lower()

                if (
                    "login_required" in lower
                    or "403" in lower
                    or "forbidden" in lower
                    or "failed to fetch segment" in lower
                    or "read timeout" in lower
                    or "could not open stream" in lower
                ):
                    errors.append(text)

        except Exception:
            break

    return errors


# ============================================================
# RUN SESSION
# ============================================================

def run_session():
    global streamlink_process
    global ffmpeg_process

    streamlink_process = None
    ffmpeg_process = None

    print()
    print("=" * 60)
    print("[SYSTEM] Starting relay session")
    print("=" * 60)

    try:
        streamlink_process = start_streamlink()

        print("[SYSTEM] Streamlink process started.")

        # Give Streamlink time to resolve YouTube
        time.sleep(3)

        if streamlink_process.poll() is not None:
            print(
                "[SYSTEM] Streamlink exited before media "
                "was available."
            )

            read_streamlink_errors(streamlink_process)

            return False

        # ----------------------------------------------------
        # IMPORTANT:
        # Don't claim RUNNING just because FFmpeg started.
        # ----------------------------------------------------

        print("[SYSTEM] Streamlink process is alive.")
        print("[SYSTEM] Starting FFmpeg pipeline...")

        ffmpeg_process = start_ffmpeg(streamlink_process)

        print("[SYSTEM] FFmpeg process started.")
        print("[SYSTEM] Waiting for actual media data...")

        # Give FFmpeg a moment
        time.sleep(3)

        if ffmpeg_process.poll() is not None:
            code = ffmpeg_process.returncode

            print(
                f"[SYSTEM] FFmpeg stopped immediately "
                f"(exit code: {code})."
            )

            return False

        print("[SYSTEM] Pipeline is active.")

        # ----------------------------------------------------
        # MONITOR
        # ----------------------------------------------------

        while not shutdown_requested:

            streamlink_code = streamlink_process.poll()
            ffmpeg_code = ffmpeg_process.poll()

            # Streamlink died
            if streamlink_code is not None:

                print(
                    f"[SYSTEM] Streamlink stopped "
                    f"(exit code: {streamlink_code})."
                )

                read_streamlink_errors(streamlink_process)

                stop_process(
                    ffmpeg_process,
                    "FFmpeg"
                )

                return False

            # FFmpeg died
            if ffmpeg_code is not None:

                print(
                    f"[SYSTEM] FFmpeg stopped "
                    f"(exit code: {ffmpeg_code})."
                )

                read_streamlink_errors(streamlink_process)

                stop_process(
                    streamlink_process,
                    "Streamlink"
                )

                return False

            # Read Streamlink stderr without declaring success
            # based only on process existence.
            if streamlink_process.stderr:

                try:
                    while True:
                        line = streamlink_process.stderr.readline()

                        if not line:
                            break

                        text = line.decode(
                            "utf-8",
                            errors="replace"
                        ).strip()

                        if text:
                            print(text)

                except Exception:
                    pass

            time.sleep(1)

        return False

    except Exception as exc:

        print(
            f"[ERROR] {type(exc).__name__}: {exc}"
        )

        return False

    finally:

        stop_process(
            ffmpeg_process,
            "FFmpeg"
        )

        stop_process(
            streamlink_process,
            "Streamlink"
        )

        ffmpeg_process = None
        streamlink_process = None


# ============================================================
# MAIN
# ============================================================

def main():

    print_header()

    print("[SYSTEM] Starting 24/7 relay...")
    print("=" * 60)

    while not shutdown_requested:

        print()
        print("=" * 60)
        print("[SYSTEM] Starting relay session")
        print("=" * 60)

        success = run_session()

        if shutdown_requested:
            break

        print()
        print("=" * 60)

        if success:
            print("[SYSTEM] Session ended.")
        else:
            print("[SYSTEM] Stream ended or connection lost.")

        print(
            f"[SYSTEM] Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )

        print("=" * 60)

        for _ in range(RECONNECT_DELAY):
            if shutdown_requested:
                break
            time.sleep(1)

    print("[SYSTEM] Relay stopped.")


# ============================================================
# ENTRY
# ============================================================

if __name__ == "__main__":
    main()
