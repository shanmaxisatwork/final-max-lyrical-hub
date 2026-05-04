#!/usr/bin/env python3
"""
MAX LYRICAL HUB — Laptop Pipeline (Split Architecture)
=======================================================
LAPTOP DOES:  Download → Watermark → Upload to GitHub Release → Push state
GITHUB DOES:  SEO → Upload to YouTube → Telegram → Cleanup

Laptop only needs ~30-40 mins ON.
After that, close laptop — GitHub Actions handles the rest automatically.
"""

import os
import sys
import json
import time
import datetime
import subprocess
import requests
import yt_dlp
from pathlib import Path

# ─── LOAD CONFIG ──────────────────────────────────────────────────────────────
CONFIG_FILE = Path(__file__).parent.parent / "laptop_config.json"

def load_config():
    if not CONFIG_FILE.exists():
        print("ERROR: laptop_config.json not found! Run setup.bat first.")
        sys.exit(1)
    with open(CONFIG_FILE) as f:
        return json.load(f)

cfg = load_config()

YT_API_KEYS        = cfg["yt_api_keys"]
TELEGRAM_BOT_TOKEN = cfg["telegram_bot_token"]
TELEGRAM_CHAT_ID   = cfg["telegram_chat_id"]
GITHUB_TOKEN       = cfg["github_token"]
GITHUB_REPO        = cfg["github_repo"]  # e.g. "maxfindsstore/max-lyrical-hub"

CHANNEL_HANDLES = [
    "@UBII2B", "@7clouds", "@VibeBirdPrime", "@VibeBird",
    "@VdjShyamyt", "@varipettiii", "@seventyskye",
    "@D-MuzeIndia", "@WaVerNoir_26", "@creativchaos", "@Illuvibess",
]

BASE_DIR       = Path(__file__).parent.parent
STATE_DIR      = BASE_DIR / "state"
DOWNLOADS_DIR  = BASE_DIR / "downloads"
PROCESSED_DIR  = BASE_DIR / "processed"
WATERMARK_PATH = BASE_DIR / "watermark" / "watermark.png"
STATE_FILE     = STATE_DIR / "seen_videos.json"
QUEUE_FILE     = STATE_DIR / "download_queue.json"
RUN_INFO_FILE  = STATE_DIR / "run_info.json"
COOKIES_FILE   = BASE_DIR / "yt_cookies.txt"

TOP_N = 10

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    clean = msg.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","")
    try:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": clean}, timeout=10)
    except Exception as e:
        print(f"  [TELEGRAM] {e}")

def load_json(path, default):
    try:
        with open(path) as f:
            d = json.load(f)
            return d if isinstance(d, type(default)) else default
    except:
        return default

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def cleanup_file(path):
    try:
        if path and os.path.exists(str(path)):
            os.remove(str(path))
            print(f"  deleted: {os.path.basename(str(path))}")
    except Exception as e:
        print(f"  [WARN] delete failed: {e}")

def safe_filename(s, maxlen=50):
    return "".join(c for c in s if c.isalnum() or c in " -_")[:maxlen].strip()

def iso_duration_to_seconds(d):
    import re
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', d or "")
    if not m: return 0
    return int(m.group(1) or 0)*3600 + int(m.group(2) or 0)*60 + int(m.group(3) or 0)

def is_short(title, desc, duration_s):
    if duration_s <= 60: return True
    return any(k in (title+desc).lower() for k in ["#shorts","#short","#ytshorts"])

# ─── KEY ROTATION ─────────────────────────────────────────────────────────────
_key_idx = 0
def get_key():
    return YT_API_KEYS[_key_idx % len(YT_API_KEYS)]
def rotate_key():
    global _key_idx
    _key_idx += 1

