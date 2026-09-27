import os
import sys
import time
import signal
import subprocess


# ============================================================
# SETTINGS
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

RESTREAM_RTMP = "rtmp://live.restream.io/live"

RESTREAM_STREAM_KEY = (
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

RESTREAM_URL = f"{RESTREAM_RTMP}/{RESTREAM_STREAM_KEY}"


# ============================================================
# GLOBALS
# ============================================================

streamlink_process = None
ffmpeg_process = None

stopping = False


# ============================================================
# SIGNALS
# ============================================================

def handle_signal(signum, frame):
    global stopping

    if stopping:
        return

    stopping = True

    print("[SYSTEM] Shutdown requested...", flush=True)

    stop_processes()


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


# ============================================================
# STOP
# ============================================================

def stop_processes():

    global streamlink_process
    global ffmpeg_process

    # Stop FFmpeg first
    if ffmpeg_process is not None:

        try:
            if ffmpeg_process.poll() is None:
                print(
                    "[SYSTEM] Stopping FFmpeg...",
                    flush=True
                )

                ffmpeg_process.terminate()

                try:
                    ffmpeg_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(
                        "[SYSTEM] Killing FFmpeg...",
                        flush=True
                    )

                    ffmpeg_process.kill()

        except Exception:
            pass

        ffmpeg_process = None

    # Then Streamlink
    if streamlink_process is not None:

        try:
            if streamlink_process.poll() is None:
                print(
                    "[SYSTEM] Stopping Streamlink...",
                    flush=True
                )

                streamlink_process.terminate()

                try:
                    streamlink_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    print(
                        "[SYSTEM] Killing Streamlink...",
                        flush=True
                    )

                    streamlink_process.kill()

        except Exception:
            pass

        streamlink_process = None


# ============================================================
# STREAMLINK
# ============================================================

def start_streamlink():

    global streamlink_process

    print("[SYSTEM] Starting Streamlink...", flush=True)
    print("[SYSTEM] Cookies: OFF", flush=True)
    print("[SYSTEM] Quality: BEST", flush=True)
    print("[SYSTEM] Video source: COPY", flush=True)
    print(
        "[SYSTEM] Waiting for YouTube stream data...",
        flush=True
    )

    command = [
        "streamlink",

        # Do not load unknown config files
        "--no-config",

        # Current valid Streamlink option
        "--auto-version-check",
        "no",

        # HLS
        "--hls-live-edge",
        "2",

        # Output buffer
        "--ringbuffer-size",
        "64M",

        # Keep looking for the live stream
        "--retry-streams",
        "10",

        # 0 = retry indefinitely
        "--retry-max",
        "0",

        # Retry opening HLS segments
        "--stream-segment-attempts",
        "10",

        "--stream-segment-timeout",
        "30",

        # IMPORTANT:
        # Raw stream data goes to stdout
        "--stdout",

        YOUTUBE_URL,
        "best",
    ]

    try:

        streamlink_process = subprocess.Popen(
            command,

            stdin=subprocess.DEVNULL,

            stdout=subprocess.PIPE,

            stderr=None,

            bufsize=0
        )

    except Exception as e:

        print(
            f"[ERROR] Failed to start Streamlink: {e}",
            flush=True
        )

        streamlink_process = None

        return False

    return True


# ============================================================
# FFMPEG
# ============================================================

def start_ffmpeg():

    global ffmpeg_process

    if streamlink_process is None:
        return False

    if streamlink_process.stdout is None:
        return False

    print("[SYSTEM] Starting FFmpeg...", flush=True)
    print("[SYSTEM] Video: COPY", flush=True)
    print("[SYSTEM] Video Encode: OFF", flush=True)
    print("[SYSTEM] Audio: AAC 128k", flush=True)

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # Input from Streamlink
        "-i",
        "-",

        # Timestamp handling
        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        "-map",
        "0:a:0?",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-ac",
        "2",

        "-af",
        "aresample=async=1000:first_pts=0",

        # ----------------------------------------------------
        # RTMP
        # ----------------------------------------------------

        "-f",
        "flv",

        RESTREAM_URL,
    ]

    try:

        ffmpeg_process = subprocess.Popen(
            command,

            # Streamlink -> FFmpeg
            stdin=streamlink_process.stdout,

            stdout=subprocess.DEVNULL,

            stderr=None,

            bufsize=0
        )

    except Exception as e:

        print(
            f"[ERROR] Failed to start FFmpeg: {e}",
            flush=True
        )

        ffmpeg_process = None

        return False

    return True


