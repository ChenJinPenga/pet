@echo off
setlocal
cd /d "%~dp0"
set ELECTRON_RUN_AS_NODE=
set DSH_PET_PACK_ROOT=%~dp0
set DSH_PET_APP_NAME=rouduan
set DSH_PET_SCALE=1
start "" "%~dp0electron.exe" "%~dp0app\main.js"
