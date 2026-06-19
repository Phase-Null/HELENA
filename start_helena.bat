@echo off
REM BUGFIX #36: was hardcoded to C:\users\franc\onedrive\desktop\HELENA;
REM now uses %~dp0 to reference the directory where this script lives
echo Starting AEGIS...
start "AEGIS" cmd /k "cd /d %~dp0aegis_core && target\release\aegis.exe"
echo Waiting for AEGIS to initialise...
timeout /t 5 /nobreak
echo Starting HELENA...
cd /d %~dp0
python start_helena.py
