@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 공지 확인 (로컬 테스트)

echo [*] 게시판을 한 번 확인합니다.
echo.
py check_notices.py

echo.
pause
