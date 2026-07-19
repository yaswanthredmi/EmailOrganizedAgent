@echo off
REM 发送飞书里标记为「待发送」的回复。供 Windows 计划任务调用。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"%PY%" src\send.py >> send.log 2>&1
