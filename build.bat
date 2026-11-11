@echo off
rem DriverWatch.exe uretir (dist klasorune)
cd /d "%~dp0"
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --onefile --windowed --name DriverWatch --icon icon.ico --add-data "icon.ico;." --collect-submodules selenium --collect-data selenium --collect-binaries selenium main.py
