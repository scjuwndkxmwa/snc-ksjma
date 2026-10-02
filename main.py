import os
import sys
import time
import base64
import subprocess


# ============================================================
# SOURCE
# ============================================================

YOUTUBE_URL = "https://youtu.be/pNd2amw7ZAo"


# ============================================================
# YOUTUBE OUTPUT
# ============================================================

YOUTUBE_STREAM_KEY = "e64m-e0kj-xbd4-24vm-c7rr"

YOUTUBE_RTMP = (
    "rtmp://a.rtmp.youtube.com/live2/"
    + YOUTUBE_STREAM_KEY
)


# ============================================================
# FILES
# ============================================================

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
        log("[COOKIES] OFF - YOUTUBE_COOKIES_B64 is not set.")
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
            f"[COOKIES] File decoded successfully: "
            f"{size} bytes"
        )

        with open(COOKIES_FILE, "rb") as f:
            first_line = (
                f.readline()
                .decode("utf-8", errors="replace")
                .strip()
            )

        if first_line not in (
            "# HTTP Cookie File",
            "# Netscape HTTP Cookie File",
        ):
            log(
                "[COOKIES] ERROR: "
                "File is not Mozilla/Netscape cookies format."
            )

            log(
                "[COOKIES] First line received: "
                + first_line[:120]
            )

            return None

        log("[COOKIES] Format check: OK")

        return COOKIES_FILE

    except Exception as e:
        log(
            "[COOKIES] ERROR: "
            f"Cannot decode/check cookies: {e}"
        )

        return None


# ============================================================
# RUNTIME CHECK
# ============================================================

def check_runtime():

    log("============================================================")
    log("[SYSTEM] Runtime check")
    log("============================================================")

    # -------------------------
    # DENO
    # -------------------------

    try:

        deno = subprocess.run(
            ["/usr/local/bin/deno", "--version"],
            capture_output=True,
            text=True
        )

        output = (
            deno.stdout.strip()
            or deno.stderr.strip()
        )

        log("[DENO]")
        log(output)

    except Exception as e:

        log(
            f"[DENO] ERROR: {e}"
        )

        return False

    # -------------------------
    # YT-DLP
    # -------------------------

    try:

        ytdlp = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True
        )

        output = (
            ytdlp.stdout.strip()
            or ytdlp.stderr.strip()
        )

        log(
            f"[yt-dlp] {output}"
        )

    except Exception as e:

        log(
            f"[yt-dlp] ERROR: {e}"
        )

        return False

    # -------------------------
    # FFMPEG
    # -------------------------

    try:

        ffmpeg = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True
        )

        first_line = (
            ffmpeg.stdout.strip()
            .splitlines()[0]
            if ffmpeg.stdout.strip()
            else ffmpeg.stderr.strip()
        )

        log(
            f"[FFmpeg] {first_line}"
        )

    except Exception as e:

        log(
            f"[FFmpeg] ERROR: {e}"
        )

        return False

    return True


# ============================================================
# TEST YOUTUBE ACCESS
# ============================================================

def test_youtube_access(cookies):

    log("============================================================")
    log("[SYSTEM] Testing YouTube access before download")
    log("============================================================")

    command = [
        "yt-dlp",

        "--no-playlist",

        "--simulate",

        "--no-warnings",

        "--js-runtimes",
        "deno",

        "--remote-components",
        "ejs:npm",

        "--no-check-certificates",
    ]

    # -------------------------
    # COOKIES
    # -------------------------

    if cookies:

        command.extend([
            "--cookies",
            cookies
        ])

        log(
            "[TEST] Cookies: ON"
        )

    else:

        log(
            "[TEST] Cookies: OFF"
        )

    # -------------------------
    # OPTIONAL USER AGENT
    # -------------------------

    user_agent = os.getenv(
        "YOUTUBE_USER_AGENT",
        ""
    ).strip()

    if user_agent:

        command.extend([
            "--user-agent",
            user_agent
        ])

        log(
            "[TEST] Custom browser User-Agent: ON"
        )

    else:

        log(
            "[TEST] Custom browser User-Agent: OFF"
        )

    command.append(
        YOUTUBE_URL
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
            "[TEST] YouTube extraction test: PASS"
        )

        return True

    log(
        "[TEST] YouTube extraction test: FAILED"
    )

    log(
        combined[-6000:]
    )

    if (
        "Sign in to confirm you're not a bot"
        in combined
    ):

        if cookies:

            log(
                "[TEST] YouTube rejected the request "
                "with the supplied cookies."
            )

            log(
                "[TEST] Possible causes:"
            )

            log(
                "[TEST] - Expired cookies"
            )

            log(
                "[TEST] - Invalid browser session"
            )

            log(
                "[TEST] - Railway IP challenge"
            )

        else:

            log(
                "[TEST] YouTube is challenging "
                "the Railway request."
            )

    return False


# ============================================================
# DOWNLOAD VIDEO
# ============================================================

