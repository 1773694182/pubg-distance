@echo off
setlocal
python -m pip install -r requirements.txt
python -m PyInstaller --onefile --windowed --name PUBGDistanceTool-Global pubg_distance_tool.py
echo.
echo Build finished. EXE path: dist\PUBGDistanceTool-Global.exe
pause
