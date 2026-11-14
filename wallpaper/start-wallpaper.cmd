@echo off
rem Starts the Garden Wallpaper server and opens make.html in your browser.
rem Keep this window open while you preview and render; close it when you are done.
cd /d "%~dp0"
where py >nul 2>nul && (py server.py --open) || (python server.py --open)
pause
