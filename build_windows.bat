@echo off
echo ========================================
echo Building Ninlab for Windows
echo ========================================
echo.

REM Check if PyInstaller is installed
where pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo ERROR: PyInstaller not found!
    echo.
    echo Please install PyInstaller:
    echo pip install pyinstaller
    echo.
    pause
    exit /b 1
)

REM Clean previous builds
echo Cleaning previous builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Build with PyInstaller
echo.
echo Building executable with PyInstaller...
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
echo Executable location: dist\NinlabApp\Ninlab.exe
echo.
echo To create an installer, run:
echo .\build_installer.bat
echo.
pause
