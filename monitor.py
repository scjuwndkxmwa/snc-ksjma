import os
import subprocess
import time
import signal
import sys
import streamlink

TIKTOK_URL = os.environ.get("TIKTOK_URL", "https://www.tiktok.com/@d.shakertawfiqalaroury/live")
CHECK_INTERVAL_OFFLINE = 15

stream_process = None


def cleanup():
    global stream_process
    if stream_process and stream_process.poll() is None:
        try:
            stream_process.terminate()
            stream_process.wait(timeout=5)
        except Exception:
            try:
                stream_process.kill()
                stream_process.wait(timeout=3)
            except Exception:
                pass
    stream_process = None


def signal_handler(sig, frame):
    print("\n[MONITOR] Stopping monitor service...")
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def is_tiktok_online(url):
    try:
        session = streamlink.Streamlink()
        streams = session.streams(url)
        return len(streams) > 0
    except Exception:
        return False


print("========================================")
print("TikTok Monitor - Listening for Live...")
print("========================================\n")

while True:
    try:
        cleanup()

        print(f"[{time.strftime('%H:%M:%S')}] [MONITOR] Checking TikTok status...")

        if not is_tiktok_online(TIKTOK_URL):
            print(f"[{time.strftime('%H:%M:%S')}] [MONITOR] TikTok is OFFLINE. Next check in {CHECK_INTERVAL_OFFLINE}s...")
            time.sleep(CHECK_INTERVAL_OFFLINE)
            continue

        print(f"\n[{time.strftime('%H:%M:%S')}] [MONITOR] TikTok LIVE detected!")
        print(f"[{time.strftime('%H:%M:%S')}] [MONITOR] Launching stream.py process...")

        stream_process = subprocess.Popen([sys.executable, "stream.py"])
        stream_process.wait()

        print(f"[{time.strftime('%H:%M:%S')}] [MONITOR] stream.py process fully terminated.")

    except KeyboardInterrupt:
        cleanup()
        break

    except Exception as e:
        print(f"[{time.strftime('%H:%M:%S')}] [MONITOR ERROR] {e}")

    finally:
        cleanup()

    time.sleep(CHECK_INTERVAL_OFFLINE)
