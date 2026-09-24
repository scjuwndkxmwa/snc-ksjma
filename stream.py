import os
import subprocess
import time
import signal
import sys

TIKTOK_URL = "https://www.tiktok.com/@mo_3la/live"
YOUTUBE_RTMP = "rtmp://a.rtmp.youtube.com/live2/3jdh-9t5f-u7tc-89qv-2zms"


# ==========================================
# MONITOR SETTINGS
# ==========================================

# Check every 6 seconds (10 times per minute)
CHECK_EVERY = 6

# Search for LIVE for 1 minute
CHECK_WINDOW = 60

# If offline for the full minute,
# stop everything for 3 minutes
OFFLINE_SLEEP = 180


streamlink_process = None
ffmpeg_process = None


# ==========================================
# STREAMLINK
# ==========================================

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


# ==========================================
# FFMPEG
# ==========================================

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

    # VIDEO COPY
    "-map", "0:v:0",
    "-c:v", "copy",

    # AUDIO
    "-map", "0:a:0?",
    "-c:a", "aac",
    "-b:a", "128k",
    "-ar", "44100",
    "-ac", "2",

    "-af",
    "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

    "-fps_mode", "passthrough",

    "-flush_packets", "1",

    "-flvflags", "no_duration_filesize",

    "-f", "flv",

    YOUTUBE_RTMP
]


# ==========================================
# PROCESS CONTROL
# ==========================================

def stop_process(process, name):

    if process and process.poll() is None:

        print(f"[SYSTEM] Stopping {name}...")

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

    global streamlink_process
    global ffmpeg_process

    stop_process(ffmpeg_process, "FFmpeg")
    stop_process(streamlink_process, "Streamlink")

    ffmpeg_process = None
    streamlink_process = None


# ==========================================
# SIGNAL HANDLER
# ==========================================

def signal_handler(sig, frame):

    print("\n[SYSTEM] Shutdown requested.")

    cleanup()

    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ==========================================
# CHECK IF TIKTOK IS LIVE
# ==========================================

def is_live():

    test_process = None

    try:

        test_process = subprocess.Popen(
            STREAMLINK_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0
        )

        # Wait briefly for Streamlink to connect
        for _ in range(5):

            time.sleep(1)

            if test_process.poll() is not None:
                return False

            # If Streamlink produced stream data,
            # the LIVE is available
            if test_process.stdout:

                data = test_process.stdout.read(1)

                if data:
                    return True

        # Still running after connection attempt
        # means Streamlink found the stream.
        return test_process.poll() is None

    except Exception:

        return False

    finally:

        if test_process:

            try:
                test_process.terminate()
                test_process.wait(timeout=3)

            except Exception:

                try:
                    test_process.kill()
                except Exception:
                    pass


# ==========================================
# WAIT FOR LIVE
# ==========================================

def wait_for_live():

    print("\n========================================")
    print("LIVE MONITOR STARTED")
    print(f"Checking every {CHECK_EVERY} seconds for 60 seconds")
    print("========================================")

    start_time = time.time()

    while time.time() - start_time < CHECK_WINDOW:

        remaining = int(
            CHECK_WINDOW - (time.time() - start_time)
        )

        print(
            f"[MONITOR] Checking TikTok... "
            f"{remaining}s remaining"
        )

        if is_live():

            print(
                "\n[MONITOR] TikTok LIVE detected!"
            )

            return True

        time.sleep(CHECK_EVERY)

    print(
        "\n[MONITOR] "
        "No LIVE detected during the 60-second window."
    )

    return False


# ==========================================
# START RESTREAM
# ==========================================

def start_restream():

    global streamlink_process
    global ffmpeg_process

    cleanup()

    print("\n========================================")
    print("TIKTOK LIVE DETECTED")
    print("STARTING RESTREAM")
    print("========================================\n")

    streamlink_process = subprocess.Popen(
        STREAMLINK_CMD,
        stdout=subprocess.PIPE,
        stderr=None,
        bufsize=0
    )

    time.sleep(3)

    if streamlink_process.poll() is not None:

        print(
            "[ERROR] Streamlink failed to start."
        )

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

    print(
        "[SYSTEM] Restream is now running."
    )

    return True


# ==========================================
# MAIN
# ==========================================

print("========================================")
print("TikTok -> YouTube Auto Restreamer")
print("========================================")
print(f"Monitor: {CHECK_EVERY} seconds (10 times / min)")
print("Search window: 60 seconds")
print("Offline sleep: 180 seconds")
print("========================================\n")


while True:

    try:

        # --------------------------------------
        # SEARCH FOR LIVE FOR 1 MINUTE
        # --------------------------------------

        live_found = wait_for_live()


        # --------------------------------------
        # LIVE FOUND
        # --------------------------------------

        if live_found:

            if not start_restream():

                print(
                    "[SYSTEM] Failed to start restream."
                )

                time.sleep(5)

                continue


            # ----------------------------------
            # MONITOR ACTIVE STREAM
            # ----------------------------------

            while True:

                time.sleep(2)

                if streamlink_process is None:
                    break

                if ffmpeg_process is None:
                    break


                streamlink_exit = (
                    streamlink_process.poll()
                )

                ffmpeg_exit = (
                    ffmpeg_process.poll()
                )


                # Stream ended
                if (
                    streamlink_exit is not None
                    or
                    ffmpeg_exit is not None
                ):

                    print(
                        "\n[SYSTEM] "
                        "TikTok LIVE ended "
                        "or streaming process stopped."
                    )

                    cleanup()

                    break


            # ----------------------------------
            # RETURN TO MONITOR
            # ----------------------------------

            print(
                "[SYSTEM] "
                "Returning to LIVE monitor..."
            )

            continue


        # --------------------------------------
        # NO LIVE FOR FULL 1 MINUTE
        # --------------------------------------

        cleanup()

        print("\n========================================")
        print("TIKTOK OFFLINE")
        print("ALL PROCESSES STOPPED")
        print("SLEEPING FOR 3 MINUTES")
        print("========================================\n")


        # --------------------------------------
        # 3 MINUTE COMPLETE SLEEP
        # --------------------------------------

        time.sleep(OFFLINE_SLEEP)


        print(
            "\n[SYSTEM] "
            "3-minute sleep finished."
        )

        print(
            "[SYSTEM] "
            "Starting another 60-second LIVE search..."
        )


    except KeyboardInterrupt:

        print("\n[SYSTEM] Stopping...")

        cleanup()

        break


    except Exception as e:

        print(
            f"\n[ERROR] {e}"
        )

        cleanup()

        print(
            "[SYSTEM] "
            "Retrying monitor in 10 seconds..."
        )

        time.sleep(10)
