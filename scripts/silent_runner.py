#!/usr/bin/env python3
"""
SILENT BACKGROUND RUNNER
- Runs completely hidden, no windows, no popups
- Checks if pipeline already ran today before starting
- Checks if laptop has been on for at least 5 minutes
- Logs everything to a file instead of screen
- Only output = Telegram messages on your phone
"""

import os
import sys
import json
import time
import datetime
import subprocess
import logging
from pathlib import Path

# ── Setup logging to file (no console output) ──
BASE_DIR = Path(__file__).parent.parent
LOG_FILE = BASE_DIR / "state" / "runner.log"
BASE_DIR.joinpath("state").mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger()

# Also suppress all stdout/stderr (dad sees nothing)
sys.stdout = open(BASE_DIR / "state" / "stdout.log", "a", encoding="utf-8")
sys.stderr = open(BASE_DIR / "state" / "stderr.log", "a", encoding="utf-8")

RUN_INFO_FILE = BASE_DIR / "state" / "run_info.json"

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

def already_ran_today():
    """Check if full pipeline already ran today."""
    run_info = load_json(RUN_INFO_FILE, {})
    last_run = run_info.get("last_run_date", "")
    if not last_run:
        return False
    try:
        last_dt = datetime.datetime.fromisoformat(last_run)
        today   = datetime.datetime.now().date()
        if last_dt.date() == today:
            log.info(f"Already ran today at {last_dt.strftime('%H:%M')} — skipping")
            return True
    except:
        pass
    return False

def has_queued_videos():
    """Check if there are videos waiting to be downloaded+uploaded."""
    queue_file = BASE_DIR / "state" / "download_queue.json"
    try:
        with open(queue_file) as f:
            queue = json.load(f)
        queued = [v for v in queue if isinstance(v, dict) and v.get("status") == "queued"]
        log.info(f"Queued videos: {len(queued)}")
        return len(queued) > 0
    except:
        # No queue file = nothing to process
        return False

def should_run_full_pipeline():
    """
    Decide whether to run full pipeline or just monitor.
    Full pipeline = download + watermark + SEO + upload (heavy, 1-2 hours)
    Monitor only  = scan channels, update queue (light, 2 minutes)
    
    Run FULL pipeline only if:
    - Has NOT run today already
    - There ARE videos queued to process
    
    Run MONITOR ONLY if:
    - Already ran today (skip everything)
    - No queued videos (just scan for new ones)
    """
    if already_ran_today():
        log.info("Already ran full pipeline today — skipping all")
        return "skip"
    
    if has_queued_videos():
        log.info("Queued videos found — running full pipeline")
        return "full"
    else:
        log.info("No queued videos — running monitor only (light scan)")
        return "monitor_only"

def get_uptime_minutes():
    """Get how long the laptop has been on (Windows)."""
    try:
        import ctypes
        tick_ms = ctypes.windll.kernel32.GetTickCount64()
        return tick_ms / 1000 / 60
    except:
        # Fallback: assume enough time has passed
        return 10

def is_good_time_to_run():
    """
    Check if current time is within one of dad's usage windows.
    We run ONLY during these windows so pipeline uses laptop during active times.
    Windows (IST):
      7:30 AM - 8:30 AM
      10:00 AM - 2:00 PM
      7:00 PM - 9:00 PM
    """
    now = datetime.datetime.now()
    h = now.hour
    m = now.minute
    current = h * 60 + m  # minutes since midnight

    windows = [
        (7*60+30,  8*60+30),   # 7:30 AM - 8:30 AM
        (10*60+0,  14*60+0),   # 10:00 AM - 2:00 PM
        (19*60+0,  21*60+0),   # 7:00 PM - 9:00 PM
    ]
    for start, end in windows:
        if start <= current <= end:
            return True
    return False

def main():
    log.info("="*50)
    log.info("Silent runner started")

    # Check 1: Has laptop been on for at least 5 minutes?
    uptime = get_uptime_minutes()
    log.info(f"Laptop uptime: {uptime:.1f} minutes")
    if uptime < 5:
        wait = (5 - uptime) * 60
        log.info(f"Waiting {wait:.0f} seconds for 5-min uptime...")
        time.sleep(wait)

    # Check 2: Is this a good time? (within usage windows)
    if not is_good_time_to_run():
        log.info("Not within active time window — skipping")
        return

    # Check 3: What mode to run?
    mode = should_run_full_pipeline()

    if mode == "skip":
        log.info("Skipping — already ran full pipeline today")
        return

    elif mode == "monitor_only":
        # Light scan only — just checks channels for new videos
        # Takes ~2 minutes, completely silent, very low CPU
        log.info("Running monitor only (no queued videos to process)")
        monitor_script = str(BASE_DIR / "scripts" / "1_monitor_channels.py")
        python_exe = sys.executable
        try:
            result = subprocess.run(
                [python_exe, monitor_script],
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR),
            )
            log.info(f"Monitor finished with code: {result.returncode}")
            if result.stdout:
                log.info(f"STDOUT:\n{result.stdout[-1000:]}")
        except Exception as e:
            log.error(f"Monitor failed: {e}")

    elif mode == "full":
        # Full pipeline — download + watermark + SEO + upload
        # Takes 1-2 hours but completely silent
        log.info("Running FULL pipeline")
        pipeline_script = str(BASE_DIR / "scripts" / "laptop_pipeline.py")
        python_exe = sys.executable
        try:
            result = subprocess.run(
                [python_exe, pipeline_script],
                capture_output=True,
                text=True,
                cwd=str(BASE_DIR),
            )
            log.info(f"Pipeline finished with code: {result.returncode}")
            if result.stdout:
                log.info(f"STDOUT:\n{result.stdout[-2000:]}")
            if result.stderr:
                log.warning(f"STDERR:\n{result.stderr[-1000:]}")
        except Exception as e:
            log.error(f"Pipeline failed: {e}")

    log.info("Silent runner done")

if __name__ == "__main__":
    main()
