import os
import sys
import time
import signal
import subprocess


# ============================================================
# CONFIGURATION
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

# Restream stream key
RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

# Restream ingest
RESTREAM_RTMP = f"rtmp://live.restream.io/live/{RESTREAM_STREAM_KEY}"


# ============================================================
# RELAY SETTINGS
# ============================================================

RESTART_DELAY = 5

# Streamlink quality
STREAM_QUALITY = "best"

# Keep a small amount of latency while avoiding excessive RAM use
RINGBUFFER_SIZE = "64M"

# HLS settings
HLS_LIVE_EDGE = "3"

# Segment retry settings
SEGMENT_ATTEMPTS = "10"
SEGMENT_TIMEOUT = "20"

# Stream read timeout
STREAM_TIMEOUT = "60"

# Playlist reload attempts
PLAYLIST_RELOAD_ATTEMPTS = "10"


# ============================================================
# GLOBAL PROCESSES
# ============================================================

streamlink_process = None
ffmpeg_process = None

shutdown_requested = False


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(message, flush=True)


# ============================================================
# PROCESS CLEANUP
# ============================================================

def stop_process(process, name, timeout=5):
    if process is None:
        return

    try:
        if process.poll() is None:
            log(f"[SYSTEM] Stopping {name}...")

            try:
                process.terminate()
            except Exception:
                pass

            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                log(f"[SYSTEM] Killing {name}...")

                try:
                    process.kill()
                except Exception:
                    pass

                try:
                    process.wait(timeout=3)
                except Exception:
                    pass

    except Exception as e:
        log(f"[SYSTEM] Error stopping {name}: {e}")


def stop_all():
    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    ffmpeg_process = None

    stop_process(streamlink_process, "Streamlink")
    streamlink_process = None


# ============================================================
# SIGNAL HANDLING
# ============================================================

def handle_signal(signum, frame):
    global shutdown_requested

    if shutdown_requested:
        return

    shutdown_requested = True

    log("")
    log("[SYSTEM] Shutdown requested...")
    stop_all()

    sys.exit(0)


signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)


# ============================================================
# START STREAMLINK
# ============================================================

def start_streamlink():

    cmd = [
        "streamlink",

        "--no-version-check",

        # YouTube
        YOUTUBE_URL,

        # Quality
        STREAM_QUALITY,

        # Output raw stream to stdout
        "--stdout",

        # HLS latency
        "--hls-live-edge",
        HLS_LIVE_EDGE,

        # Buffer
        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        # Keep searching for the live stream
        "--retry-streams",
        "10",

        # 0 = unlimited retries
        "--retry-max",
        "0",

        # Retry opening stream
        "--retry-open",
        "5",

        # Segment reliability
        "--stream-segment-attempts",
        SEGMENT_ATTEMPTS,

        "--stream-segment-timeout",
        SEGMENT_TIMEOUT,

        # Stream timeout
        "--stream-timeout",
        STREAM_TIMEOUT,

        # HLS playlist recovery
        "--hls-playlist-reload-attempts",
        PLAYLIST_RELOAD_ATTEMPTS,

        # HTTP timeout
        "--http-timeout",
        "30",

        # Segment download threads
        "--stream-segment-threads",
        "2",
    ]

    log("[SYSTEM] Starting Streamlink...")
    log("[SYSTEM] Cookies: OFF")
    log("[SYSTEM] Quality: BEST")
    log("[SYSTEM] Video source will be copied.")
    log("[SYSTEM] Waiting for YouTube stream data...")

    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=None,
            stdin=subprocess.DEVNULL,
            bufsize=0,
        )

        return process

    except Exception as e:
        log(f"[ERROR] Could not start Streamlink: {e}")
        return None


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(streamlink):

    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log("[SYSTEM] Audio: AAC 128k")
    log("[SYSTEM] Sending stream to Restream...")

    cmd = [
        "ffmpeg",

        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",

        "-thread_queue_size",
        "1024",

        "-fflags",
        "+genpts+discardcorrupt",

        "-err_detect",
        "ignore_err",

        "-i",
        "-",

        # ----------------------------------------------------
        # VIDEO
        # ----------------------------------------------------

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # Helps stream-copy timestamp handling
        "-copytb",
        "1",

        # Don't force FPS conversion
        "-fps_mode",
        "passthrough",

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

        # Keep audio timestamps under control
        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # ----------------------------------------------------
        # TIMESTAMP / MUXING
        # ----------------------------------------------------

        "-avoid_negative_ts",
        "make_zero",

        "-max_interleave_delta",
        "0",

        # ----------------------------------------------------
        # FLV / RTMP
        # ----------------------------------------------------

        "-flvflags",
        "no_duration_filesize",

        "-f",
        "flv",

        RESTREAM_RTMP,
    ]

    try:
        process = subprocess.Popen(
            cmd,
            stdin=streamlink.stdout,
            stdout=subprocess.DEVNULL,
            stderr=None,
            bufsize=0,
        )

        # Parent no longer needs its duplicate stdout handle
        if streamlink.stdout:
            streamlink.stdout.close()

        return process

    except Exception as e:
        log(f"[ERROR] Could not start FFmpeg: {e}")
        return None


