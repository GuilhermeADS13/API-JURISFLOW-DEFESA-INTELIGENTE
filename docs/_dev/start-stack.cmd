@echo off
REM Atalho para iniciar a stack AutoJuri (Docker Desktop + containers + healthcheck).
REM Duplo-clique aqui ou pin na taskbar.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start-stack.ps1"
pause
