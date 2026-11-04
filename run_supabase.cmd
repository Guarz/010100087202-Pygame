@echo off
rem Chạy server local nhưng dùng database PostgreSQL trên Supabase theo DATABASE_URL trong file .env.
cd /d "%~dp0backend"
set PYTHONUTF8=1
"%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8001
