@echo off
chcp 65001 >nul
title 信用卡帳單分析報表 Streamlit Dashboard

cd /d "%~dp0"

echo ===================================================
echo 💳 正在啟動 信用卡帳單分析報表...
echo ===================================================

:: Check if virtual environment exists
if not exist "venv\Scripts\python.exe" (
    echo [INFO] 正在建立 Python 虛擬環境 (venv)...
    python -m venv venv
    if errorlevel 1 (
        echo [ERROR] 建立虛擬環境失敗，請確認已安裝 Python 3.9+ 並勾選 Add Python to PATH！
        pause
        exit /b 1
    )
    echo [INFO] 正在安裝必要套件 (requirements.txt)...
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\pip.exe install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] 套件安裝失敗，請檢查網路連線或套件清單！
        pause
        exit /b 1
    )
)

:: Check if config.json exists, if not copy from config.example.json
if not exist "config.json" (
    if exist "config.example.json" (
        echo [INFO] 正在建立初始設定檔 config.json...
        copy config.example.json config.json >nul
    )
)

echo [INFO] 正在啟動 Streamlit 伺服器並自動開啟瀏覽器...
set PYTHONPATH=.
start "" "venv\Scripts\streamlit.exe" run app.py --server.headless=false --browser.serverAddress=localhost

echo [SUCCESS] 儀表板已在瀏覽器中開啟！此視窗可縮小保留在背景。
