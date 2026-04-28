@echo off
chcp 65001 > nul 2>&1
title Diagnostico Football Analytics
echo.
echo ============================================
echo   DIAGNOSTICO - Football Analytics
echo ============================================
echo.
echo [1] Verificando Python...
py --version 2>nul || python --version 2>nul || (echo ERRO: Python nao encontrado & pause & exit /b 1)
echo.
echo [2] Verificando Streamlit...
py -m streamlit --version 2>nul || python -m streamlit --version 2>nul || echo AVISO: Streamlit nao instalado
echo.
echo [3] Pasta atual e app.py...
echo Pasta: %CD%
if exist app.py (echo app.py ENCONTRADO) else (echo ERRO: app.py NAO encontrado)
echo.
echo [4] Testando imports...
py -c "import sys; sys.path.insert(0,'.'); erros=[]" 2>nul || python -c "import sys; sys.path.insert(0,'.')" 2>nul
py diagnostico.py 2>&1 || python diagnostico.py 2>&1
echo.
echo [5] Iniciando Streamlit...
echo.
py -m streamlit run app.py --server.headless false --browser.gatherUsageStats false 2>&1 || python -m streamlit run app.py --server.headless false --browser.gatherUsageStats false 2>&1
pause
