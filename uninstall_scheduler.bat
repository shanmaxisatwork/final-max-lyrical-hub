@echo off
:: Remove all Max Lyrical Hub scheduled tasks
net session >nul 2>&1
if errorlevel 1 (
    echo Please run as Administrator
    pause
    exit /b 1
)

echo Removing Max Lyrical Hub scheduled tasks...
schtasks /delete /tn "MaxLyricalHub_Startup" /f >nul 2>&1 && echo Startup task removed
schtasks /delete /tn "MaxLyricalHub_Morning" /f >nul 2>&1 && echo Morning task removed
schtasks /delete /tn "MaxLyricalHub_Midday"  /f >nul 2>&1 && echo Midday task removed
schtasks /delete /tn "MaxLyricalHub_Evening" /f >nul 2>&1 && echo Evening task removed
echo.
echo All tasks removed! Automation is OFF.
pause
