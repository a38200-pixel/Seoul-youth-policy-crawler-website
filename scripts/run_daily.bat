@echo off
setlocal
cd /d "%~dp0.."
set "PYTHON=%USERPROFILE%\anaconda3\envs\web_crawling\python.exe"
"%PYTHON%" -m backend.crawler.crawl --daily --headless
echo %date% %time% exit=%ERRORLEVEL% >> backend\logs\scheduler.log
endlocal