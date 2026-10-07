@echo off
REM Launch without a console window (pythonw). Falls back to pyw, then python.
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
REM Last resort: visible console so errors are still readable
python src\launcher.py
if errorlevel 1 pause
