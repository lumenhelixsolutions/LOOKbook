@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0.."
set ROOT_DIR=%CD%

echo ==^> Initializing MoneyPrinterTurbo submodule...
git submodule update --init --recursive -- tools\moneyprinter
if errorlevel 1 (
    echo ERROR: Failed to update submodule.
    exit /b 1
)

echo ==^> Installing MoneyPrinterTurbo dependencies...
cd /d "%ROOT_DIR%\tools\moneyprinter"
uv pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies. Ensure uv or pip is available.
        exit /b 1
    )
)

echo ==^> Linking lookBOOK config...
if not exist "%ROOT_DIR%\config" mkdir "%ROOT_DIR%\config"
if not exist "%ROOT_DIR%\tools\moneyprinter\config.toml" (
    copy "%ROOT_DIR%\config\moneyprinter.toml" "%ROOT_DIR%\tools\moneyprinter\config.toml" >nul 2>&1
)

echo ==^> MoneyPrinterTurbo ready.
echo     Start: cd tools\moneyprinter ^&^& python main.py
