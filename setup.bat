@echo off
title Max Lyrical Hub - First Time Setup
color 0B

echo.
echo ============================================================
echo   MAX LYRICAL HUB - Windows Setup
echo   Run this ONCE to set everything up
echo ============================================================
echo.

REM ── Step 1: Check Python ──
echo [STEP 1] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python is NOT installed!
    echo.
    echo Please:
    echo 1. Go to https://python.org/downloads
    echo 2. Download Python 3.11
    echo 3. Install it - CHECK the box "Add Python to PATH"
    echo 4. Run this setup.bat again
    echo.
    pause
    exit
)
python --version
echo Python OK!

REM ── Step 2: Check FFmpeg ──
echo.
echo [STEP 2] Checking FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo FFmpeg not found - downloading...
    echo.
    echo Please download FFmpeg manually:
    echo 1. Go to https://www.gyan.dev/ffmpeg/builds/
    echo 2. Download "ffmpeg-release-essentials.zip"
    echo 3. Extract it
    echo 4. Copy ffmpeg.exe, ffprobe.exe to this folder: %~dp0
    echo 5. Run setup.bat again
    echo.
    pause
    exit
)
echo FFmpeg OK!

REM ── Step 3: Install Python packages ──
echo.
echo [STEP 3] Installing Python packages...
pip install --upgrade yt-dlp requests google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client Pillow
echo Packages installed!

REM ── Step 4: Create config file ──
echo.
echo [STEP 4] Creating config file...

if exist "laptop_config.json" (
    echo laptop_config.json already exists - skipping
) else (
    echo Creating laptop_config.json template...
    (
        echo {
        echo   "yt_api_keys": [
        echo     "PASTE_YOUR_YT_API_KEY_1_HERE",
        echo     "PASTE_YOUR_YT_API_KEY_2_HERE",
        echo     "PASTE_YOUR_YT_API_KEY_3_HERE",
        echo     "PASTE_YOUR_YT_API_KEY_4_HERE"
        echo   ],
        echo   "yt_oauth_json": "PASTE_YOUR_YT_OAUTH_JSON_HERE",
        echo   "openrouter_api_key": "PASTE_YOUR_OPENROUTER_KEY_HERE",
        echo   "telegram_bot_token": "PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE",
        echo   "telegram_chat_id": "PASTE_YOUR_TELEGRAM_CHAT_ID_HERE"
        echo }
    ) > laptop_config.json
    echo laptop_config.json created!
)

REM ── Step 5: Create folders ──
echo.
echo [STEP 5] Creating folders...
if not exist "downloads" mkdir downloads
if not exist "processed" mkdir processed
if not exist "state" mkdir state
if not exist "watermark" mkdir watermark
echo Folders ready!

REM ── Step 6: Cookies reminder ──
echo.
echo ============================================================
echo   SETUP ALMOST DONE! Two more things:
echo ============================================================
echo.
echo [ACTION 1] Edit laptop_config.json
echo   - Open laptop_config.json in Notepad
echo   - Fill in all your API keys and tokens
echo   - Save the file
echo.
echo [ACTION 2] Add YouTube cookies
echo   - Install Chrome extension: "Get cookies.txt LOCALLY"
echo   - Go to youtube.com while logged into your channel
echo   - Click extension - Export cookies
echo   - Save the file as "yt_cookies.txt" in THIS folder
echo.
echo ============================================================
echo   After doing both actions above, run run.bat to start!
echo ============================================================
echo.
pause
