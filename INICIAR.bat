@echo off
chcp 65001 > nul 2>&1
title Football Analytics
echo.
echo ============================================
echo   FOOTBALL ANALYTICS - INICIANDO...
echo ============================================
echo.

rem --- Detecta o comando python correto ---
set PYTHON=python
py --version > nul 2>&1 && set PYTHON=py

%PYTHON% --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ERRO: Python nao encontrado.
    echo Execute INSTALAR.bat primeiro.
    pause
    exit /b 1
)

%PYTHON% -c "import streamlit" > nul 2>&1
if %errorlevel% neq 0 (
    echo Instalando dependencias...
    %PYTHON% -m pip install streamlit pandas plotly requests python-dotenv tenacity
)

if not exist ".env" (
    echo Arquivo .env nao encontrado.
    if exist ".env.example" (copy ".env.example" ".env" > nul)
    echo Configure sua chave de API no arquivo .env
    notepad .env
    pause
)

echo Limpando cache Python...
%PYTHON% -c "import shutil; from pathlib import Path; [shutil.rmtree(d,ignore_errors=True) for d in Path('.').rglob('__pycache__')]"

echo Iniciando o app...
echo Acesse em: http://localhost:8501
echo Para encerrar: pressione Ctrl+C
echo.

%PYTHON% -m streamlit run app.py --server.headless false --browser.gatherUsageStats false

pause
