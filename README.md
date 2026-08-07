# CreditCardPaymetAnalysis

💳 **信用卡電子帳單 Parsing & Dashboard 分析可視化工具**

基於 Python + Streamlit 開發的信用卡帳單分析 Dashboard，支援加密 PDF 電子帳單自動解析、交易明細過濾、月份複選統計、每日/各月消費趨勢圖表與 Modal 彈窗明細查詢。

---

## 🌟 功能特點

- 🔒 **加密 PDF 自動解析**：支援加密信用卡電子帳單（如台新銀行等），自動將國曆年份轉換為西元年份，並聰明處理解析跨列商家說明名稱。
- 📊 **四大 KPI 核心數據**：
  - **總消費金額**
  - **總消費筆數**（點擊卡片空白處可觸發彈出式 Modal 明細視窗，支援複製卡片文字）
  - **平均單筆消費**
  - **單筆最高金額**（動態自動縮放商家名稱與金額字體大小）
- 🗓️ **月份篩選器**：使用 Popover + Form 一鍵批次套用多個月份統計。
- ⚙️ **門檻金額過濾**：可自訂小於等於該金額的項目過濾（設定自動儲存至 `config.json`）。
- 📈 **消費趨勢視覺化**：整合 Plotly 互動式每日分布圖與各月花費對比圖。

---

## 🚀 快速開始

### 1. 建立並啟用 Python 虛擬環境

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. 設定參數

複製範例設定檔：

```bash
cp config.example.json config.json
```

編輯 `config.json`，輸入您的 PDF 解密密碼：

```json
{
  "bill_pdf_dir": "./bills",
  "pdf_password": "YOUR_PDF_PASSWORD",
  "min_amount_filter": 0
}
```

將您的信用卡電子帳單 PDF 放置於 `./bills` 目錄下。

### 3. 啟動 Dashboard

執行專案內建腳本：

```bash
./run_dashboard.sh
```

或使用 streamlit 命令：

```bash
./venv/bin/streamlit run app.py
```

開啟瀏覽器造訪 [http://localhost:8501](http://localhost:8501) 即可開始使用！

---

## 🛡️ 安全注意事項

本專案之 `.gitignore` 已預設排除 `config.json` 與 `bills/*.pdf` 等敏感個人資料檔，請勿將包含個人財務與密碼的檔案提交至 Git 倉庫。
