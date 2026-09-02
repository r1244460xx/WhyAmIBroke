#!/bin/bash
# 雙擊一鍵啟動 信用卡帳單分析報表 (macOS)
cd "$(dirname "$0")"

# Check if venv exists
if [ ! -f "./venv/bin/python" ]; then
    echo "正在建立 Python 虛擬環境 (venv)..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

if [ ! -f "config.json" ] && [ -f "config.example.json" ]; then
    cp config.example.json config.json
fi

echo "正在啟動 Streamlit 儀表板並自動開啟瀏覽器..."
PYTHONPATH=. ./venv/bin/streamlit run app.py --server.headless=false --browser.serverAddress=localhost
