#!/bin/bash
# =========================================================
# 信用卡帳單分析報表 (Where Did My Money Go) - Linux / macOS 啟動腳本
# =========================================================
set -e
cd "$(dirname "$0")"

echo "========================================================="
echo "💳 正在啟動 信用卡帳單分析報表..."
echo "========================================================="

# 1. 檢查並建立虛擬環境 (venv)
if [ ! -f "./venv/bin/python" ] || [ ! -f "./venv/bin/streamlit" ]; then
    echo "[1/3] 正在建立專屬 Python 虛擬環境 (venv)..."
    
    if command -v python3 >/dev/null 2>&1; then
        python3 -m venv venv
    elif command -v python >/dev/null 2>&1; then
        python -m venv venv
    else
        echo "[ERROR] 找不到 Python！請先安裝 Python 3.9 或以上版本。"
        exit 1
    fi

    echo "[2/3] 正在於虛擬環境中安裝相依套件 (requirements.txt)..."
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
else
    echo "[INFO] 已偵測到現有虛擬環境 (venv)。"
fi

# 2. 檢查初始設定檔與帳單目錄
if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
    echo "[INFO] 正在建立初始設定檔 config.json..."
    cp config.example.json config.json
fi

if [ ! -d "bills" ]; then
    mkdir -p bills
fi

# 3. 啟動 Streamlit 應用
echo "[3/3] 正在啟動 Streamlit 伺服器並自動開啟瀏覽器..."
PYTHONPATH=. ./venv/bin/streamlit run app.py --server.headless=false --browser.serverAddress=localhost
