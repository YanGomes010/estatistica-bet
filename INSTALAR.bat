@echo off
chcp 65001 > nul 2>&1
title Instalacao - Football Analytics

echo.
echo ============================================
echo   FOOTBALL ANALYTICS - INSTALADOR
echo ============================================
echo.

python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado!
    echo.
    echo Acesse: https://www.python.org/downloads/
    echo Baixe Python 3.11 ou superior.
    echo IMPORTANTE: marque "Add Python to PATH" na instalacao!
    echo.
    pause
    exit /b 1
)

echo Python encontrado:
python --version
echo.

if not exist ".env" (
    echo Criando arquivo .env...
    copy ".env.example" ".env" > nul
    echo Arquivo .env criado!
    echo.
    echo IMPORTANTE: Edite o .env com suas chaves de API.
    echo.
) else (
    echo Arquivo .env ja existe.
)

echo.
echo Instalando dependencias...
echo Aguarde, pode demorar alguns minutos...
echo.

pip install streamlit plotly pandas numpy requests python-dotenv pytz tenacity beautifulsoup4 lxml httpx pydantic tqdm

if %errorlevel% neq 0 (
    echo.
    echo ERRO na instalacao. Tente manualmente:
    echo   pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo Instalando soccerdata (FBref/xG - opcional)...
pip install soccerdata > nul 2>&1
if %errorlevel% neq 0 (
    echo soccerdata nao instalado - xG do FBref nao disponivel.
    echo O app funciona normalmente sem ele.
) else (
    echo soccerdata instalado!
)

echo.
echo ============================================
echo   INSTALACAO CONCLUIDA COM SUCESSO!
echo ============================================
echo.
echo PROXIMOS PASSOS:
echo.
echo 1. Abra o arquivo .env com o Bloco de Notas
echo    e cole sua chave de API na linha:
echo    FOOTBALL_DATA_API_KEY=sua_chave_aqui
echo.
echo    Chave gratuita em:
echo    https://www.football-data.org/client/register
echo.
echo 2. Execute: INICIAR.bat
echo.
pause
