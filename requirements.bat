@echo off
setlocal
cd /d "%~dp0"

echo === GT Hybrid Creator: installing requirements ===
echo.

rem Find Python: prefer the "py" launcher, fall back to "python"
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY (
    where python >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo ERROR: Python was not found on your PATH.
    echo Install Python from https://www.python.org/downloads/ and tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

if not exist "requirements.txt" (
    echo ERROR: requirements.txt not found in %CD%
    echo.
    pause
    exit /b 1
)

echo Using: %PY%
%PY% --version
echo.

echo Upgrading pip...
%PY% -m pip install --upgrade pip
if errorlevel 1 goto :fail

echo.
echo Installing from requirements.txt...
%PY% -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo === Done. All requirements installed. ===
echo.
pause
exit /b 0

:fail
echo.
echo === Install failed. See the error above. ===
echo.
pause
exit /b 1