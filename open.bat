@echo off
title Open Lingjing Guide Pages
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\open.ps1"
if errorlevel 1 (
  echo.
  echo Lingjing Guide pages could not be opened. Please read the error above.
  pause
)