def download_video(cookies):

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
                    f"[SYSTEM] Size: "
                    f"{size / (1024 * 1024):.2f} MB"
                )

                return True

        except Exception:
            pass

    # -------------------------
    # REMOVE OLD FILE
    # -------------------------

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

    # ========================================================
    # QUALITY
    #
    # Prefer:
    # 1080p
    # 60 FPS
    # H.264
    # M4A audio
    # ========================================================

    format_selector = (
        "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
        "bestaudio[ext=m4a]/"

        "best[height<=1080][fps<=60][vcodec^=avc1]/"

        "bestvideo[height<=1080][fps<=60][vcodec^=avc1]+"
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

        "--socket-timeout",
        "60",

        "--concurrent-fragments",
        "4",

        "--js-runtimes",
        "deno",

        "--remote-components",
        "ejs:npm",
    ]

    # -------------------------
    # COOKIES
    # -------------------------

    if cookies:

        command.extend([
            "--cookies",
            cookies
        ])

    # -------------------------
    # USER AGENT
    # -------------------------

    user_agent = os.getenv(
        "YOUTUBE_USER_AGENT",
        ""
    ).strip()

    if user_agent:

        command.extend([
            "--user-agent",
            user_agent
        ])

    command.append(
        YOUTUBE_URL
    )

    log(
        "[SYSTEM] Selecting best compatible quality..."
    )

    log(
        "[SYSTEM] Target: up to 1080p / 60 FPS / H.264"
    )

    result = subprocess.run(
        command
    )

    if result.returncode != 0:

        log(
            "[ERROR] yt-dlp download failed."
        )

        return False

    if not os.path.exists(VIDEO_FILE):

        log(
            "[ERROR] Video file was not created."
        )

        return False

    size = os.path.getsize(
        VIDEO_FILE
    )

    if size < 10 * 1024 * 1024:

        log(
            "[ERROR] Downloaded file is too small."
        )

        return False

    log(
        "[SYSTEM] Download completed: "
        f"{size / (1024 * 1024):.2f} MB"
    )

    return True


# ============================================================
# SHOW VIDEO INFO
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

        output = (
            result.stdout.strip()
            or result.stderr.strip()
        )

        log(output)

    except Exception as e:

        log(
            f"[FFPROBE] ERROR: {e}"
        )


# ============================================================
# START YOUTUBE STREAM
# ============================================================

def start_stream():

    log("============================================================")
    log("[SYSTEM] Starting 24/7 YouTube stream")
    log("============================================================")

    log(
        "[VIDEO] COPY / NO VIDEO ENCODE"
    )

    log(
        "[AUDIO] AAC 128k / 44100Hz / Stereo"
    )

    log(
        "[LOOP] Infinite"
    )

    log(
        "[OUTPUT] YouTube RTMP"
    )

    # ========================================================
    # FFMPEG
    # ========================================================

    command = [

        "ffmpeg",

        "-hide_banner",

        "-loglevel",
        "warning",

        # Real-time playback
        "-re",

        # Repeat forever
        "-stream_loop",
        "-1",

        # Input
        "-i",
        VIDEO_FILE,

        # -------------------------
        # VIDEO
        # -------------------------

        "-map",
        "0:v:0",

        "-c:v",
        "copy",

        # -------------------------
        # AUDIO
        # -------------------------

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

        # -------------------------
        # TIMESTAMP
        # -------------------------

        "-fflags",
        "+genpts",

        "-avoid_negative_ts",
        "make_zero",

        # -------------------------
        # OUTPUT
        # -------------------------

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
                "[SYSTEM] FFmpeg stopped. "
                f"Exit code: {return_code}"
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
                f"[ERROR] FFmpeg error: {e}"
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

    # ========================================================
    # RUNTIME
    # ========================================================

    if not check_runtime():

        log(
            "[FATAL] Runtime check failed."
        )

        sys.exit(1)

    # ========================================================
    # COOKIES
    # ========================================================

    cookies = prepare_cookies()

    if (
        os.getenv("YOUTUBE_COOKIES_B64")
        and not cookies
    ):

        log(
            "[FATAL] YOUTUBE_COOKIES_B64 exists "
            "but the cookie file failed validation."
        )

        sys.exit(1)

    # ========================================================
    # TEST YOUTUBE
    # ========================================================

    if not test_youtube_access(
        cookies
    ):

        log(
            "[FATAL] YouTube access test failed."
        )

        log(
            "[FATAL] Download will NOT start."
        )

        sys.exit(1)

    # ========================================================
    # DOWNLOAD
    # ========================================================

    if not download_video(
        cookies
    ):

        log(
            "[FATAL] Could not download YouTube video."
        )

        sys.exit(1)

    # ========================================================
    # VIDEO INFO
    # ========================================================

    show_video_info()

    # ========================================================
    # STREAM
    # ========================================================

    start_stream()


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":
    main()
