@echo off
echo ========================================
echo Building Ninlab Installer
echo ========================================
echo.

REM Check if dist\Ninlab exists
if not exist "dist\Ninlab\Ninlab.exe" (
    echo ERROR: Executable not found!
    echo Please run build_windows.bat first to create the executable.
    echo.
    pause
    exit /b 1
)

REM Create output directory
if not exist installer_output mkdir installer_output

REM Check if Inno Setup is installed
where iscc >nul 2>nul
if %errorlevel% neq 0 (
    if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" (
        echo Found Inno Setup at default location.
        set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    ) else (
        echo ERROR: Inno Setup Compiler not found!
        echo.
        echo Please install Inno Setup from:
        echo https://jrsoftware.org/isdl.php
        echo.
        echo After installation, add it to PATH or run:
        echo "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" ninlab_installer.iss
        echo.
        pause
        exit /b 1
    )
) else (
    set "ISCC=iscc"
)

REM Build installer
echo Building installer...
"%ISCC%" ninlab_installer.iss

if %errorlevel% neq 0 (
    echo.
    echo ========================================
    echo INSTALLER BUILD FAILED!
    echo ========================================
    pause
    exit /b 1
)

echo.
echo ========================================
echo INSTALLER BUILD SUCCESSFUL!
echo ========================================
echo.
echo Installer location: installer_output\NinlabSetup.exe
echo.
echo You can now distribute NinlabSetup.exe to users.
echo.
pause
