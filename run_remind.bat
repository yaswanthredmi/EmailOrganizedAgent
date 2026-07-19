@echo off
REM DDL 提醒：更新「提醒」字段，若配置了 webhook 则推送。
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    set "PY=python"
)
"%PY%" src\remind.py >> remind.log 2>&1
