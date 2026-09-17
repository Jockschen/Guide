@echo off
title Lingjing Guide Local Services
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1" -KeepAlive
if errorlevel 1 (
  echo.
  echo Lingjing Guide failed to start. Please read the error above.
  pause
)
