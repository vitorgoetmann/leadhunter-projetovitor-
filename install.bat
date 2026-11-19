@echo off
echo.
echo  ==========================================
echo   LeadHunter - Instalacao automatica
echo  ==========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale em: https://www.python.org/downloads/
    echo        Marque a opcao "Add Python to PATH" durante a instalacao.
    pause
    exit /b 1
)

echo [OK] Python encontrado.

:: Install dependencies
echo.
echo [1/2] Instalando dependencias Python...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERRO] Falha ao instalar dependencias.
    pause
    exit /b 1
)
echo [OK] Dependencias instaladas.

:: Install Playwright browsers
echo.
echo [2/2] Instalando navegador Chromium para o scraper...
python -m playwright install chromium
if errorlevel 1 (
    echo [ERRO] Falha ao instalar Chromium.
    pause
    exit /b 1
)
echo [OK] Chromium instalado.

echo.
echo  ==========================================
echo   Instalacao concluida com sucesso!
echo   Execute: start.bat para iniciar o app.
echo  ==========================================
echo.
pause
