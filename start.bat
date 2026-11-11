@echo off
title UR_PICASSO - Servidor
echo ==================================================
echo     UR_PICASSO - ROBO RETRATISTA DE EVENTOS
echo ==================================================
cd /d "%~dp0"
python -m uvicorn app:app --host 0.0.0.0 --port 5000 --reload
pause

