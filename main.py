# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import subprocess
import sys
import time

# ==========================================================
# ضع رابط الفيديو ومفتاح بث يوتيوب هنا مباشرة
# ==========================================================
YOUTUBE_URL = "https://www.youtube.com/live/dNcDvu-LOx4?si=5uhpaqDkpY1a8Rj0"
STREAM_KEY = "50vb-qw3d-zvth-x1tg-acjw"
RTMP_SERVER = "rtmp://a.rtmp.youtube.com/live2"
# ==========================================================

WARP_PORT = "40000"
YT_CLIENT_SETS = [
    [],
    ["--extractor-args", "youtube:player_client=tv_downgraded,web_safari,mweb"],
    ["--extractor-args", "youtube:player_client=android_vr,visionos,ios"],
]


def log(msg):
    print(msg, flush=True)


def init_warp_daemon():
    """تشغيل خدمة WARP في الخلفية وتفعيل وضع البروكسي."""
    if not shutil.which("warp-svc") or not shutil.which("warp-cli"):
        return False
    subprocess.Popen(["warp-svc"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    subprocess.run(["warp-cli", "--accept-tos", "registration", "new"], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "mode", "proxy"], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "proxy", "port", WARP_PORT], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "connect"], capture_output=True)
    for _ in range(15):
        r = subprocess.run(["warp-cli", "--accept-tos", "status"], capture_output=True, text=True)
        if "Connected" in (r.stdout + r.stderr):
            log("[WARP] متصل وجاهز على بورت 40000")
            return True
        time.sleep(1)
    return False


def rotate_warp_ip():
    """تغيير هوية WARP للحصول على IP جديد عند الحظر."""
    if not shutil.which("warp-cli"):
        return False
    log("[WARP] جاري تغيير الـ IP...")
    subprocess.run(["warp-cli", "--accept-tos", "disconnect"], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "registration", "delete"], capture_output=True)
    time.sleep(2)
    subprocess.run(["warp-cli", "--accept-tos", "registration", "new"], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "mode", "proxy"], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "proxy", "port", WARP_PORT], capture_output=True)
    subprocess.run(["warp-cli", "--accept-tos", "connect"], capture_output=True)
    time.sleep(4)
    return True


def is_blocked(text):
    return bool(re.search(
        r"confirm you.{0,3}re not a bot|HTTP Error 429|Too Many Requests|Sign in to confirm",
        text or "", re.I,
    ))


def extract_stream_urls(url, use_proxy, client_idx):
    """استخراج روابط البث المباشرة بأعلى جودة H.264 متوافقة مع YouTube RTMP بدون كوكيز."""
    fmt = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*[vcodec^=avc1]+ba/b[vcodec^=avc1]/bv*+ba/b"
    cmd = [
        "yt-dlp", "--ignore-config", "--no-playlist", "--no-warnings",
        "-f", fmt, "-j",
        "--socket-timeout", "30", "--retries", "5",
    ]
    if shutil.which("node"):
        cmd += ["--js-runtimes", "node"]
    if use_proxy:
        cmd += ["--proxy", f"socks5://127.0.0.1:{WARP_PORT}"]
    cmd += YT_CLIENT_SETS[client_idx % len(YT_CLIENT_SETS)]
    cmd += ["--", url]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    lines = (r.stdout + "\n" + r.stderr).splitlines()
    for line in reversed(lines):
        if line.startswith("{"):
            try:
                info = json.loads(line)
                req_fmts = info.get("requested_formats")
                if req_fmts and len(req_fmts) >= 2:
                    v_url = req_fmts[0]["url"]
                    a_url = req_fmts[1]["url"]
                    headers = req_fmts[0].get("http_headers") or info.get("http_headers") or {}
                    return [v_url, a_url], headers, info.get("title", ""), ""
                elif info.get("url"):
                    headers = info.get("http_headers") or {}
                    return [info["url"]], headers, info.get("title", ""), ""
            except Exception:
                continue

    errs = [s.strip() for s in lines if "ERROR" in s]
    return None, {}, "", (" | ".join(errs[-2:]) or "فشل استخراج الروابط")


def relay_stream(stream_urls, headers, rtmp_target, use_proxy):
    """نقل الفيديو بأعلى جودة زي ما هو (-c:v copy) إلى YouTube Live."""
    hdr_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() != "host")

    cmd = []
    if use_proxy and shutil.which("proxychains4"):
        cmd += ["proxychains4", "-q"]

    cmd += ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-stats"]

    for u in stream_urls:
        if hdr_str:
            cmd += ["-headers", hdr_str]
        cmd += [
            "-reconnect", "1",
            "-reconnect_streamed", "1",
            "-reconnect_delay_max", "5",
            "-re",
            "-i", u,
        ]

    if len(stream_urls) >= 2:
        cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    else:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]

    cmd += [
        "-c:v", "copy",
        "-fps_mode", "passthrough",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        "-ac", "2",
        "-af", "aresample=async=1000",
        "-f", "flv",
        rtmp_target,
    ]

    proc = subprocess.run(cmd)
    return proc.returncode


if __name__ == "__main__":
    url = (os.environ.get("YOUTUBE_URL") or YOUTUBE_URL).strip()
    key = (os.environ.get("STREAM_KEY") or STREAM_KEY).strip()
    rtmp = (os.environ.get("RTMP_SERVER") or RTMP_SERVER).strip().rstrip("/")

    if not url or "PUT_LINK_HERE" in url:
        log("❌ ضع رابط اليوتيوب في YOUTUBE_URL أولاً.")
        sys.exit(1)
    if not key or "PUT_YOUTUBE_STREAM_KEY_HERE" in key:
        log("❌ ضع مفتاح بث يوتيوب في STREAM_KEY أولاً.")
        sys.exit(1)

    rtmp_target = f"{rtmp}/{key}"
    warp_ready = init_warp_daemon()

    lanes = [False] + ([True] if warp_ready else [])  # False = direct, True = WARP proxy
    attempt = 0

    while True:
        use_proxy = lanes[attempt % len(lanes)]
        client_idx = attempt // len(lanes)
        lane_name = "WARP-Proxy" if use_proxy else "Direct"

        log(f"\n🔍 [{lane_name}] جاري سحب أعلى جودة للرابط (client_set={client_idx % len(YT_CLIENT_SETS)})...")
        urls, headers, title, err = extract_stream_urls(url, use_proxy, client_idx)

        if not urls:
            log(f"⚠️ فشل الاستخراج عبر [{lane_name}]: {err[:160]}")
            if use_proxy and is_blocked(err):
                rotate_warp_ip()
            attempt += 1
            time.sleep(3)
            continue

        log(f"✅ العنوان: {title}")
        log(f"🚀 بدأ النقل المباشر بأعلى جودة (Copy) إلى يوتيوب عبر [{lane_name}]...")
        rc = relay_stream(urls, headers, rtmp_target, use_proxy)

        if rc == 0:
            log("✅ انتهى البث/الفيديو بشكل طبيعي.")
            break

        log(f"⚠️ توقف البث (كود {rc})، جاري إعادة الاتصال وتحديث الروابط...")
        attempt += 1
        time.sleep(3)