# ============================================================
# START ONE RELAY SESSION
# ============================================================

def run_session():

    global streamlink_process
    global ffmpeg_process

    log("")
    log("============================================================")
    log("[SYSTEM] Starting relay session")
    log("============================================================")

    # --------------------------------------------------------
    # Start Streamlink
    # --------------------------------------------------------

    streamlink_process = start_streamlink()

    if streamlink_process is None:
        return False

    # --------------------------------------------------------
    # Give Streamlink a moment to initialize
    # --------------------------------------------------------

    start_wait = time.time()

    while not shutdown_requested:

        if streamlink_process.poll() is not None:
            code = streamlink_process.returncode

            log(
                f"[SYSTEM] Streamlink stopped before FFmpeg "
                f"(exit code: {code})"
            )

            stop_all()
            return False

        # As soon as Streamlink has started producing output,
        # FFmpeg can consume it.
        if streamlink_process.stdout is not None:
            break

        if time.time() - start_wait > 30:
            log("[SYSTEM] Streamlink startup timeout.")
            stop_all()
            return False

        time.sleep(0.2)

    log("[SYSTEM] Streamlink process is alive.")
    log("[SYSTEM] Starting FFmpeg pipeline...")

    # --------------------------------------------------------
    # Start FFmpeg
    # --------------------------------------------------------

    ffmpeg_process = start_ffmpeg(streamlink_process)

    if ffmpeg_process is None:
        stop_all()
        return False

    log("[SYSTEM] Stream is RUNNING.")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Audio: AAC 128k")
    log("[SYSTEM] Auto-Reconnect: ON")

    # --------------------------------------------------------
    # Monitor both processes
    # --------------------------------------------------------

    while not shutdown_requested:

        streamlink_code = streamlink_process.poll()
        ffmpeg_code = ffmpeg_process.poll()

        # FFmpeg stopped
        if ffmpeg_code is not None:

            log("")
            log(
                f"[SYSTEM] FFmpeg stopped "
                f"(exit code: {ffmpeg_code})."
            )

            if streamlink_code is None:
                log(
                    "[SYSTEM] Streamlink is still running, "
                    "stopping it before reconnect."
                )

            stop_all()

            return False

        # Streamlink stopped
        if streamlink_code is not None:

            log("")
            log(
                f"[SYSTEM] Streamlink stopped "
                f"(exit code: {streamlink_code})."
            )

            log(
                "[SYSTEM] YouTube/HLS connection ended "
                "or encountered a recoverable error."
            )

            log(
                "[SYSTEM] Recreating Streamlink + FFmpeg session..."
            )

            stop_all()

            return False

        time.sleep(1)

    stop_all()
    return False


# ============================================================
# MAIN RELAY LOOP
# ============================================================

def main():

    log("============================================================")
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("============================================================")
    log(f"YouTube        : {YOUTUBE_URL}")
    log("Destination    : Restream")
    log("Cookies        : OFF")
    log("Video          : COPY")
    log("Video Encode   : OFF")
    log("Crop           : OFF")
    log("Resize         : OFF")
    log("FPS Convert    : OFF")
    log("Audio          : AAC 128k")
    log("Auto-Reconnect : ON")
    log("Status         : STARTING")
    log("============================================================")

    log("[SYSTEM] Starting 24/7 relay...")

    while not shutdown_requested:

        try:

            run_session()

        except KeyboardInterrupt:
            break

        except Exception as e:

            log("")
            log(f"[ERROR] Relay session error: {e}")
            log("[SYSTEM] Cleaning up...")

            stop_all()

        if shutdown_requested:
            break

        # ----------------------------------------------------
        # Reconnect delay
        # ----------------------------------------------------

        log("")
        log("============================================================")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{RESTART_DELAY} seconds..."
        )
        log("============================================================")

        for _ in range(RESTART_DELAY):

            if shutdown_requested:
                break

            time.sleep(1)

    stop_all()

    log("[SYSTEM] Relay stopped.")


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
