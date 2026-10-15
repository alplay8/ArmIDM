@echo off
cd /d "%~dp0"
title ArmIDM - Automatic Windows .EXE Builder
echo ============================================================================
echo   ArmIDM - Pembuat File Standalone ArmIDM.exe Otomatis (Windows)
echo ============================================================================
echo.

REM 1. Periksa instalasi Python di Windows
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python belum terdeteksi di PATH Windows Anda.
    echo Silakan instal Python 3 dari https://www.python.org/downloads/
    pause
    exit /b 1
)

REM 2. Tutup ArmIDM.exe yang sedang berjalan di System Tray agar file tidak terkunci saat di-build
echo [1/4] Menutup proses ArmIDM.exe lama di latar belakang (jika ada) dan membersihkan cache...
taskkill /F /IM ArmIDM.exe /T >nul 2>&1
taskkill /F /IM PyIDM.exe /T >nul 2>&1
timeout /t 1 /nobreak >nul
if exist "build" rmdir /s /q "build" >nul 2>&1
if exist "dist" rmdir /s /q "dist" >nul 2>&1
if exist "ArmIDM.spec" del /f /q "ArmIDM.spec" >nul 2>&1

echo [2/4] Memeriksa PyInstaller...
python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    python -m pip install --upgrade pip pyinstaller
)

echo.
echo [3/4] Mengompilasi armidm.py menjadi Single-File Standalone ArmIDM.exe...
python -m PyInstaller --noconfirm --onefile --windowed --clean --name "ArmIDM" --icon "armidm.ico" "armidm.py"

if not exist "dist\ArmIDM.exe" (
    echo.
    echo [INFO] Mencoba kompilasi ulang dengan mode kompatibilitas Windows Defender...
    timeout /t 2 /nobreak >nul
    if exist "build" rmdir /s /q "build" >nul 2>&1
    if exist "dist" rmdir /s /q "dist" >nul 2>&1
    python -m PyInstaller --noconfirm --onefile --windowed --clean --name "ArmIDM" "armidm.py"
)

if not exist "dist\ArmIDM.exe" (
    echo.
    echo [ERROR] Gagal membuat dist\ArmIDM.exe. Pastikan Antivirus/Windows Defender tidak memblokir PyInstaller.
    pause
    exit /b 1
)

echo.
echo [4/4] Menyalin ArmIDM.exe ke folder utama...
copy /Y "dist\ArmIDM.exe" "ArmIDM.exe" >nul
if exist "ArmIDM.exe" (
    echo.
    echo ============================================================================
    echo   BERHASIL! File "ArmIDM.exe" telah siap digunakan!
    echo   Lokasi: %~dp0ArmIDM.exe
    echo ============================================================================
) else (
    echo [WARNING] ArmIDM.exe berhasil dibuat di dalam folder: %~dp0dist\ArmIDM.exe
)

pause
