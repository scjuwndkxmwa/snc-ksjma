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
# GET DIRECT MEDIA URL
# =========================================================

def get_direct_url():

    print("[INFO] Extracting YouTube media URL via yt-dlp...")

    cmd = [
        "yt-dlp",

        "-g",

        # H.264 video + AAC audio when available.
        # Fallback to the best available format.
        "-f",
        "bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/best[vcodec^=avc1][acodec^=mp4a]/best",

        "--no-check-certificates",

        # Use BgUtils PO Token provider.
        "--extractor-args",
        "youtube:player_client=mweb",

        YOUTUBE_VIDEO_URL
    ]


    # -----------------------------------------------------
    # Cookies if supplied
    # -----------------------------------------------------

    if os.path.exists(COOKIES_PATH):

        cmd.extend([
            "--cookies",
            COOKIES_PATH
        ])


    # -----------------------------------------------------
    # Run yt-dlp
    # -----------------------------------------------------

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
            "[ERROR] yt-dlp returned no media URL."
        )

        return None


    print(
        f"[INFO] yt-dlp returned {len(urls)} media URL(s)."
    )

    return urls


# =========================================================
# FFMPEG
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
print("PO Token: BgUtils")
print("========================================\n")


# =========================================================
# MAIN LOOP
# =========================================================

while True:

    try:

        cleanup()


        # -------------------------------------------------
        # Extract media
        # -------------------------------------------------

        urls = get_direct_url()


        if not urls:

            print(
                "[WARNING] Could not extract media."
            )

            print(
                "[INFO] Retrying in 30 seconds..."
            )

            time.sleep(30)

            continue


        # -------------------------------------------------
        # Determine input layout
        # -------------------------------------------------

        if len(urls) >= 2:

            video_url = urls[0]
            audio_url = urls[1]

            print(
                "[INFO] Separate video/audio streams found."
            )


            FFMPEG_CMD = [

                "ffmpeg",

                "-hide_banner",
                "-loglevel", "warning",
                "-stats",

                "-re",

                # Video
                "-i",
                video_url,

                # Audio
                "-i",
                audio_url,

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
                "1:a:0?",

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

                "-fps_mode",
                "passthrough",

                "-flush_packets",
                "1",

                "-flvflags",
                "no_duration_filesize",

                "-f",
                "flv",

                YOUTUBE_RTMP_DESTINATION
            ]


        else:

            stream_url = urls[0]

            print(
                "[INFO] Combined video/audio stream found."
            )


            FFMPEG_CMD = [

                "ffmpeg",

                "-hide_banner",
                "-loglevel", "warning",
                "-stats",

                "-re",

                "-fflags",
                "+genpts+discardcorrupt",

                "-err_detect",
                "ignore_err",

                "-i",
                stream_url,

                "-map",
                "0:v:0",

                "-c:v",
                "copy",

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

                "-fps_mode",
                "passthrough",

                "-flush_packets",
                "1",

                "-flvflags",
                "no_duration_filesize",

                "-f",
                "flv",

                YOUTUBE_RTMP_DESTINATION
            ]


        # -------------------------------------------------
        # Start FFmpeg
        # -------------------------------------------------

        print(
            "[INFO] Starting FFmpeg → YouTube Live..."
        )

        ffmpeg_process = subprocess.Popen(

            FFMPEG_CMD,

            stdout=sys.stdout,

            stderr=sys.stderr
        )


        return_code = ffmpeg_process.wait()


        print(
            f"[INFO] FFmpeg ended "
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
        "[INFO] Waiting 5 seconds before retry..."
    )

    time.sleep(5)
