import os
import sys
import time
import base64
import subprocess


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://youtu.be/pNd2amw7ZAo"

YOUTUBE_STREAM_KEY = "e64m-e0kj-xbd4-24vm-c7rr"

YOUTUBE_RTMP = (
    "rtmp://a.rtmp.youtube.com/live2/"
    + YOUTUBE_STREAM_KEY
)

VIDEO_FILE = "/tmp/video.mp4"
COOKIES_FILE = "/tmp/youtube_cookies.txt"


# ============================================================
# LOG
# ============================================================

def log(message):
    print(message, flush=True)


# ============================================================
# COOKIES
# ============================================================

def prepare_cookies():

    cookies_b64 = os.getenv("YOUTUBE_COOKIES_B64")

    if not cookies_b64:
        log("[COOKIES] OFF")
        return None

    try:

        data = base64.b64decode(
            cookies_b64,
            validate=True
        )

        with open(COOKIES_FILE, "wb") as f:
            f.write(data)

        size = len(data)

        log(
            f"[COOKIES] Decoded: {size} bytes"
        )

        with open(COOKIES_FILE, "rb") as f:
            lines = f.readlines()

        # Count actual cookie lines
        cookie_lines = []

        for line in lines:

            line = line.decode(
                "utf-8",
                errors="replace"
            ).strip()

            if (
                line
                and not line.startswith("#")
            ):
                cookie_lines.append(line)

        log(
            f"[COOKIES] Actual cookie entries: "
            f"{len(cookie_lines)}"
        )

        if len(cookie_lines) == 0:

            log(
                "[COOKIES] WARNING: "
                "No actual cookies found."
            )

            log(
                "[COOKIES] Continuing WITHOUT cookies."
            )

            return None

        first_line = (
            lines[0]
            .decode(
                "utf-8",
                errors="replace"
            )
            .strip()
        )

        if first_line not in (
            "# HTTP Cookie File",
            "# Netscape HTTP Cookie File"
        ):

            log(
                "[COOKIES] Invalid Netscape format."
            )

            return None

        log(
            "[COOKIES] Format: OK"
        )

        return COOKIES_FILE

    except Exception as e:

        log(
            f"[COOKIES] ERROR: {e}"
        )

        return None


# ============================================================
# RUNTIME
# ============================================================

def check_runtime():

    log("============================================================")
    log("[SYSTEM] Runtime check")
    log("============================================================")

    # DENO
    try:

        result = subprocess.run(
            [
                "/usr/local/bin/deno",
                "--version"
            ],
            capture_output=True,
            text=True
        )

        log("[DENO]")
        log(
            result.stdout.strip()
            or result.stderr.strip()
        )

    except Exception as e:

        log(
            f"[DENO] ERROR: {e}"
        )

        return False

    # YT-DLP
    try:

        result = subprocess.run(
            [
                "yt-dlp",
                "--version"
            ],
            capture_output=True,
            text=True
        )

        log(
            "[yt-dlp] "
            + (
                result.stdout.strip()
                or result.stderr.strip()
            )
        )

    except Exception as e:

        log(
            f"[yt-dlp] ERROR: {e}"
        )

        return False

    # FFMPEG
    try:

        result = subprocess.run(
            [
                "ffmpeg",
                "-version"
            ],
            capture_output=True,
            text=True
        )

        first_line = (
            result.stdout.strip()
            .splitlines()[0]
            if result.stdout.strip()
            else result.stderr.strip()
        )

        log(
            "[FFmpeg] "
            + first_line
        )

    except Exception as e:

        log(
            f"[FFmpeg] ERROR: {e}"
        )

        return False

    return True


# ============================================================
# BUILD YT-DLP COMMAND
# ============================================================

