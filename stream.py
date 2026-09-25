import os
import subprocess
import time
import signal
import sys


# =========================================================
# SETTINGS
# =========================================================

YOUTUBE_VIDEO_URL = "https://youtu.be/mtKF4rn6SLM"

YOUTUBE_STREAM_KEY = "r77y-h37m-x6xr-x0dj-0g6q"

YOUTUBE_RTMP_DESTINATION = (
    f"rtmp://a.rtmp.youtube.com/live2/{YOUTUBE_STREAM_KEY}"
)


# =========================================================
# OPTIONAL COOKIES
# =========================================================

COOKIES_ENV = os.getenv("YOUTUBE_COOKIES")
COOKIES_PATH = "/tmp/cookies.txt"

if COOKIES_ENV:
    with open(COOKIES_PATH, "w", encoding="utf-8") as f:
        f.write(COOKIES_ENV)


# =========================================================
# GET YOUTUBE HLS URL
# =========================================================

def get_direct_url():

    print("[INFO] Extracting YouTube HLS URL via yt-dlp...")

    cmd = [
        "yt-dlp",

        "-g",

        "-f", "best",

        "--no-check-certificates",

        "--extractor-args",
        "youtube:player_client=web_safari",

        YOUTUBE_VIDEO_URL
    ]

    if os.path.exists(COOKIES_PATH):
        cmd.extend([
            "--cookies",
            COOKIES_PATH
        ])

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:

        print("[ERROR] yt-dlp failed:")
        print(result.stderr.strip())

        return None

    urls = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
    ]

    if not urls:

        print(
            "[ERROR] yt-dlp returned no HLS URL."
        )

        return None

    print(
        "[INFO] YouTube HLS URL obtained successfully."
    )

    return urls[0]


# =========================================================
# FFMPEG PROCESS
# =========================================================

ffmpeg_process = None


def cleanup():

    global ffmpeg_process

    if ffmpeg_process and ffmpeg_process.poll() is None:

        print("[SYSTEM] Stopping FFmpeg...")

        try:

            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=5)

        except Exception:

            try:
                ffmpeg_process.kill()
                ffmpeg_process.wait(timeout=3)

            except Exception:
                pass

    ffmpeg_process = None


# =========================================================
# SIGNAL HANDLER
# =========================================================

def signal_handler(sig, frame):

    print(
        "\n[SYSTEM] Shutdown signal received."
    )

    cleanup()

    sys.exit(0)


signal.signal(
    signal.SIGINT,
    signal_handler
)

signal.signal(
    signal.SIGTERM,
    signal_handler
)


# =========================================================
# START
# =========================================================

print("========================================")
print("YouTube Video → YouTube Live")
print("========================================")
print(
    f"Source: {YOUTUBE_VIDEO_URL}"
)
print("Video: COPY")
print("Audio: AAC")
print("========================================\n")


# =========================================================
# MAIN LOOP
# =========================================================

while True:

    try:

        cleanup()

        stream_url = get_direct_url()

        if not stream_url:

            print(
                "[WARNING] Could not get YouTube HLS URL."
            )

            print(
                "[INFO] Retrying in 15 seconds..."
            )

            time.sleep(15)

            continue


        print(
            "[INFO] HLS URL obtained!"
        )

        print(
            "[INFO] Starting FFmpeg → YouTube Live..."
        )


        # -------------------------------------------------
        # FFMPEG
        # -------------------------------------------------

        FFMPEG_CMD = [

            "ffmpeg",

            "-hide_banner",
            "-loglevel", "warning",
            "-stats",

            # Play source in real time
            "-re",

            # Input
            "-i",
            stream_url,

            # Timestamp handling
            "-fflags",
            "+genpts+discardcorrupt",

            "-err_detect",
            "ignore_err",

            # Video
            "-map",
            "0:v:0",

            "-c:v",
            "copy",

            # Audio
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
            "aresample=async=1000:min_hard_comp=0.100000:first_pts=0",

            # Keep original video timing
            "-fps_mode",
            "passthrough",

            "-flush_packets",
            "1",

            # FLV
            "-flvflags",
            "no_duration_filesize",

            # Output
            "-f",
            "flv",

            YOUTUBE_RTMP_DESTINATION
        ]


        ffmpeg_process = subprocess.Popen(

            FFMPEG_CMD,

            stdout=sys.stdout,

            stderr=sys.stderr
        )


        return_code = ffmpeg_process.wait()


        print(
            f"\n[INFO] FFmpeg ended "
            f"(exit code: {return_code})."
        )


    except KeyboardInterrupt:

        print(
            "\n[SYSTEM] Stopping..."
        )

        cleanup()

        break


    except Exception as e:

        print(
            f"\n[ERROR] Unexpected error: {e}"
        )


    finally:

        cleanup()


    print(
        "[INFO] Stream session ended."
    )

    print(
        "[INFO] Restarting in 5 seconds..."
    )

    time.sleep(5)
