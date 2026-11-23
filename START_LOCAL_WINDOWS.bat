@echo off
cd /d "%~dp0"
where py >nul 2>&1 && (start http://localhost:8787 & py -m http.server 8787 & exit /b)
where python >nul 2>&1 && (start http://localhost:8787 & python -m http.server 8787 & exit /b)
echo Install Python first from python.org or host on GitHub Pages / Render.
pause
