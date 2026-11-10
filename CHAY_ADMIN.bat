@echo off
chcp 65001 >nul
title Tomkids AppStore & Cydia Admin Portal
echo ========================================================
echo   TOMKIDS APPSTORE & CYDIA ADMIN PORTAL
echo   - Kho Ứng Dụng AppStore OTA
echo   - Cài Đặt Nhanh DEB (Cydia Cluster Repo)
echo ========================================================
cd /d "%~dp0"
python appvn_admin.py
pause