# ============================================================
# RUN ONE SESSION
# ============================================================

def run_session():

    global streamlink_process
    global ffmpeg_process

    streamlink_process = None
    ffmpeg_process = None

    print("", flush=True)
    print(
        "============================================================",
        flush=True
    )
    print(
        "[SYSTEM] Starting relay session",
        flush=True
    )
    print(
        "============================================================",
        flush=True
    )

    # --------------------------------------------------------
    # START STREAMLINK
    # --------------------------------------------------------

    if not start_streamlink():
        return False

    time.sleep(2)

    if stopping:
        return False

    if streamlink_process is None:
        return False

    if streamlink_process.poll() is not None:

        print(
            "[SYSTEM] Streamlink exited before opening YouTube.",
            flush=True
        )

        return False

    print(
        "[SYSTEM] Streamlink process is alive.",
        flush=True
    )

    # --------------------------------------------------------
    # START FFMPEG
    # --------------------------------------------------------

    if not start_ffmpeg():
        return False

    print(
        "[SYSTEM] FFmpeg is connected to Streamlink.",
        flush=True
    )

    print(
        "[SYSTEM] Waiting for actual media data...",
        flush=True
    )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # Do NOT print RUNNING immediately.
    #
    # Wait until both processes remain alive.
    # --------------------------------------------------------

    start_time = time.time()

    running_printed = False

    while not stopping:

        # Streamlink stopped
        if streamlink_process is not None:

            streamlink_code = streamlink_process.poll()

            if streamlink_code is not None:

                print(
                    f"[SYSTEM] Streamlink stopped "
                    f"(exit code: {streamlink_code}).",
                    flush=True
                )

                return False

        # FFmpeg stopped
        if ffmpeg_process is not None:

            ffmpeg_code = ffmpeg_process.poll()

            if ffmpeg_code is not None:

                print(
                    f"[SYSTEM] FFmpeg stopped "
                    f"(exit code: {ffmpeg_code}).",
                    flush=True
                )

                return False

        # After both processes have survived for 5 seconds,
        # consider the pipeline established.
        if not running_printed:

            if time.time() - start_time >= 5:

                print(
                    "[SYSTEM] Stream is RUNNING.",
                    flush=True
                )

                print(
                    "[SYSTEM] Sending YouTube -> Restream.",
                    flush=True
                )

                running_printed = True

        time.sleep(1)

    return False


# ============================================================
# MAIN 24/7 LOOP
# ============================================================

def main():

    print(
        "============================================================",
        flush=True
    )

    print(
        "       YouTube 24/7 -> Restream -> TikTok",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    print(
        f"YouTube        : {YOUTUBE_URL}",
        flush=True
    )

    print(
        "Destination    : Restream",
        flush=True
    )

    print(
        "Cookies        : OFF",
        flush=True
    )

    print(
        "Video          : COPY",
        flush=True
    )

    print(
        "Video Encode   : OFF",
        flush=True
    )

    print(
        "Crop           : OFF",
        flush=True
    )

    print(
        "Resize         : OFF",
        flush=True
    )

    print(
        "FPS Convert    : OFF",
        flush=True
    )

    print(
        "Audio          : AAC 128k",
        flush=True
    )

    print(
        "Auto-Reconnect : ON",
        flush=True
    )

    print(
        "Status         : STARTING",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    print(
        "[SYSTEM] Starting 24/7 relay...",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    while not stopping:

        try:

            run_session()

        except Exception as e:

            print(
                f"[ERROR] Relay session error: {e}",
                flush=True
            )

        if stopping:
            break

        # ----------------------------------------------------
        # CLEANUP
        # ----------------------------------------------------

        print(
            "[SYSTEM] Cleaning up failed session...",
            flush=True
        )

        stop_processes()

        # ----------------------------------------------------
        # RECONNECT
        # ----------------------------------------------------

        print(
            "============================================================",
            flush=True
        )

        print(
            "[SYSTEM] Reconnecting in 5 seconds...",
            flush=True
        )

        print(
            "============================================================",
            flush=True
        )

        for _ in range(5):

            if stopping:
                break

            time.sleep(1)

    stop_processes()

    print(
        "[SYSTEM] Relay stopped.",
        flush=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
