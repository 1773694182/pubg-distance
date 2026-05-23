@echo off
setlocal
py -3 -m pip install -r requirements.txt || exit /b 1
py -3 -m PyInstaller --onefile --console --uac-admin --name PUBGDistanceTool-Global pubg_distance_tool.py || exit /b 1
echo.
echo Build finished. EXE path: dist\PUBGDistanceTool-Global.exe
pause