def build_ytdlp_command(
    cookies,
    client_mode
):

    command = [
        "yt-dlp",

        "--no-playlist",

        "--no-warnings",

        "--js-runtimes",
        "deno",

        "--remote-components",
        "ejs:npm",

        "--no-check-certificates",

        "--retries",
        "5",

        "--extractor-retries",
        "5",

        "--socket-timeout",
        "60"
    ]

    # --------------------------------------------------------
    # CLIENT
    # --------------------------------------------------------

    if client_mode == "default":

        log(
            "[CLIENT] default"
        )

    elif client_mode == "web_safari":

        command.extend([
            "--extractor-args",
            "youtube:player_client=default,web_safari",
            "--extractor-args",
            "youtube:webpage_client=web_safari"
        ])

        log(
            "[CLIENT] default + web_safari"
        )

    elif client_mode == "android_vr":

        command.extend([
            "--extractor-args",
            "youtube:player_client=android_vr"
        ])

        log(
            "[CLIENT] android_vr"
        )

    elif client_mode == "tv":

        command.extend([
            "--extractor-args",
            "youtube:player_client=tv"
        ])

        log(
            "[CLIENT] tv"
        )

    elif client_mode == "web_embedded":

        command.extend([
            "--extractor-args",
            "youtube:player_client=web_embedded"
        ])

        log(
            "[CLIENT] web_embedded"
        )

    # --------------------------------------------------------
    # COOKIES
    # --------------------------------------------------------

    if cookies:

        command.extend([
            "--cookies",
            cookies
        ])

        log(
            "[COOKIES] ON"
        )

    else:

        log(
            "[COOKIES] OFF"
        )

    command.append(
        YOUTUBE_URL
    )

    return command


# ============================================================
# TEST YOUTUBE
# ============================================================

