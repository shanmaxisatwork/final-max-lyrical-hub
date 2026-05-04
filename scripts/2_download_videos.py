#!/usr/bin/env python3
"""
STEP 2: Download videos using yt-dlp with cookies
- Tries 3 format options in sequence — guaranteed to work
- Uses YouTube cookies to bypass bot detection
"""

import os
import json
import time
import requests
import yt_dlp
from pathlib import Path

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
YT_COOKIES         = os.environ.get("YT_COOKIES", "")
QUEUE_FILE         = "state/download_queue.json"
DOWNLOADS_DIR      = "downloads"
COOKIES_FILE       = "/tmp/yt_cookies.txt"

def telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    clean = msg.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","")
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean}, timeout=10)
    except Exception as e:
        print(f"  [TELEGRAM ERROR] {e}")

def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def write_cookies():
    if not YT_COOKIES:
        print("  [WARN] YT_COOKIES not set!")
        return False
    with open(COOKIES_FILE, "w") as f:
        f.write(YT_COOKIES)
    print(f"  cookies written")
    return True

def download_thumbnail(url, video_id):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            path = f"{DOWNLOADS_DIR}/{video_id}_thumbnail.jpg"
            with open(path, "wb") as f:
                f.write(r.content)
            print(f"  thumbnail saved")
            return path
    except Exception as e:
        print(f"  thumbnail failed: {e}")
    return None

def try_download(url, out, fmt):
    """Attempt download with a specific format string. Returns True on success."""
    print(f"  trying format: {fmt}")
    last_pct = {"v": 0}

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            dled  = d.get("downloaded_bytes", 0)
            if total > 0:
                pct = (dled / total) * 100
                if pct - last_pct["v"] >= 25:
                    print(f"     {pct:.0f}% — {dled//1024//1024}MB/{total//1024//1024}MB")
                    last_pct["v"] = pct
        elif d["status"] == "finished":
            print(f"  streams done, merging...")

    opts = {
        "format": fmt,
        "outtmpl": out,
        "merge_output_format": "mp4",
        "cookiefile": COOKIES_FILE,
        "progress_hooks": [progress_hook],
        "retries": 3,
        "fragment_retries": 3,
        "noplaylist": True,
        "quiet": False,
        "no_warnings": False,
        "ignoreerrors": False,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        print(f"  format failed: {str(e)[:100]}")
        # Clean up partial file
        for f in Path(DOWNLOADS_DIR).glob(f"{out}*"):
            try: os.remove(f)
            except: pass
        return False

def download_video(video_id, title):
    Path(DOWNLOADS_DIR).mkdir(exist_ok=True)
    safe = "".join(c for c in title if c.isalnum() or c in " -_")[:50].strip()
    out  = f"{DOWNLOADS_DIR}/{video_id}_{safe}.mp4"
    url  = f"https://www.youtube.com/watch?v={video_id}"

    # 3 format attempts — from best quality to guaranteed fallback
    formats = [
        "bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio",  # attempt 1: 1080p preferred
        "bestvideo+bestaudio",                                     # attempt 2: best available
        "best",                                                    # attempt 3: single file, always works
    ]

    for fmt in formats:
        # Remove partial files before each attempt
        for f in Path(DOWNLOADS_DIR).glob(f"{video_id}*.mp4"):
            try: os.remove(f)
            except: pass

        success = try_download(url, out, fmt)

        if success:
            # Find actual output (yt-dlp may rename)
            actual = out
            if not os.path.exists(actual):
                candidates = sorted(Path(DOWNLOADS_DIR).glob(f"{video_id}*.mp4"), key=os.path.getmtime, reverse=True)
                if candidates:
                    actual = str(candidates[0])
                else:
                    print(f"  file not found after download attempt")
                    continue

            size = os.path.getsize(actual) / (1024*1024)
            if size < 0.5:
                print(f"  file too small ({size:.1f}MB), trying next format...")
                continue

            print(f"  downloaded with format: {fmt}")
            print(f"  size: {size:.1f} MB")
            return actual

    raise Exception("All 3 format attempts failed — check GitHub Actions logs")

def main():
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Downloader (yt-dlp + cookies)")
    print(f"{'='*60}\n")

    if not write_cookies():
        telegram("ERROR: YT_COOKIES secret missing! Add it to GitHub secrets.")
        return

    queue       = load_json(QUEUE_FILE, [])
    to_download = [v for v in queue if v.get("status") == "queued"]

    if not to_download:
        print("no videos queued.")
        telegram("Downloader: No videos queued.")
        return

    print(f"{len(to_download)} video(s) to download\n")
    telegram(f"Download Started!\n{len(to_download)} video(s) via yt-dlp...")

    for v in to_download:
        vid_id = v["id"]
        title  = v["title"]
        mins   = v.get("duration_s", 0) // 60

        print(f"\n{'─'*50}")
        print(f"Downloading: {title[:70]}")
        print(f"ID: {vid_id} | {mins}m | {v.get('views',0):,} views")

        telegram(
            f"Downloading #{v.get('rank','?')}\n"
            f"{title[:60]}\n"
            f"{mins} min | {v.get('views',0):,} views\n"
            f"Starting yt-dlp..."
        )

        thumb_path = download_thumbnail(v.get("thumbnail_url",""), vid_id)

        try:
            video_path = download_video(vid_id, title)
            file_size  = os.path.getsize(video_path) / (1024*1024)

            for item in queue:
                if item["id"] == vid_id:
                    item["status"]         = "downloaded"
                    item["video_path"]     = video_path
                    item["thumbnail_path"] = thumb_path
                    break

            save_json(QUEUE_FILE, queue)
            telegram(
                f"Download Complete!\n"
                f"{title[:60]}\n"
                f"Size: {file_size:.1f} MB\n"
                f"Thumbnail: {'saved' if thumb_path else 'not found'}\n"
                f"Next: Adding watermark..."
            )
            print(f"SUCCESS! {file_size:.1f} MB")

        except Exception as e:
            err = str(e)[:200]
            print(f"FAILED: {err}")
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = "download_failed"
                    item["error"]  = err
                    break
            save_json(QUEUE_FILE, queue)
            telegram(f"Download FAILED\n{title[:50]}\nError: {err[:150]}")

        time.sleep(2)

    done   = sum(1 for v in queue if v.get("status") == "downloaded")
    failed = sum(1 for v in to_download if v.get("status") == "download_failed")
    print(f"\nDone: {done} success, {failed} failed")
    telegram(f"Download Phase Done!\nSuccess: {done} | Failed: {failed}\nNext: Watermark processing...")

if __name__ == "__main__":
    main()
