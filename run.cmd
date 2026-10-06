@echo off
cd /d "%~dp0"
set "HERE=%~dp0"

set "PY="
if exist "%HERE%tools\python\python.exe" set "PY=%HERE%tools\python\python.exe"
if not defined PY if exist "C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe" set "PY=C:\Users\Administrator\AppData\Local\hermes\hermes-agent\venv\Scripts\python.exe"
if not defined PY if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe"
if not defined PY if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe" set "PY=C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
if not defined PY (
  where python >nul 2>nul
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  echo Python 3.8+ with tkinter not found.
  echo Install Python then: pip install -r requirements.txt
  pause
  exit /b 1
)

if not exist "%HERE%config.json" (
  copy /y "%HERE%config.example.json" "%HERE%config.json" >nul
  echo Created config.json. Fill fofa_key and start again.
  notepad "%HERE%config.json"
  pause
  exit /b 1
)

"%PY%" "%HERE%ui.py"
if errorlevel 1 (
  echo.
  echo Start failed. See crash.log in this folder.
  pause
)
