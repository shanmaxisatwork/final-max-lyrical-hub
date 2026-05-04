@echo off
:: ============================================================
:: MAX LYRICAL HUB - Auto Scheduler Installer
:: Run this ONCE to make everything fully automatic
:: After this, laptop just needs to be turned on - that's it!
:: ============================================================

:: Must run as Administrator
net session >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Please right-click install_scheduler.bat
    echo         and select "Run as Administrator"
    echo.
    pause
    exit /b 1
)

set FOLDER=%~dp0
set PYTHON=%FOLDER%venv\Scripts\pythonw.exe
set SCRIPT=%FOLDER%scripts\silent_runner.py

:: Check if virtual env exists, if not use system python
if not exist "%PYTHON%" (
    for /f "tokens=*" %%i in ('where pythonw 2^>nul') do set PYTHON=%%i
)
if "%PYTHON%"=="" (
    for /f "tokens=*" %%i in ('where python 2^>nul') do set PYTHON=%%i
)

echo.
echo ============================================================
echo   MAX LYRICAL HUB - Installing Auto Scheduler
echo ============================================================
echo.
echo Folder: %FOLDER%
echo Python: %PYTHON%
echo Script: %SCRIPT%
echo.

:: ── Delete old tasks if they exist ──
schtasks /delete /tn "MaxLyricalHub_Startup" /f >nul 2>&1
schtasks /delete /tn "MaxLyricalHub_Morning" /f >nul 2>&1
schtasks /delete /tn "MaxLyricalHub_Midday" /f >nul 2>&1
schtasks /delete /tn "MaxLyricalHub_Evening" /f >nul 2>&1

echo [1/5] Creating STARTUP task (runs 5 min after boot)...
:: Runs 5 minutes after ANY user logs in, hidden, no UI
schtasks /create ^
  /tn "MaxLyricalHub_Startup" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc ONLOGON ^
  /delay 0005:00 ^
  /ru "%USERNAME%" ^
  /rl HIGHEST ^
  /f >nul 2>&1
if errorlevel 1 (
    echo [WARN] Startup task creation had an issue - trying alternate method...
    schtasks /create /tn "MaxLyricalHub_Startup" /tr "\"%PYTHON%\" \"%SCRIPT%\"" /sc ONLOGON /delay 0005:00 /f
) else (
    echo       Done!
)

echo [2/5] Creating MORNING task (7:35 AM)...
schtasks /create ^
  /tn "MaxLyricalHub_Morning" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc DAILY ^
  /st 07:35 ^
  /ru "%USERNAME%" ^
  /f >nul 2>&1
echo       Done!

echo [3/5] Creating MIDDAY task (10:05 AM)...
schtasks /create ^
  /tn "MaxLyricalHub_Midday" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc DAILY ^
  /st 10:05 ^
  /ru "%USERNAME%" ^
  /f >nul 2>&1
echo       Done!

echo [4/5] Creating EVENING task (7:05 PM)...
schtasks /create ^
  /tn "MaxLyricalHub_Evening" ^
  /tr "\"%PYTHON%\" \"%SCRIPT%\"" ^
  /sc DAILY ^
  /st 19:05 ^
  /ru "%USERNAME%" ^
  /f >nul 2>&1
echo       Done!

echo [5/5] Verifying tasks...
schtasks /query /tn "MaxLyricalHub_Startup" >nul 2>&1 && echo       Startup task: OK || echo       Startup task: FAILED
schtasks /query /tn "MaxLyricalHub_Morning" >nul 2>&1 && echo       Morning task: OK || echo       Morning task: FAILED
schtasks /query /tn "MaxLyricalHub_Midday"  >nul 2>&1 && echo       Midday task:  OK || echo       Midday task:  FAILED
schtasks /query /tn "MaxLyricalHub_Evening" >nul 2>&1 && echo       Evening task: OK || echo       Evening task: FAILED

echo.
echo ============================================================
echo   AUTO SCHEDULER INSTALLED SUCCESSFULLY!
echo ============================================================
echo.
echo What happens now:
echo   - Laptop turns on at 7:30 AM? Pipeline runs at 7:35 AM
echo   - Laptop turns on at 10:00 AM? Pipeline runs at 10:05 AM
echo   - Laptop turns on at 7:00 PM? Pipeline runs at 7:05 PM
echo   - Laptop restarts? Pipeline runs 5 min after boot
echo.
echo What dad sees: NOTHING (completely silent background)
echo What you see:  Telegram messages on your phone
echo.
echo The pipeline runs ONCE per day maximum.
echo Even if laptop restarts 10 times, it only processes once.
echo.
echo To STOP the automation, run: uninstall_scheduler.bat
echo.
pause
