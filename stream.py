import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_URL = "https://www.youtube.com/@Yasseraldosry/live"

RESTREAM_URL = (
    "rtmp://live.restream.io/live/"
    "re_12012590_event333a4548cabc4367b4154e3ccbd1a7f9"
)

CHECK_INTERVAL_OFFLINE = 30
COOLDOWN_AFTER_END = 30


# =========================================================
# STREAMLINK
# =========================================================

STREAMLINK_CMD = [
    "streamlink",

    "--hls-live-edge", "2",
    "--ringbuffer-size", "512M",

    # Keep looking for the YouTube LIVE indefinitely
    "--retry-streams", "5",
    "--retry-max", "0",

    # Retry opening the actual stream
    "--retry-open", "5",

    "--stream-segment-attempts", "5",
    "--stream-segment-timeout", "15",

    "--stdout",

    YOUTUBE_URL,
    "best"
]


# =========================================================
# FFMPEG
# =========================================================

FFMPEG_CMD = [
    "ffmpeg",

    "-hide_banner",
    "-loglevel", "warning",
    "-stats",

    # INPUT
    "-thread_queue_size", "1024",
    "-fflags", "+genpts+discardcorrupt",
    "-err_detect", "ignore_err",

    "-i", "-",

    # VIDEO
    # COPY - NO VIDEO ENCODING
    "-map", "0:v:0",
    "-c:v", "copy",

    # Preserve source timing
    "-fps_mode", "passthrough",

    # AUDIO
    # Audio only is encoded
    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    # AUDIO SYNC
    "-af",
    "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

    # OUTPUT
    "-flush_packets", "1",
    "-flvflags", "no_duration_filesize",

    "-f", "flv",

    RESTREAM_URL
]


# =========================================================
# PROCESSES
# =========================================================

streamlink_process = None
ffmpeg_process = None
stopping = False


# =========================================================
# STOP PROCESS
# =========================================================

def stop_process(process, name="process"):

    if process is None:
        return

    if process.poll() is not None:
        return

    print(f"[SYSTEM] Stopping {name}...")

    try:
        process.terminate()
        process.wait(timeout=5)

    except subprocess.TimeoutExpired:

        print(f"[SYSTEM] {name} did not stop. Killing...")

        try:
            process.kill()
            process.wait(timeout=3)

        except Exception:
            pass

    except Exception as e:

        print(f"[SYSTEM] Error stopping {name}: {e}")

        try:
            process.kill()
        except Exception:
            pass


# =========================================================
# CLEANUP
# =========================================================

def cleanup():

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


# =========================================================
# SIGNAL HANDLER
# =========================================================

def signal_handler(sig, frame):

    global stopping

    stopping = True

    print("\n[SYSTEM] Shutdown requested.")

    cleanup()

    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# =========================================================
# START
# =========================================================

print("==============================================")
print("       YouTube -> Restream -> TikTok")
print("==============================================")
print("YouTube     : @Yasseraldosry")
print("Video       : COPY")
print("Video Encode: OFF")
print("Crop        : OFF")
print("Resize      : OFF")
print("FPS Convert : OFF")
print("Audio       : AAC 128k")
print("Destination : Restream")
print("Auto Detect : ON")
print("Status      : RUNNING")
print("==============================================\n")


# =========================================================
# MAIN LOOP
# =========================================================

while not stopping:

    try:

        cleanup()

        print(
            f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            "Starting YouTube monitor..."
        )

        print(
            "[SYSTEM] Waiting for an actual YouTube LIVE stream..."
        )

        # -------------------------------------------------
        # START STREAMLINK
        # -------------------------------------------------

        streamlink_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=None,
            bufsize=0
        )

        # -------------------------------------------------
        # START FFMPEG IMMEDIATELY
        #
        # FFmpeg will wait for Streamlink's stdout.
        # We DO NOT assume that Streamlink being alive
        # means that a playable stream exists.
        # -------------------------------------------------

        ffmpeg_process = subprocess.Popen(
            FFMPEG_CMD,
            stdin=streamlink_process.stdout,
            stdout=None,
            stderr=None,
            bufsize=0
        )

        # Close parent's copy of the pipe
        streamlink_process.stdout.close()

        print("[SYSTEM] FFmpeg started.")
        print("[SYSTEM] Waiting for YouTube stream data...\n")


        # -------------------------------------------------
        # MONITOR
        # -------------------------------------------------

        while not stopping:

            ffmpeg_return = ffmpeg_process.poll()
            streamlink_return = streamlink_process.poll()

            # FFmpeg stopped
            if ffmpeg_return is not None:

                print(
                    f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"FFmpeg stopped. Exit code: "
                    f"{ffmpeg_return}"
                )

                break

            # Streamlink stopped
            if streamlink_return is not None:

                print(
                    f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
                    f"Streamlink stopped. Exit code: "
                    f"{streamlink_return}"
                )

                break

            time.sleep(1)


        if stopping:
            break


        # -------------------------------------------------
        # CURRENT SESSION ENDED
        # -------------------------------------------------

        print("\n==============================================")
        print("YouTube LIVE session ended.")
        print("Stopping current processes...")
        print("==============================================\n")

        cleanup()

        print(
            f"[SYSTEM] Waiting {COOLDOWN_AFTER_END} seconds "
            "before starting the next monitoring cycle..."
        )

        time.sleep(COOLDOWN_AFTER_END)


    except KeyboardInterrupt:

        stopping = True

        cleanup()

        break


    except BrokenPipeError:

        print("\n[ERROR] Broken pipe detected.")

        cleanup()

        time.sleep(5)


    except OSError as e:

        print(f"\n[ERROR] OS error: {e}")

        cleanup()

        time.sleep(10)


    except Exception as e:

        print(f"\n[ERROR] Unexpected error: {e}")

        cleanup()

        time.sleep(10)


    finally:

        if not stopping:
            cleanup()


print("\n[SYSTEM] Relay stopped.")
