@echo off
rem Chạy server local với database SQLite (backend\python_quest.db), không đụng tới Supabase.
rem Tài khoản admin lấy từ ADMIN_USERNAME / ADMIN_PASSWORD trong file .env (nếu có).
cd /d "%~dp0backend"
set DATABASE_URL=sqlite:///./python_quest.db
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
