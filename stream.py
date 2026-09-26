import subprocess
import time
import signal
import sys


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/7DHNbnPMNiM"

# ============================================================
# RESTREAM
# ============================================================

RESTREAM_STREAM_KEY = "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"

RESTREAM_RTMP = (
    "rtmp://live.restream.io/live/"
    + RESTREAM_STREAM_KEY
)


# ============================================================
# VIDEO / AUDIO
# ============================================================

VIDEO_QUALITY = "best"

VIDEO_COPY = True

AUDIO_CODEC = "aac"
AUDIO_BITRATE = "128k"
AUDIO_SAMPLE_RATE = "44100"
AUDIO_CHANNELS = "2"


# ============================================================
# STREAMLINK SETTINGS
# ============================================================

HLS_LIVE_EDGE = "3"

RINGBUFFER_SIZE = "128M"

RETRY_STREAMS = "10"
RETRY_MAX = "0"

RETRY_OPEN = "10"

SEGMENT_ATTEMPTS = "10"
SEGMENT_TIMEOUT = "15"

STREAM_TIMEOUT = "60"

PLAYLIST_RELOAD_ATTEMPTS = "10"

SEGMENT_THREADS = "2"


# ============================================================
# RECONNECT
# ============================================================

RECONNECT_DELAY = 5


# ============================================================
# PROCESS VARIABLES
# ============================================================

streamlink_process = None
ffmpeg_process = None

stopping = False


# ============================================================
# LOG
# ============================================================

def log(text):
    print(text, flush=True)


# ============================================================
# STOP PROCESS
# ============================================================

def terminate_process(process, name):

    if process is None:
        return

    try:

        if process.poll() is None:

            log(f"[SYSTEM] Stopping {name}...")

            process.terminate()

            try:
                process.wait(timeout=5)

            except subprocess.TimeoutExpired:

                log(f"[SYSTEM] Killing {name}...")

                process.kill()

                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    pass

    except Exception as e:

        log(f"[SYSTEM] Error stopping {name}: {e}")


# ============================================================
# STOP EVERYTHING
# ============================================================

def stop_all():

    global streamlink_process
    global ffmpeg_process

    terminate_process(
        ffmpeg_process,
        "FFmpeg"
    )

    terminate_process(
        streamlink_process,
        "Streamlink"
    )

    ffmpeg_process = None
    streamlink_process = None


# ============================================================
# SIGNAL HANDLER
# ============================================================

def signal_handler(signum, frame):

    global stopping

    if stopping:
        return

    stopping = True

    log("")
    log("[SYSTEM] Shutdown requested...")

    stop_all()


# ============================================================
# START STREAMLINK
# ============================================================

def start_streamlink():

    command = [

        "streamlink",

        "--stdout",

        "--hls-live-edge",
        HLS_LIVE_EDGE,

        "--ringbuffer-size",
        RINGBUFFER_SIZE,

        "--retry-streams",
        RETRY_STREAMS,

        "--retry-max",
        RETRY_MAX,

        "--retry-open",
        RETRY_OPEN,

        "--stream-segment-attempts",
        SEGMENT_ATTEMPTS,

        "--stream-segment-timeout",
        SEGMENT_TIMEOUT,

        "--stream-timeout",
        STREAM_TIMEOUT,

        "--stream-segment-threads",
        SEGMENT_THREADS,

        "--hls-playlist-reload-attempts",
        PLAYLIST_RELOAD_ATTEMPTS,

        "--hls-segment-stream-data",

        YOUTUBE_URL,

        VIDEO_QUALITY
    ]

    log("[SYSTEM] Starting Streamlink...")
    log("[SYSTEM] Cookies: OFF")
    log("[SYSTEM] Waiting for YouTube LIVE...")

    try:

        process = subprocess.Popen(

            command,

            stdout=subprocess.PIPE,

            stderr=None,

            bufsize=0
        )

        return process

    except Exception as e:

        log(
            f"[ERROR] Failed to start Streamlink: {e}"
        )

        return None


# ============================================================
# START FFMPEG
# ============================================================

def start_ffmpeg(streamlink):

    command = [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        "-stats",

        # ----------------------------------------------------
        # INPUT
        # ----------------------------------------------------

        "-thread_queue_size",
        "1024",

        "-i",
        "pipe:0",

        # ----------------------------------------------------
        # TIMESTAMP HANDLING
        # ----------------------------------------------------

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

        # Keep original video timestamps/frame timing
        "-fps_mode",
        "passthrough",

        # ----------------------------------------------------
        # AUDIO
        # ----------------------------------------------------

        "-map",
        "0:a:0?",

        "-c:a",
        AUDIO_CODEC,

        "-b:a",
        AUDIO_BITRATE,

        "-ar",
        AUDIO_SAMPLE_RATE,

        "-ac",
        AUDIO_CHANNELS,

        # Audio timestamp stabilization
        "-af",
        "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

        # ----------------------------------------------------
        # MUX / TIMESTAMPS
        # ----------------------------------------------------

        "-avoid_negative_ts",
        "make_zero",

        "-max_interleave_delta",
        "0",

        # ----------------------------------------------------
        # OUTPUT
        # ----------------------------------------------------

        "-f",
        "flv",

        RESTREAM_RTMP
    ]

    log("[SYSTEM] Starting FFmpeg...")
    log("[SYSTEM] Video: COPY")
    log("[SYSTEM] Video Encode: OFF")
    log("[SYSTEM] Audio: AAC 128k")
    log("[SYSTEM] Sending stream to Restream...")

    try:

        process = subprocess.Popen(

            command,

            stdin=streamlink.stdout,

            stdout=None,

            stderr=None,

            bufsize=0
        )

        return process

    except Exception as e:

        log(
            f"[ERROR] Failed to start FFmpeg: {e}"
        )

        return None


