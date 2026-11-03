@echo off
rem Chạy server local ở chế độ dev (đăng nhập chỉ cần email, admin là admin@local.dev).
cd /d "%~dp0backend"
set AUTH_MODE=dev
set ADMIN_EMAILS=admin@local.dev
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
