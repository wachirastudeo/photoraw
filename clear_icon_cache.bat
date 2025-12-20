@echo off
echo Clearing Windows Icon Cache...
echo.

REM Close Explorer
taskkill /F /IM explorer.exe

REM Delete icon cache files
del /A /Q "%localappdata%\IconCache.db"
del /A /F /Q "%localappdata%\Microsoft\Windows\Explorer\iconcache*"

REM Restart Explorer
start explorer.exe

echo.
echo Icon cache cleared successfully!
echo Please wait a few seconds for Explorer to restart...
timeout /t 3
