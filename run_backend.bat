@echo off
"C:\Program Files\Python310\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
