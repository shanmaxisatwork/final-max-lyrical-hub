#!/usr/bin/env python3
"""
GITHUB ACTIONS UPLOAD SCRIPT
Runs in cloud after laptop finishes download+watermark.
1. Reads queue for videos with status "ready_for_upload"
2. Downloads watermarked video from GitHub Release
3. Generates SEO via OpenRouter AI
4. Uploads to YouTube with thumbnail + scheduling
5. Sends Telegram alerts
6. Cleans up GitHub Release assets
"""

import os
import json
import time
import datetime
import requests
import tempfile
from pathlib import Path
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ─── CONFIG ───────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
YT_OAUTH_JSON      = os.environ["YT_OAUTH_JSON"]
GITHUB_TOKEN       = os.environ.get("GITHUB_TOKEN_CUSTOM") or os.environ.get("GITHUB_TOKEN","")
GITHUB_REPO        = os.environ.get("GITHUB_REPOSITORY","")

QUEUE_FILE = "state/download_queue.json"

# Upload schedule: spread across 2 days, 5 slots per day
# 5 upload slots per day (IST times → UTC)
# 3:00PM, 5:00PM, 7:00PM, 9:00PM, 11:00PM IST
UPLOAD_SLOTS_UTC = ["09:30", "11:30", "13:30", "15:30", "17:30"]
MAX_PER_DAY = 5
SCHEDULE_DAYS = 3

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

def calculate_day_distribution(total_videos):
    """
    Divide videos across SCHEDULE_DAYS days, max MAX_PER_DAY per day.
    Returns list of video counts per day e.g. [5, 5, 5] or [3, 3, 3].
    """
    videos_to_schedule = min(total_videos, MAX_PER_DAY * SCHEDULE_DAYS)
    per_day   = videos_to_schedule // SCHEDULE_DAYS
    remainder = videos_to_schedule % SCHEDULE_DAYS
    day_counts = []
    for day in range(SCHEDULE_DAYS):
        count = per_day + (1 if day < remainder else 0)
        day_counts.append(count)
    print(f"  Schedule distribution: {total_videos} videos -> {day_counts} across {SCHEDULE_DAYS} days")
    return day_counts

def get_schedule_time(day_offset, slot_in_day):
    """
    Get UTC publish time for a video.
    day_offset: 0=today, 1=tomorrow, 2=day after
    slot_in_day: 0-4 (which of the 5 daily time slots)
    """
    now_utc = datetime.datetime.utcnow()
    today   = now_utc.date()
    h, m    = map(int, UPLOAD_SLOTS_UTC[slot_in_day].split(":"))
    utc_dt  = datetime.datetime(today.year, today.month, today.day, h, m, 0)
    utc_dt += datetime.timedelta(days=day_offset)
    # If time already passed, push to next available slot
    if utc_dt <= now_utc:
        utc_dt += datetime.timedelta(days=1)
    ist_dt  = utc_dt + datetime.timedelta(hours=5, minutes=30)
    return utc_dt.strftime("%Y-%m-%dT%H:%M:%S.000Z"), ist_dt.strftime("%d %b %Y, %I:%M %p IST")

# ─── DOWNLOAD FROM GITHUB RELEASE ─────────────────────────────────────────────
def download_from_release(url, suffix=".mp4"):
    """Download a file from GitHub Release URL to a temp file."""
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    r = requests.get(url, headers=headers, stream=True, timeout=600)
    r.raise_for_status()
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in r.iter_content(chunk_size=1024*1024):
        if chunk:
            tmp.write(chunk)
    tmp.close()
    size = os.path.getsize(tmp.name) / (1024*1024)
    print(f"  downloaded from release: {size:.1f}MB -> {tmp.name}")
    return tmp.name

def delete_release_asset(asset_url):
    """Delete a file from GitHub Release after uploading to YouTube."""
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
    }
    # Get asset ID from URL
    parts = asset_url.split("/")
    try:
        # List assets to find the one to delete
        repo_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/tags/processed-videos"
        r = requests.get(repo_url, headers=headers, timeout=15)
        if r.status_code == 200:
            release_id = r.json()["id"]
            assets = requests.get(
                f"https://api.github.com/repos/{GITHUB_REPO}/releases/{release_id}/assets",
                headers=headers, timeout=15
            ).json()
            filename = asset_url.split("/")[-1]
            for asset in assets:
                if asset["name"] == filename:
                    requests.delete(
                        f"https://api.github.com/repos/{GITHUB_REPO}/releases/assets/{asset['id']}",
                        headers=headers, timeout=15
                    )
                    print(f"  deleted release asset: {filename}")
                    return
    except Exception as e:
        print(f"  [WARN] Could not delete release asset: {e}")