def yt_get(url, params, retries=4):
    for _ in range(retries):
        params["key"] = get_key()
        try:
            r = requests.get(url, params=params, timeout=15)
            if r.status_code == 403:
                reason = r.json().get("error",{}).get("errors",[{}])[0].get("reason","")
                if "quota" in reason.lower():
                    rotate_key()
                    time.sleep(1)
                    continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  API error: {e}")
            rotate_key()
            time.sleep(1)
    return None

# ─── GITHUB RELEASE UPLOAD ────────────────────────────────────────────────────
def get_or_create_release(tag="processed-videos"):
    """Get existing release or create new one for storing processed videos."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    # Try to get existing release
    r = requests.get(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/{tag}",
        headers=headers, timeout=15
    )
    if r.status_code == 200:
        return r.json()["id"], r.json()["upload_url"]

    # Create new release
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/releases",
        headers=headers,
        json={
            "tag_name": tag,
            "name": "Processed Videos Queue",
            "body": "Auto-managed by Max Lyrical Hub bot. Do not delete manually.",
            "draft": False,
            "prerelease": True,
        },
        timeout=15
    )
    r.raise_for_status()
    data = r.json()
    return data["id"], data["upload_url"]

def upload_to_github_release(file_path, release_id, filename):
    """Upload a file to GitHub Release assets."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "video/mp4",
    }
    upload_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets?name={filename}"

    file_size = os.path.getsize(file_path) / (1024*1024)
    print(f"  uploading to GitHub Release: {filename} ({file_size:.1f}MB)")
    print(f"  this may take a few minutes...")

    with open(file_path, "rb") as f:
        r = requests.post(upload_url, headers=headers, data=f, timeout=600)

    if r.status_code in [200, 201]:
        download_url = r.json()["browser_download_url"]
        print(f"  uploaded! URL: {download_url}")
        return download_url
    else:
        raise Exception(f"GitHub upload failed: {r.status_code} — {r.text[:200]}")

def upload_thumbnail_to_release(thumb_path, release_id, filename):
    """Upload thumbnail to GitHub Release."""
    if not thumb_path or not os.path.exists(thumb_path):
        return None
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "image/jpeg",
    }
    upload_url = f"https://uploads.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets?name={filename}"
    with open(thumb_path, "rb") as f:
        r = requests.post(upload_url, headers=headers, data=f, timeout=60)
    if r.status_code in [200, 201]:
        return r.json()["browser_download_url"]
    return None

# ─── MONITOR CHANNELS ─────────────────────────────────────────────────────────
def get_scan_hours():
    run_info = load_json(RUN_INFO_FILE, {})
    if run_info.get("is_first_run", True):
        print("FIRST RUN — scanning past 10 days")
        telegram("First Run! Scanning past 10 days...")
        return 240
    print("Regular run — scanning past 2 days")
    return 48

def resolve_handle(handle):
    data = yt_get(
        "https://www.googleapis.com/youtube/v3/channels",
        {"part": "id,snippet", "forHandle": handle.lstrip("@"), "maxResults": 1}
    )
    if data and data.get("items"):
        item = data["items"][0]
        return item["id"], item["snippet"]["title"]
    return None, None

