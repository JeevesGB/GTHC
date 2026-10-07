@echo off
where pythonw >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" pythonw src\launcher.py
    exit /b 0
)
where pyw >nul 2>&1
if %ERRORLEVEL%==0 (
    start "" pyw src\launcher.py
    exit /b 0
)
python src\launcher.py
if errorlevel 1 pause