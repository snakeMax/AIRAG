@echo off
REM Build the Windows installer locally (needs Python 3.10+ and Inno Setup 6).
cd /d "%~dp0"
if not exist ".venv-build\Scripts\python.exe" py -3 -m venv .venv-build 2>nul || python -m venv .venv-build
".venv-build\Scripts\python.exe" -m pip install -r requirements.txt -r requirements-build.txt || goto :fail
".venv-build\Scripts\python.exe" tools\build.py %* || goto :fail
echo.
echo Done. See the dist folder.
pause
exit /b 0
:fail
echo Build failed.
pause
exit /b 1
