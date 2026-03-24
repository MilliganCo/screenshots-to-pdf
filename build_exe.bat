@echo off
chcp 65001 >nul
echo Сборка Screenshots_to_PDF.exe...
python -m pip install pyinstaller --quiet 2>nul
python -m PyInstaller --onefile --name "Screenshots_to_PDF" --windowed --clean merge_screenshots_to_pdf.py
echo.
echo Готово! EXE: dist\Screenshots_to_PDF.exe
pause