# ============================================================
# RUN ONE SESSION
# ============================================================

def run_session():

    global streamlink_process
    global ffmpeg_process

    streamlink_process = None
    ffmpeg_process = None

    log("")
    log("=" * 60)
    log("[SYSTEM] Starting relay session")
    log("=" * 60)

    # --------------------------------------------------------
    # STREAMLINK
    # --------------------------------------------------------

    streamlink_process = start_streamlink()

    if streamlink_process is None:

        return False

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Do NOT use peek() on the pipe.
    #
    # FFmpeg can read directly from Streamlink stdout.
    # --------------------------------------------------------

    time.sleep(1)

    if stopping:
        return False

    if streamlink_process.poll() is not None:

        log(
            "[SYSTEM] Streamlink exited before "
            "FFmpeg could start."
        )

        return False

    log("[SYSTEM] Streamlink process is alive.")
    log("[SYSTEM] Starting FFmpeg pipeline...")

    # --------------------------------------------------------
    # FFMPEG
    # --------------------------------------------------------

    ffmpeg_process = start_ffmpeg(
        streamlink_process
    )

    if ffmpeg_process is None:

        return False

    log("[SYSTEM] Stream is RUNNING.")

    # --------------------------------------------------------
    # CLOSE OUR COPY OF STREAMLINK STDOUT
    #
    # FFmpeg now owns the pipe.
    # --------------------------------------------------------

    try:

        streamlink_process.stdout.close()

    except Exception:
        pass

    # --------------------------------------------------------
    # MONITOR
    # --------------------------------------------------------

    while not stopping:

        streamlink_code = streamlink_process.poll()

        ffmpeg_code = ffmpeg_process.poll()

        # ----------------------------------------------------
        # FFMPEG EXITED
        # ----------------------------------------------------

        if ffmpeg_code is not None:

            log(
                "[SYSTEM] FFmpeg stopped."
            )

            log(
                f"[SYSTEM] FFmpeg exit code: "
                f"{ffmpeg_code}"
            )

            return False

        # ----------------------------------------------------
        # STREAMLINK EXITED
        # ----------------------------------------------------

        if streamlink_code is not None:

            log(
                "[SYSTEM] Streamlink stopped."
            )

            log(
                f"[SYSTEM] Streamlink exit code: "
                f"{streamlink_code}"
            )

            return False

        time.sleep(2)

    return False


# ============================================================
# MAIN 24/7 LOOP
# ============================================================

def main():

    global stopping

    log("")
    log("=" * 60)
    log("       YouTube 24/7 -> Restream -> TikTok")
    log("=" * 60)

    log(
        f"YouTube        : {YOUTUBE_URL}"
    )

    log(
        "Destination    : Restream"
    )

    log(
        "Cookies        : OFF"
    )

    log(
        "Video          : COPY"
    )

    log(
        "Video Encode   : OFF"
    )

    log(
        "Crop           : OFF"
    )

    log(
        "Resize         : OFF"
    )

    log(
        "FPS Convert    : OFF"
    )

    log(
        "Audio          : AAC 128k"
    )

    log(
        "Auto-Reconnect : ON"
    )

    log(
        "Status         : STARTING"
    )

    log("=" * 60)

    log(
        "[SYSTEM] Starting 24/7 relay..."
    )

    log("=" * 60)

    while not stopping:

        try:

            run_session()

        except KeyboardInterrupt:

            stopping = True
            break

        except Exception as e:

            log(
                f"[ERROR] Session exception: {e}"
            )

        if stopping:
            break

        # ----------------------------------------------------
        # COMPLETE CLEANUP
        # ----------------------------------------------------

        log(
            "[SYSTEM] Cleaning up session..."
        )

        stop_all()

        # ----------------------------------------------------
        # RECONNECT
        # ----------------------------------------------------

        log("")
        log(
            f"[SYSTEM] Reconnecting in "
            f"{RECONNECT_DELAY} seconds..."
        )

        time.sleep(
            RECONNECT_DELAY
        )

    # --------------------------------------------------------
    # FINAL CLEANUP
    # --------------------------------------------------------

    log(
        "[SYSTEM] Final cleanup..."
    )

    stop_all()

    log(
        "[SYSTEM] Relay stopped."
    )


# ============================================================
# SIGNALS
# ============================================================

signal.signal(
    signal.SIGTERM,
    signal_handler
)

signal.signal(
    signal.SIGINT,
    signal_handler
)


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    main()
