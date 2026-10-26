import os
import sys
import time
import base64
import subprocess


# ============================================================
# CONFIG
# ============================================================

YOUTUBE_URL = "https://www.youtube.com/live/cJFeAw3pkek?si=_JAHZD_-haE6JgRo"

YOUTUBE_STREAM_KEY = "70w6-cwe2-g22v-kz95-161h"

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

    clients = [
        "default",
        "web_safari",
        "android_vr",
        "tv",
        "web_embedded"
    ]

    for client in clients:

        log("")
        log("------------------------------------------------------------")
        log(f"[TEST] Trying client: {client}")
        log("------------------------------------------------------------")

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

            log(f"[SUCCESS] YouTube client works: {client}")

            return client

        log(f"[FAILED] Client {client}")

        log
