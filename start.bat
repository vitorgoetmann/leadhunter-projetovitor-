@echo off
echo.
echo  ==========================================
echo   LeadHunter - Iniciando servidor...
echo  ==========================================
echo.
echo  Acesse no navegador: http://localhost:8000
echo  Pressione Ctrl+C para parar.
echo.
cd /d "%~dp0"
python app.py
pause
