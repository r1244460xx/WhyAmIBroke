@echo off
chcp 65001 >nul
title 信用卡帳單分析報表 (Where Did My Money Go)

cd /d "%~dp0"

echo =========================================================
echo 💳 正在啟動 信用卡帳單分析報表...
echo =========================================================

:: 1. 檢查並建立虛擬環境 (venv)
if not exist "venv\Scripts\python.exe" (
    echo [1/3] 正在建立專屬 Python 虛擬環境 (venv)...
    
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        python -m venv venv
    ) else (
        where py >nul 2>&1
        if %errorlevel% equ 0 (
            py -m venv venv
        ) else (
            echo [ERROR] 找不到 Python！請先安裝 Python 3.9+ 並勾選 "Add Python to PATH"。
            pause
            exit /b 1
        )
    )

    if %errorlevel% neq 0 (
        echo [ERROR] 建立虛擬環境失敗，請檢查 Python 設定！
        pause
        exit /b 1
    )

    echo [2/3] 正在於虛擬環境中安裝相依套件 (requirements.txt)...
    venv\Scripts\python.exe -m pip install --upgrade pip
    venv\Scripts\pip.exe install -r requirements.txt
    if %errorlevel% neq 0 (
        echo [ERROR] 套件安裝失敗，請檢查網路連線後重試！
        pause
        exit /b 1
    )
) else (
    echo [INFO] 已偵測到現有虛擬環境 (venv)。
)

:: 2. 檢查初始設定檔與帳單目錄
if not exist "config.json" (
    if exist "config.example.json" (
        echo [INFO] 正在建立初始設定檔 config.json...
        copy config.example.json config.json >nul
    )
)

if not exist "bills" (
    mkdir bills
)

:: 3. 啟動 Streamlit 應用
echo [3/3] 正在啟動 Streamlit 伺服器並自動開啟瀏覽器...
set PYTHONPATH=.
start "" "venv\Scripts\streamlit.exe" run app.py --server.headless=false --browser.serverAddress=localhost

echo =========================================================
echo [SUCCESS] 儀表板已在瀏覽器中開啟！此視窗可縮小保留於背景。
echo =========================================================
