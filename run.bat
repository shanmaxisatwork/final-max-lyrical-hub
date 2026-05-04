@echo off
title Max Lyrical Hub - Pipeline Runner
color 0A

echo.
echo ============================================================
echo   MAX LYRICAL HUB - Automated Pipeline
echo ============================================================
echo.

REM Check Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found!
    echo Please install Python from https://python.org
    echo Make sure to check "Add Python to PATH" during install
    pause
    exit
)

REM Check if config exists
if not exist "laptop_config.json" (
    echo [ERROR] laptop_config.json not found!
    echo Please run setup.bat first
    pause
    exit
)

REM Check if FFmpeg is installed
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] FFmpeg not found!
    echo Please run setup.bat first to install FFmpeg
    pause
    exit
)

REM Install/update Python packages
echo [1/3] Checking Python packages...
pip install -q --upgrade yt-dlp requests google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
echo       Done!

echo.
echo [2/3] Syncing latest queue from GitHub...
git pull origin main --quiet 2>nul || echo       (Git sync skipped - running with local state)

echo.
echo [3/3] Starting pipeline...
echo.
echo  Telegram alerts will come to your phone at every step!
echo  You can minimize this window and do other things.
echo.
echo ============================================================
echo.

python scripts/laptop_pipeline.py

echo.
echo ============================================================
echo   Pipeline finished! Check Telegram for results.
echo ============================================================
echo.

REM Push updated state back to GitHub
echo Saving state to GitHub...
git add state/ >nul 2>&1
git commit -m "Laptop run: %date% %time%" >nul 2>&1
git push origin main --quiet 2>nul || echo (Git push skipped)

echo Done! This window will close in 10 seconds...
timeout /t 10