# ─── SEO GENERATION ───────────────────────────────────────────────────────────
def generate_seo(title, description, tags, channel_name):
    tags_str = ", ".join(tags[:20]) if tags else "music, lyrics"
    prompt = f"""You are a YouTube SEO expert. Generate metadata for Max Lyrical Hub channel.

ORIGINAL VIDEO:
- Title: {title}
- Channel: {channel_name}
- Tags: {tags_str}
- Description: {description[:300]}

Generate:
1. TITLE: SEO-optimized (max 100 chars), keep song/artist name
2. DESCRIPTION: Opening hook, credit to {channel_name}, search terms section with 15 keywords, 25 hashtags, subscribe line
3. TAGS: 35 comma-separated YouTube tags

Respond ONLY in JSON (no markdown): {{"title":"...","description":"...","tags":["..."]}}"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": f"https://github.com/{GITHUB_REPO}",
    }
    models = [
        "google/gemini-flash-1.5",
        "meta-llama/llama-3.1-8b-instruct:free",
        "mistralai/mistral-7b-instruct:free",
    ]
    for model in models:
        try:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers,
                json={"model": model, "messages": [{"role":"user","content":prompt}], "max_tokens": 1500},
                timeout=30,
            )
            r.raise_for_status()
            content = r.json()["choices"][0]["message"]["content"].strip()
            content = content.replace("```json","").replace("```","").strip()
            seo = json.loads(content)
            print(f"  SEO done with {model}")
            return seo
        except Exception as e:
            print(f"  {model} failed: {e}")
            continue

    return {
        "title": title[:90] + " | Max Lyrical Hub",
        "description": f"Music\nOriginal: {channel_name}\n#MaxLyricalHub #Music #Lyrics",
        "tags": (tags[:20] if tags else []) + ["Max Lyrical Hub","music","lyrics"],
    }

# ─── YOUTUBE UPLOAD ───────────────────────────────────────────────────────────
def get_youtube_service():
    creds_data = json.loads(YT_OAUTH_JSON)
    creds = Credentials(
        token=creds_data.get("token"),
        refresh_token=creds_data.get("refresh_token"),
        token_uri=creds_data.get("token_uri","https://oauth2.googleapis.com/token"),
        client_id=creds_data.get("client_id"),
        client_secret=creds_data.get("client_secret"),
        scopes=["https://www.googleapis.com/auth/youtube.upload",
                "https://www.googleapis.com/auth/youtube"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        print("  OAuth token refreshed")
    return build("youtube", "v3", credentials=creds)

def upload_video(youtube, video_path, title, description, tags, category_id, schedule_time):
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:500] if isinstance(tags,list) else [],
            "categoryId": category_id or "10",
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": schedule_time,
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(video_path, mimetype="video/mp4", resumable=True, chunksize=50*1024*1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    print(f"  uploading to YouTube...")
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress()*100)
            if pct % 25 == 0:
                print(f"     {pct}%")
    return response.get("id")

def set_thumbnail(youtube, yt_video_id, thumb_path):
    if not thumb_path or not os.path.exists(thumb_path):
        return False
    try:
        media = MediaFileUpload(thumb_path, mimetype="image/jpeg")
        youtube.thumbnails().set(videoId=yt_video_id, media_body=media).execute()
        print(f"  thumbnail set!")
        return True
    except Exception as e:
        print(f"  thumbnail failed: {e}")
        return False

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*60}")
    print(f"MAX LYRICAL HUB — GitHub Actions Uploader")
    print(f"Started: {now}")
    print(f"{'='*60}\n")

    queue    = load_json(QUEUE_FILE, [])
    to_upload = [v for v in queue if isinstance(v,dict) and v.get("status") == "ready_for_upload"]

    if not to_upload:
        print("No videos ready for upload")
        telegram("Uploader: No videos ready — laptop may still be processing.")
        return

    total = len(to_upload)
    print(f"{total} video(s) ready to upload to YouTube")

    # Calculate smart distribution across 3 days
    day_counts = calculate_day_distribution(total)
    print(f"Schedule plan: {day_counts}")

    # Build schedule map: video index -> (day_offset, slot_in_day)
    schedule_map = []
    for day_offset, count in enumerate(day_counts):
        for slot in range(count):
            schedule_map.append((day_offset, slot))

    # Build Telegram summary of schedule plan
    plan_lines = ["GitHub Actions: Uploading to YouTube!"]
    plan_lines.append(f"Total: {total} videos across {SCHEDULE_DAYS} days:")
    for i, count in enumerate(day_counts):
        day_label = ["Today", "Tomorrow", "Day After"][i]
        plan_lines.append(f"  {day_label}: {count} videos")
    telegram("\n".join(plan_lines))

    try:
        youtube = get_youtube_service()
        print("YouTube OAuth ready\n")
    except Exception as e:
        telegram(f"YouTube auth failed: {e}")
        return

    results = {"success": 0, "failed": 0}

    for idx, v in enumerate(to_upload):
        vid_id    = v["id"]
        title     = v["title"]
        video_url = v.get("github_video_url","")
        thumb_url = v.get("github_thumb_url","")

        # Get this video's day and slot from schedule map
        if idx < len(schedule_map):
            day_offset, slot_in_day = schedule_map[idx]
        else:
            # Extra videos beyond 15: save for next scan
            print(f"  Skipping #{idx+1} — beyond 3-day capacity, saving for next run")
            continue

        print(f"\n{'─'*55}")
        print(f"#{v.get('rank','?')}: {title[:60]}")
        print(f"  Scheduled: Day {day_offset+1}, Slot {slot_in_day+1}")

        def save_status(status, extra={}):
            for item in queue:
                if item["id"] == vid_id:
                    item["status"] = status
                    item.update(extra)
                    break
            save_json(QUEUE_FILE, queue)

        video_tmp = None
        thumb_tmp = None

        try:
            # ── 1. Download from GitHub Release ──
            print("\n[1/3] Downloading from GitHub Release...")
            telegram(f"Uploading #{v.get('rank','?')}\n{title[:55]}\nFetching from storage...")
            video_tmp = download_from_release(video_url, ".mp4")
            if thumb_url:
                thumb_tmp = download_from_release(thumb_url, ".jpg")

            # ── 2. Generate SEO ──
            print("\n[2/3] Generating SEO...")
            seo       = generate_seo(title, v.get("description_raw",""), v.get("tags",[]), v.get("channel_name",""))
            seo_title = seo.get("title", title)
            seo_desc  = seo.get("description","")
            seo_tags  = seo.get("tags",[])
            print(f"  Title: {seo_title}")

            # ── 3. Upload to YouTube with smart schedule time ──
            print("\n[3/3] Uploading to YouTube...")
            schedule_utc, schedule_ist = get_schedule_time(day_offset, slot_in_day)
            telegram(f"Uploading to YouTube...\n{seo_title[:55]}\nScheduled: {schedule_ist}")

            yt_vid_id = upload_video(
                youtube, video_tmp, seo_title, seo_desc,
                seo_tags, v.get("category_id","10"), schedule_utc
            )
            set_thumbnail(youtube, yt_vid_id, thumb_tmp)
            yt_link = f"https://www.youtube.com/watch?v={yt_vid_id}"
            print(f"\nUPLOADED! {yt_link}")
            print(f"Goes live: {schedule_ist}")

            # ── 4. Cleanup ──
            for tmp in [video_tmp, thumb_tmp]:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
            if video_url: delete_release_asset(video_url)
            if thumb_url: delete_release_asset(thumb_url)

            save_status("uploaded", {
                "yt_video_id":  yt_vid_id,
                "yt_link":      yt_link,
                "scheduled_at": schedule_ist,
                "seo_title":    seo_title,
            })
            results["success"] += 1
            telegram(
                f"UPLOAD COMPLETE!\n"
                f"{seo_title[:60]}\n"
                f"Goes live: {schedule_ist}\n"
                f"{yt_link}"
            )

        except Exception as e:
            err = str(e)[:200]
            print(f"\nFAILED: {err}")
            results["failed"] += 1
            for tmp in [video_tmp, thumb_tmp]:
                if tmp and os.path.exists(tmp):
                    try: os.remove(tmp)
                    except: pass
            save_status("upload_failed", {"error": err})
            telegram("Upload Failed\n" + title[:50] + "\n" + err[:100])

        time.sleep(3)

    summary = (
        f"All Done!\n\n"
        f"Uploaded: {results['success']}\n"
        f"Failed: {results['failed']}\n"
        f"Videos scheduled across next 2 days!\n"
        f"Max Lyrical Hub is growing!"
    )
    print(f"\n{summary}")
    telegram(summary)

if __name__ == "__main__":
    main()
