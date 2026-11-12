@echo off
setlocal EnableExtensions
chcp 65001 >nul
title Tamagotchi Studio + Claude
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

echo.
echo    ===============================================
echo         TAMAGOTCHI STUDIO + CLAUDE
echo    ===============================================
echo.

if exist ".venv\Scripts\python.exe" goto deps

echo  [1/3] Procurando o Python...
set "PY="
py -3 --version >nul 2>nul && set "PY=py -3"
if not defined PY python --version >nul 2>nul && set "PY=python"
if not defined PY (
    echo  Python nao encontrado. Instalando o Python 3.12 pelo winget...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
    if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set PY="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
)
if not defined PY (
    echo.
    echo  Nao consegui instalar o Python sozinho.
    echo  Baixe em https://www.python.org/downloads/ ^(marque "Add Python to PATH"^)
    echo  e abra este arquivo de novo.
    pause
    exit /b 1
)
echo  [2/3] Criando o ambiente do programa...
%PY% -m venv .venv
if errorlevel 1 goto erro

:deps
fc /b requirements.txt ".venv\req.ok" >nul 2>nul
if not errorlevel 1 goto prepare
echo  [2/3] Instalando as bibliotecas (so na primeira vez, pode levar alguns minutos)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q --upgrade pip
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto erro
echo        Voz offline do Windows (opcional)...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q pyttsx3 >nul 2>nul
copy /y requirements.txt ".venv\req.ok" >nul

:prepare
if exist "tools\arduino-cli\arduino-cli.exe" if exist "%LOCALAPPDATA%\Arduino15\packages\arduino\hardware\avr" goto run
echo  [3/3] Baixando o compilador do Arduino (so na primeira vez)...
".venv\Scripts\python.exe" -m app.prepare

:run
if defined TAMA_NOLAUNCH exit /b 0
echo.
echo  Abrindo o Tamagotchi Studio...
".venv\Scripts\python.exe" -m app.main
if errorlevel 1 goto erro
exit /b 0

:erro
echo.
echo  Algo deu errado. Leia a mensagem acima.
echo  Dica: confira sua internet e tente abrir o TAMAGOTCHI.bat de novo.
pause
exit /b 1
