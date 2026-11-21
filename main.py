# -*- coding: utf-8 -*-
import json
import os
import re
import shutil
import subprocess
import sys
import time

# ==========================================================
# رابط الفيديو ومفتاح بث يوتيوب
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


def prefer_ipv4():
    """تفضيل IPv4 لتجنب أخطاء SOCKS5 IPv6 مع ffmpeg و proxychains."""
    try:
        with open("/etc/gai.conf", "a", encoding="utf-8") as f:
            f.write("\nprecedence ::ffff:0:0/96  100\n")
    except Exception:
        pass


def _warp(*args, timeout=30):
    try:
        r = subprocess.run(
            ["warp-cli", "--accept-tos", *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


def verify_warp_proxy(retries=6):
    """التأكد من أن البروكسي يمرر الإنترنت فعلياً وليس مجرد متصل شكلياً."""
    for _ in range(retries):
        r = subprocess.run(
            [
                "curl", "-4", "-s", "--max-time", "8",
                "-x", f"socks5h://127.0.0.1:{WARP_PORT}",
                "https://www.cloudflare.com/cdn-cgi/trace",
            ],
            capture_output=True, text=True,
        )
        if r.returncode == 0 and "warp=" in r.stdout:
            ip_match = re.search(r"ip=([^\s]+)", r.stdout)
            warp_ip = ip_match.group(1) if ip_match else "OK"
            log(f"[WARP-Proxy] ✓ شغال ويمرر البيانات (IP: {warp_ip})")
            return True
        time.sleep(2)
    return False


def configure_and_connect_warp():
    if not _warp("registration", "new")[0]:
        _warp("register")
    if not _warp("mode", "proxy")[0]:
        _warp("set-mode", "proxy")
    if not _warp("proxy", "port", WARP_PORT)[0]:
        _warp("set-proxy-port", WARP_PORT)
    _warp("connect")

    for _ in range(15):
        if "Connected" in _warp("status")[1]:
            break
        time.sleep(1)

    if verify_warp_proxy(retries=5):
        return True

    # لو السيرفر بيحجب UDP WireGuard نحول لبروتوكول MASQUE تلقائياً
    log("[WARP-Proxy] جاري التبديل إلى بروتوكول MASQUE...")
    _warp("disconnect")
    if not _warp("tunnel", "protocol", "set", "MASQUE")[0]:
        _warp("set-tunnel-protocol", "MASQUE")
    _warp("connect")
    time.sleep(3)
    return verify_warp_proxy(retries=6)


def init_warp_daemon():
    """تشغيل خدمة WARP في الخلفية وتفعيل وضع البروكسي."""
    if not shutil.which("warp-svc") or not shutil.which("warp-cli"):
        log("❌ أداة cloudflare-warp غير مثبتة في الحاوية.")
        return False
    subprocess.Popen(["warp-svc"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    return configure_and_connect_warp()


def rotate_warp_ip():
    """تغيير هوية WARP للحصول على IP جديد عند الحظر."""
    log("[WARP-Proxy] جاري تغيير الـ IP والحصول على هوية جديدة...")
    _warp("disconnect")
    if not _warp("registration", "delete")[0]:
        _warp("delete")
    time.sleep(2)
    return configure_and_connect_warp()


def is_blocked(text):
    return bool(re.search(
        r"confirm you.{0,3}re not a bot|HTTP Error 429|Too Many Requests|Sign in to confirm",
        text or "", re.I,
    ))


def extract_stream_urls(url, client_idx):
    """استخراج روابط البث المباشرة بأعلى جودة H.264 عبر WARP Proxy فقط."""
    fmt = "bv*[vcodec^=avc1]+ba[acodec^=mp4a]/bv*[vcodec^=avc1]+ba/b[vcodec^=avc1]/bv*+ba/b"
    cmd = [
        "yt-dlp", "--ignore-config", "--no-playlist", "--no-warnings",
        "--force-ipv4",
        "--proxy", f"socks5h://127.0.0.1:{WARP_PORT}",
        "-f", fmt, "-j",
        "--socket-timeout", "30", "--retries", "5",
    ]
    if shutil.which("node"):
        cmd += ["--js-runtimes", "node"]
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


def relay_stream(stream_urls, headers, rtmp_target):
    """نقل الفيديو بأعلى جودة زي ما هو (-c:v copy) عبر WARP Proxy إلى YouTube Live."""
    hdr_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if k.lower() != "host")

    cmd = []
    if shutil.which("proxychains4"):
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
    prefer_ipv4()

    url = (os.environ.get("YOUTUBE_URL") or YOUTUBE_URL).strip()
    key = (os.environ.get("STREAM_KEY") or STREAM_KEY).strip()
    rtmp = (os.environ.get("RTMP_SERVER") or RTMP_SERVER).strip().rstrip("/")

    if not url:
        log("❌ ضع رابط اليوتيوب في YOUTUBE_URL أولاً.")
        sys.exit(1)
    if not key:
        log("❌ ضع مفتاح بث يوتيوب في STREAM_KEY أولاً.")
        sys.exit(1)

    rtmp_target = f"{rtmp}/{key}"

    while not init_warp_daemon():
        log("⚠️ تعذر تشغيل WARP Proxy، إعادة المحاولة بعد 5 ثوانٍ...")
        time.sleep(5)

    client_idx = 0
    while True:
        log(f"\n🔍 [WARP-Proxy] جاري سحب أعلى جودة للرابط (client_set={client_idx % len(YT_CLIENT_SETS)})...")
        urls, headers, title, err = extract_stream_urls(url, client_idx)

        if not urls:
            log(f"⚠️ فشل الاستخراج عبر [WARP-Proxy]: {err[:160]}")
            if is_blocked(err) or "Connection refused" in err:
                rotate_warp_ip()
            client_idx += 1
            time.sleep(3)
            continue

        log(f"✅ العنوان: {title}")
        log("🚀 بدأ النقل المباشر بأعلى جودة (Copy) إلى يوتيوب عبر [WARP-Proxy]...")
        rc = relay_stream(urls, headers, rtmp_target)

        if rc == 0:
            log("✅ انتهى البث/الفيديو بشكل طبيعي.")
            break

        log(f"⚠️ توقف البث (كود {rc})، جاري تحديث الروابط وإعادة الاتصال...")
        client_idx += 1
        time.sleep(3)
