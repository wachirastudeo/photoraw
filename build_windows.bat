@echo off
echo ========================================
echo Building Ninlab for Windows
echo ========================================
echo.

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build with PyInstaller
echo.
echo Building executable...
pyinstaller Ninlab.spec

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo BUILD FAILED!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo BUILD SUCCESSFUL!
echo ========================================
echo.
echo Executable location: dist\Ninlab\Ninlab.exe
echo.
echo You can now:
echo 1. Run the app from dist\Ninlab\Ninlab.exe
echo 2. Create installer with: build_installer.bat
echo.
pause
