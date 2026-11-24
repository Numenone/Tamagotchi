@echo off
rem Cerebro do PIXO no PC para o ESP32 do Wokwi (abre http://localhost:8765)
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Rode o TAMAGOTCHI.bat uma vez antes, para instalar o Python do projeto e colocar a chave.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" wokwi\cerebro_pc.py
pause
