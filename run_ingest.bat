@echo off
REM 读取新邮件 -> AI 总结 -> 写入飞书。供 Windows 计划任务调用。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"%PY%" src\ingest.py >> ingest.log 2>&1
