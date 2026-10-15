@echo off
cd /d "%~dp0"
title ArmIDM - Auto Uploader ke GitHub
echo ============================================================================
echo   ArmIDM - Asisten Upload Otomatis ke Repository GitHub Anda
echo ============================================================================
echo.

REM 1. Cek apakah Git sudah terinstal
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Git belum terdeteksi di komputer Anda.
    echo Silakan unduh dan instal Git terlebih dahulu dari: https://git-scm.com/download/win
    echo Atau gunakan Cara Upload Langsung via Browser di github.com/new
    pause
    exit /b 1
)

REM 2. Bersihkan folder sementara hasil build lokal agar tidak membebani upload
if exist "build" rmdir /s /q "build" >nul 2>&1
if exist "dist" rmdir /s /q "dist" >nul 2>&1
if exist "ArmIDM.spec" del /f /q "ArmIDM.spec" >nul 2>&1

echo Langkah Persiapan:
echo 1. Buka https://github.com/new di browser Anda untuk membuat repository baru kosong
echo    ^(Misalnya beri nama: ArmIDM, dan biarkan tanpa centang Add README^).
echo 2. Salin URL Repository GitHub Anda ^(contoh: https://github.com/username/ArmIDM.git^).
echo.
set /p REPO_URL="Tempel (Paste) URL Repository GitHub Anda di sini lalu tekan ENTER: "

if "%REPO_URL%"=="" (
    echo [ERROR] URL Repository tidak boleh kosong.
    pause
    exit /b 1
)

echo.
echo [1/4] Menginisialisasi Git Repository lokal...
if not exist ".git" (
    git init
)
git branch -M main

echo [2/4] Menambahkan seluruh file proyek ArmIDM...
git add .
git commit -m "Initial release: ArmIDM Download Manager & Multi-Browser Extensions"

echo [3/4] Menghubungkan ke Repository GitHub: %REPO_URL%
git remote remove origin >nul 2>&1
git remote add origin "%REPO_URL%"

echo [4/4] Mengunggah (Push) proyek ke GitHub...
git push -u origin main

if %errorlevel% equ 0 (
    echo.
    echo ============================================================================
    echo   BERHASIL! Seluruh proyek ArmIDM telah ter-upload ke GitHub Anda!
    echo   Silakan buka halaman GitHub Anda dan cek tab "Actions" untuk melihat
    echo   proses build otomatis ArmIDM.exe di cloud GitHub!
    echo ============================================================================
) else (
    echo.
    echo [INFO] Jika gagal karena cabang remote sudah memiliki isi, mencoba push paksa...
    git push -u origin main --force
)

pause