def test_youtube_access(cookies):

    log("============================================================")
    log("[SYSTEM] Testing YouTube access")
    log("============================================================")

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Try several clients automatically.
    #
    # Some YouTube clients currently have different
    # PO-token / SABR / bot-check requirements.
    # --------------------------------------------------------

    clients = [
        "default",
        "web_safari",
        "android_vr",
        "tv",
        "web_embedded"
    ]

    for client in clients:

        log("")
        log(
            "------------------------------------------------------------"
        )

        log(
            f"[TEST] Trying client: {client}"
        )

        log(
            "------------------------------------------------------------"
        )

        command = build_ytdlp_command(
            cookies,
            client
        )

        command.insert(
            2,
            "--simulate"
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        combined = (
            result.stdout
            + "\n"
            + result.stderr
        ).strip()

        if result.returncode == 0:

            log(
                f"[SUCCESS] YouTube client works: {client}"
            )

            return client

        log(
            f"[FAILED] Client {client}"
        )

        # Show useful error only
        log(
            combined[-2500:]
        )

        time.sleep(2)

    log("")
    log(
        "============================================================"
    )

    log(
        "[FATAL] All YouTube clients failed."
    )

    log(
        "[FATAL] YouTube is currently blocking "
        "this Railway request."
    )

    log(
        "============================================================"
    )

    return None


# ============================================================
# DOWNLOAD
# ============================================================

def download_video(
    cookies,
    working_client
):

    # --------------------------------------------------------
    # Existing video
    # --------------------------------------------------------

    if os.path.exists(VIDEO_FILE):

        try:

            size = os.path.getsize(
                VIDEO_FILE
            )

            if size > 10 * 1024 * 1024:

                log(
                    "[SYSTEM] Existing video found."
                )

                log(
                    f"[SYSTEM] "
                    f"{size / 1024 / 1024:.2f} MB"
                )

                return True

        except Exception:
            pass

    # Remove old file

    try:

        if os.path.exists(VIDEO_FILE):
            os.remove(VIDEO_FILE)

    except Exception:
        pass

    log("============================================================")
    log("[SYSTEM] Downloading YouTube video")
    log("============================================================")

    log(
        f"[SOURCE] {YOUTUBE_URL}"
    )

    # --------------------------------------------------------
    # Prefer H264 <=1080p <=60fps
    # --------------------------------------------------------

    format_selector = (
        "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
        "bestaudio[ext=m4a]/"

        "best[height<=1080][fps<=60][vcodec^=avc1]/"

        "bestvideo[height<=1080][fps<=60]+"
        "bestaudio/"

        "best[height<=1080][fps<=60]/"

        "best"
    )

    command = [
        "yt-dlp",

        "--no-playlist",

        "-f",
        format_selector,

        "--merge-output-format",
        "mp4",

        "-o",
        VIDEO_FILE,

        "--no-part",

        "--retries",
        "10",

        "--fragment-retries",
        "10",

        "--extractor-retries",
        "10",

        "--socket-timeout",
        "60",

        "--concurrent-fragments",
        "4",

        "--js-runtimes",
        "deno",

        "--remote-components",
        "ejs:npm",

        "--no-check-certificates"
    ]

    # --------------------------------------------------------
    # Same client that passed the test
    # --------------------------------------------------------

    if working_client == "web_safari":

        command.extend([
            "--extractor-args",
            "youtube:player_client=default,web_safari",

            "--extractor-args",
            "youtube:webpage_client=web_safari"
        ])

    elif working_client == "android_vr":

        command.extend([
            "--extractor-args",
            "youtube:player_client=android_vr"
        ])

    elif working_client == "tv":

        command.extend([
            "--extractor-args",
            "youtube:player_client=tv"
        ])

    elif working_client == "web_embedded":

        command.extend([
            "--extractor-args",
            "youtube:player_client=web_embedded"
        ])

    # --------------------------------------------------------
    # Cookies
    # --------------------------------------------------------

    if cookies:

        command.extend([
            "--cookies",
            cookies
        ])

    command.append(
        YOUTUBE_URL
    )

    log(
        "[SYSTEM] Target:"
    )

    log(
        "1080p / 60 FPS / H.264 when available"
    )

    log(
        f"[SYSTEM] Using client: {working_client}"
    )

    result = subprocess.run(
        command
    )

    if result.returncode != 0:

        log(
            "[ERROR] yt-dlp download failed."
        )

        return False

    if not os.path.exists(
        VIDEO_FILE
    ):

        log(
            "[ERROR] Video file not created."
        )

        return False

    size = os.path.getsize(
        VIDEO_FILE
    )

    if size < 10 * 1024 * 1024:

        log(
            "[ERROR] Video file too small."
        )

        return False

    log(
        "[SUCCESS] Download completed."
    )

    log(
        f"[SIZE] "
        f"{size / 1024 / 1024:.2f} MB"
    )

    return True


# ============================================================
# VIDEO INFO
# ============================================================

def show_video_info():

    log("============================================================")
    log("[SYSTEM] Video information")
    log("============================================================")

    command = [
        "ffprobe",

        "-v",
        "error",

        "-select_streams",
        "v:0",

        "-show_entries",
        "stream=codec_name,width,height,r_frame_rate",

        "-of",
        "default=noprint_wrappers=1",

        VIDEO_FILE
    ]

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        log(
            result.stdout.strip()
            or result.stderr.strip()
        )

    except Exception as e:

        log(
            f"[FFPROBE] ERROR: {e}"
        )


# ============================================================
# START STREAM
# ============================================================

def start_stream():

    log("============================================================")
    log("[SYSTEM] Starting YouTube LIVE")
    log("============================================================")

    log("[VIDEO] COPY")
    log("[AUDIO] AAC 128k / 44.1kHz / Stereo")
    log("[LOOP] 24/7")

    command = [
        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        # Real time
        "-re",

        # Infinite loop
        "-stream_loop",
        "-1",

        # Input
        "-i",
        VIDEO_FILE,

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

        # Timestamp
        "-fflags",
        "+genpts",

        "-avoid_negative_ts",
        "make_zero",

        # RTMP
        "-f",
        "flv",

        YOUTUBE_RTMP
    ]

    while True:

        process = None

        try:

            log(
                "[SYSTEM] Connecting to YouTube..."
            )

            process = subprocess.Popen(
                command
            )

            return_code = process.wait()

            log(
                "[SYSTEM] FFmpeg stopped."
            )

            log(
                f"[SYSTEM] Exit code: {return_code}"
            )

        except KeyboardInterrupt:

            log(
                "[SYSTEM] Stopping..."
            )

            if process:

                try:
                    process.terminate()
                except Exception:
                    pass

            break

        except Exception as e:

            log(
                f"[ERROR] FFmpeg: {e}"
            )

        log(
            "[SYSTEM] Reconnecting in 10 seconds..."
        )

        time.sleep(10)


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("============================================================")
    log(" YouTube Video -> YouTube LIVE 24/7")
    log(" Multi-client YouTube fallback")
    log(" Deno + yt-dlp + FFmpeg")
    log("============================================================")

    log(
        f"[SOURCE] {YOUTUBE_URL}"
    )

    log(
        "[OUTPUT] YouTube LIVE"
    )

    log(
        "[VIDEO] COPY"
    )

    log(
        "[AUDIO] AAC 128k / 44.1kHz / Stereo"
    )

    log(
        "[LOOP] 24/7"
    )

    log("============================================================")

    # Runtime

    if not check_runtime():

        log(
            "[FATAL] Runtime check failed."
        )

        sys.exit(1)

    # Cookies

    cookies = prepare_cookies()

    # Test

    working_client = test_youtube_access(
        cookies
    )

    if not working_client:

        log("")
        log(
            "[FATAL] No YouTube client could access the video."
        )

        log(
            "[FATAL] Nothing was downloaded."
        )

        sys.exit(1)

    # Download

    if not download_video(
        cookies,
        working_client
    ):

        log(
            "[FATAL] Could not download video."
        )

        sys.exit(1)

    # Info

    show_video_info()

    # Stream

    start_stream()


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
