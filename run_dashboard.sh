#!/bin/bash
# 啟動信用卡帳單分析報表 Streamlit 儀表板
cd "$(dirname "$0")"
PYTHONPATH=. ./venv/bin/streamlit run app.py