def get_recent_videos(channel_id, channel_name, hours_back):
    published_after = (
        datetime.datetime.utcnow() - datetime.timedelta(hours=hours_back)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = yt_get(
        "https://www.googleapis.com/youtube/v3/channels",
        {"part": "contentDetails", "id": channel_id}
    )
    if not data or not data.get("items"):
        return []
    playlist = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    videos = []
    page_token = None
    while True:
        params = {"part": "snippet", "playlistId": playlist, "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        pdata = yt_get("https://www.googleapis.com/youtube/v3/playlistItems", params)
        if not pdata:
            break
        for item in pdata.get("items", []):
            pub = item["snippet"]["publishedAt"]
            if pub >= published_after:
                vid_id = item["snippet"]["resourceId"]["videoId"]
                videos.append({
                    "id": vid_id,
                    "channel_name": channel_name,
                    "channel_id": channel_id,
                    "title": item["snippet"]["title"],
                    "published": pub,
                    "thumbnail_url": (
                        item["snippet"].get("thumbnails",{})
                        .get("maxres", item["snippet"].get("thumbnails",{})
                        .get("high",{})).get("url","")
                    ),
                })
            else:
                return videos
        page_token = pdata.get("nextPageToken")
        if not page_token:
            break
    return videos

def enrich_videos(video_ids):
    enriched = {}
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        data = yt_get(
            "https://www.googleapis.com/youtube/v3/videos",
            {"part": "statistics,contentDetails,snippet", "id": ",".join(batch)}
        )
        if not data:
            continue
        for item in data.get("items", []):
            vid_id  = item["id"]
            stats   = item.get("statistics", {})
            detail  = item.get("contentDetails", {})
            snippet = item.get("snippet", {})
            duration_s = iso_duration_to_seconds(detail.get("duration",""))
            views    = int(stats.get("viewCount", 0))
            likes    = int(stats.get("likeCount", 0))
            comments = int(stats.get("commentCount", 0))
            enriched[vid_id] = {
                "duration_s":  duration_s,
                "views":       views,
                "likes":       likes,
                "comments":    comments,
                "engagement":  views + likes*5 + comments*10,
                "description": snippet.get("description",""),
                "tags":        snippet.get("tags",[]),
                "category_id": snippet.get("categoryId","10"),
                "thumbnail_url": (
                    snippet.get("thumbnails",{})
                    .get("maxres", snippet.get("thumbnails",{})
                    .get("standard", snippet.get("thumbnails",{})
                    .get("high",{}))).get("url","")
                ),
            }
    return enriched

def monitor_channels(hours_back):
    print("\n" + "="*60)
    print("STEP 1: Monitor Channels")
    print("="*60)

    seen  = load_json(STATE_FILE, {})
    queue = load_json(QUEUE_FILE, [])
    queued_ids = {v["id"] for v in queue if isinstance(v, dict)}

    print("\nResolving handles...")
    channels = []
    for handle in CHANNEL_HANDLES:
        uc_id, name = resolve_handle(handle)
        if uc_id:
            channels.append({"handle": handle, "id": uc_id, "name": name})
            print(f"  {handle} -> {name}")
        time.sleep(0.3)

    all_new = []
    print(f"\nFetching videos (past {hours_back//24} days)...")
    for ch in channels:
        videos = get_recent_videos(ch["id"], ch["name"], hours_back)
        new = [v for v in videos if v["id"] not in seen and v["id"] not in queued_ids]
        print(f"  {ch['name']}: {len(new)} new")
        all_new.extend(new)
        time.sleep(0.3)

    if not all_new:
        print("No new videos found")
        telegram("No new videos found in scan window.")
        return []

    print(f"\nFetching stats for {len(all_new)} videos...")
    enriched = enrich_videos([v["id"] for v in all_new])

    long_videos = []
    for v in all_new:
        info = enriched.get(v["id"], {})
        if is_short(v["title"], info.get("description",""), info.get("duration_s",0)):
            seen[v["id"]] = "skipped_short"
            continue
        v.update(info)
        long_videos.append(v)

    if not long_videos:
        save_json(STATE_FILE, seen)
        return []

    long_videos.sort(key=lambda x: x.get("engagement",0), reverse=True)
    top = long_videos[:TOP_N]

    print(f"\nTOP {len(top)} VIDEOS:")
    queue_items = []
    for rank, v in enumerate(top, 1):
        mins = v.get("duration_s",0) // 60
        print(f"  #{rank} [{mins}m] {v['title'][:60]} | {v.get('views',0):,} views")
        queue_items.append({
            "id":              v["id"],
            "title":           v["title"],
            "channel_name":    v["channel_name"],
            "url":             f"https://www.youtube.com/watch?v={v['id']}",
            "duration_s":      v.get("duration_s",0),
            "views":           v.get("views",0),
            "likes":           v.get("likes",0),
            "comments":        v.get("comments",0),
            "engagement":      v.get("engagement",0),
            "thumbnail_url":   v.get("thumbnail_url",""),
            "tags":            v.get("tags",[]),
            "category_id":     v.get("category_id","10"),
            "description_raw": v.get("description",""),
            "rank":            rank,
            "status":          "queued",
        })
        seen[v["id"]] = "queued"

    for v in long_videos[TOP_N:]:
        seen[v["id"]] = "skipped_not_top"

    updated = [v for v in queue if v.get("status") not in ["queued","failed"]] + queue_items
    save_json(QUEUE_FILE, updated)
    save_json(STATE_FILE, seen)

    lines = [f"Scan Complete! Found {len(top)} videos:\n"]
    for v in queue_items:
        lines.append(f"#{v['rank']} {v['title'][:50]} | {v['views']:,} views")
    telegram("\n".join(lines))
    return queue_items

# ─── DOWNLOAD ─────────────────────────────────────────────────────────────────
def download_video(video_id, title):
    DOWNLOADS_DIR.mkdir(exist_ok=True)
    safe = safe_filename(title)
    out  = str(DOWNLOADS_DIR / f"{video_id}_{safe}.mp4")
    url  = f"https://www.youtube.com/watch?v={video_id}"

    last_pct = {"v": 0}
    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate",0)
            dled  = d.get("downloaded_bytes",0)
            if total > 0:
                pct = (dled/total)*100
                if pct - last_pct["v"] >= 25:
                    print(f"     {pct:.0f}% — {dled//1024//1024}MB/{total//1024//1024}MB")
                    last_pct["v"] = pct
        elif d["status"] == "finished":
            print(f"  merging streams...")

    formats = [
        "bestvideo[height<=1080]+bestaudio/bestvideo+bestaudio",
        "bestvideo+bestaudio",
        "best",
    ]
    cookie_opts = {"cookiefile": str(COOKIES_FILE)} if COOKIES_FILE.exists() else {}

    for fmt in formats:
        for f in DOWNLOADS_DIR.glob(f"{video_id}*.mp4"):
            try: os.remove(f)
            except: pass
        try:
            print(f"  trying format: {fmt}")
            with yt_dlp.YoutubeDL({
                "format": fmt,
                "outtmpl": out,
                "merge_output_format": "mp4",
                "progress_hooks": [progress_hook],
                "retries": 5,
                "fragment_retries": 5,
                "noplaylist": True,
                **cookie_opts,
            }) as ydl:
                ydl.download([url])

            actual = out
            if not os.path.exists(actual):
                candidates = sorted(DOWNLOADS_DIR.glob(f"{video_id}*.mp4"), key=os.path.getmtime, reverse=True)
                if candidates:
                    actual = str(candidates[0])
                else:
                    continue

            size = os.path.getsize(actual) / (1024*1024)
            if size < 1:
                continue
            print(f"  downloaded: {size:.1f} MB")
            return actual
        except Exception as e:
            print(f"  format failed: {str(e)[:80]}")
            continue

    raise Exception("All download formats failed")

def download_thumbnail(url, video_id):
    if not url:
        return None
    try:
        r = requests.get(url, timeout=15)
        if r.status_code == 200:
            path = DOWNLOADS_DIR / f"{video_id}_thumbnail.jpg"
            path.write_bytes(r.content)
            return str(path)
    except:
        pass
    return None

# ─── WATERMARK ────────────────────────────────────────────────────────────────
def add_watermark(input_path, video_id, title):
    PROCESSED_DIR.mkdir(exist_ok=True)
    output = str(PROCESSED_DIR / f"{video_id}_{safe_filename(title)}_wm.mp4")
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-i", str(WATERMARK_PATH),
        "-filter_complex",
        "[1:v]scale=iw*8/100:-1,format=rgba,colorchannelmixer=aa=0.85[wm];"
        "[0:v][wm]overlay=W-w-20:20",
        "-codec:a", "copy",
        "-preset", "fast",
        "-crf", "18",
        output
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"FFmpeg error: {result.stderr[-200:]}")
    size = os.path.getsize(output) / (1024*1024)
    print(f"  watermarked: {size:.1f} MB")
    return output

# ─── GIT PUSH STATE ───────────────────────────────────────────────────────────
def push_state_to_github():
    """Push updated queue state to GitHub so Actions can pick it up."""
    print("\nPushing state to GitHub...")
    try:
        subprocess.run(["git", "-C", str(BASE_DIR), "add", "state/"], capture_output=True)
        subprocess.run(
            ["git", "-C", str(BASE_DIR), "commit", "-m",
             f"Laptop: processed {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            capture_output=True
        )
        result = subprocess.run(
            ["git", "-C", str(BASE_DIR), "push", "origin", "main"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("  state pushed to GitHub!")
            return True
        else:
            print(f"  git push issue: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"  git push failed: {e}")
        return False

# ─── TRIGGER GITHUB ACTIONS ───────────────────────────────────────────────────
def trigger_github_actions():
    """Trigger the upload workflow on GitHub Actions."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    r = requests.post(
        f"https://api.github.com/repos/{GITHUB_REPO}/actions/workflows/upload.yml/dispatches",
        headers=headers,
        json={"ref": "main"},
        timeout=15,
    )
    if r.status_code in [200, 204]:
        print("  GitHub Actions upload workflow triggered!")
        return True
    else:
        print(f"  trigger failed: {r.status_code}")
        return False

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — Laptop Pipeline (Download + Watermark only)")
    print(f"Started: {now}")
    print(f"{'='*60}")

    telegram(f"Laptop Pipeline Started!\n{now}\nDownloading + watermarking videos...")

    DOWNLOADS_DIR.mkdir(exist_ok=True)
    PROCESSED_DIR.mkdir(exist_ok=True)
    STATE_DIR.mkdir(exist_ok=True)

    # Step 1: Scan channels
    hours_back = get_scan_hours()
    monitor_channels(hours_back)

    # Load queue — resume interrupted + new queued
    queue = load_json(QUEUE_FILE, [])

    # Reset any interrupted mid-step statuses
    for item in queue:
        if item.get("status") in ["downloading", "watermarking"]:
            print(f"  Resuming interrupted: {item['title'][:50]}")
            item["status"] = "queued"
            for key in ["video_path", "processed_path", "thumbnail_path"]:
                p = item.get(key,"")
                if p and os.path.exists(p):
                    try: os.remove(p)
                    except: pass
                item[key] = ""

    to_process = [v for v in queue if v.get("status") in ["queued", "failed"]]
    save_json(QUEUE_FILE, queue)

    if not to_process:
        print("\nNo videos to process")
        telegram("No videos to process — queue empty.")
        return

    print(f"\n{len(to_process)} video(s) to download + watermark")
    telegram(f"{len(to_process)} videos to process\nLaptop needed for ~{len(to_process)*5} minutes\nClose laptop after this — GitHub handles upload!")

    # Get GitHub Release for uploading processed files
    print("\nConnecting to GitHub Release...")
    try:
        release_id, _ = get_or_create_release("processed-videos")
        print(f"  Release ready (ID: {release_id})")
    except Exception as e:
        telegram(f"GitHub Release setup failed: {e}")
        print(f"GitHub Release failed: {e}")
        return

    results = {"success": 0, "failed": 0}

    for v in to_process:
        vid_id = v["id"]
        title  = v["title"]
        mins   = v.get("duration_s",0) // 60

        print(f"\n{'─'*55}")
        print(f"#{v.get('rank','?')}: {title[:60]}")
        print(f"{mins}m | {v.get('views',0):,} views")

        def save_status(status, extra={}):
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = status
                    item.update(extra)
                    break
            save_json(QUEUE_FILE, queue)

        video_path = None
        thumb_path = None
        wm_path    = None

        try:
            # ── 1. Download ──
            print("\n[1/3] Downloading...")
            save_status("downloading")
            telegram(f"Downloading #{v.get('rank','?')}\n{title[:55]}\n{mins}min | {v.get('views',0):,} views")
            thumb_path = download_thumbnail(v.get("thumbnail_url",""), vid_id)
            video_path = download_video(vid_id, title)
            file_size  = os.path.getsize(video_path) / (1024*1024)
            save_status("downloaded", {"video_path": video_path, "thumbnail_path": thumb_path or ""})
            telegram(f"Downloaded! {file_size:.0f}MB\n{title[:50]}")

            # ── 2. Watermark ──
            print("\n[2/3] Adding watermark...")
            save_status("watermarking")
            telegram(f"Adding watermark...\n{title[:50]}")
            wm_path = add_watermark(video_path, vid_id, title)
            cleanup_file(video_path)
            video_path = None
            wm_size = os.path.getsize(wm_path) / (1024*1024)
            save_status("watermarked", {"processed_path": wm_path})
            telegram(f"Watermark added! {wm_size:.0f}MB\n{title[:50]}")

            # ── 3. Upload to GitHub Release ──
            print("\n[3/3] Uploading to GitHub Release...")
            save_status("uploading_to_release")
            telegram(f"Uploading to cloud storage...\n{title[:50]}\nThis takes a few minutes...")

            safe = safe_filename(title)
            video_filename = f"{vid_id}_{safe}.mp4"
            thumb_filename = f"{vid_id}_thumbnail.jpg"

            video_url = upload_to_github_release(wm_path, release_id, video_filename)
            thumb_url = upload_thumbnail_to_release(thumb_path, release_id, thumb_filename)

            # Cleanup local files — no longer needed after upload to release
            cleanup_file(wm_path)
            cleanup_file(thumb_path)
            wm_path    = None
            thumb_path = None

            # Mark as ready_for_upload — GitHub Actions picks this up
            save_status("ready_for_upload", {
                "github_video_url":  video_url,
                "github_thumb_url":  thumb_url or "",
                "processed_path":    "",
                "thumbnail_path":    "",
            })

            results["success"] += 1
            print(f"\nSUCCESS! Ready for GitHub Actions to upload to YouTube")
            telegram(
                f"Video Ready!\n"
                f"{title[:55]}\n"
                f"Uploaded to cloud storage\n"
                f"GitHub Actions will upload to YouTube automatically!"
            )

        except Exception as e:
            err = str(e)[:200]
            print(f"\nFAILED: {err}")
            results["failed"] += 1
            for path in [video_path, wm_path, thumb_path]:
                cleanup_file(path)
            save_status("failed", {"error": err, "video_path": "", "processed_path": "", "thumbnail_path": ""})
            telegram("Failed (skipping)\n" + title[:50] + "\n" + err[:100])

        time.sleep(2)

    # Push updated queue to GitHub
    print("\nPushing state to GitHub...")
    pushed = push_state_to_github()

    # Trigger GitHub Actions upload workflow
    print("Triggering GitHub Actions upload workflow...")
    triggered = trigger_github_actions()

    # Update run info
    save_json(RUN_INFO_FILE, {
        "last_run_date": datetime.datetime.now().isoformat(),
        "is_first_run": False
    })

    summary = (
        f"Laptop Job Done!\n\n"
        f"Processed: {results['success']} videos\n"
        f"Failed: {results['failed']} videos\n\n"
        f"State pushed to GitHub: {'Yes' if pushed else 'Check manually'}\n"
        f"Upload workflow triggered: {'Yes' if triggered else 'Check GitHub Actions'}\n\n"
        f"YOU CAN CLOSE THE LAPTOP NOW!\n"
        f"GitHub Actions will handle SEO + YouTube upload automatically."
    )
    print(f"\n{'='*60}")
    print(summary)
    telegram(summary)

if __name__ == "__main__":
    main()
