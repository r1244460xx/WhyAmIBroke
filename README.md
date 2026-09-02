# CreditCardPaymetAnalysis

💳 **信用卡電子帳單 Parsing & Dashboard 分析可視化工具**

基於 Python + Streamlit 開發的信用卡帳單分析 Dashboard，支援加密 PDF 電子帳單自動解析、時序因果刷退自動對銷、月份複選統計、每日/各月消費趨勢圖表與 Modal 彈窗明細查詢。

---

## 🌟 功能特點

- 🔒 **加密 PDF 自動解析**：支援加密信用卡電子帳單（如台新銀行等），自動將國曆年份轉換為西元年份，並聰明處理解析跨列商家說明名稱。
- 🔄 **時序因果約束刷退對銷**：自動比對刷退項目與當日或之前時間最接近之原始消費，精準抵銷，不逆向扣抵未來交易。
- 📊 **三大核心 KPI 卡片**：
  - **總消費金額**
  - **總消費筆數**（整張卡片為可點擊區塊，點擊直接彈出交易明細視窗）
  - **單筆最高金額**（含商家備註與動態字級排版）
- 🗓️ **月份篩選器**：提供「🔘 全選」與「✖️ 全取消」快捷按鈕，支援自訂複選與一鍵套用。
- ⚙️ **門檻金額過濾**：可自訂過濾小於等於特定金額的小額消費（設定自動儲存至 `config.json`）。
- 📈 **消費趨勢視覺化**：整合 Plotly 互動式「每日消費金額分布」與「帳單月份消費總額」高對比度柱狀圖。
- ⚡ **極速快取機制**：內建 `@st.cache_data` 記憶體快取，切換分頁與篩選查詢 0.005 秒瞬間刷新。

---

## 🚀 雙擊一鍵啟動 (無需輸入指令)

### 🪟 Windows 使用者：
直接用滑鼠雙擊資料夾內的 **`run_dashboard.bat`** 檔案：
1. 程式會自動偵測並建立 Python 虛擬環境、自動安裝所需套件。
2. 自動啟動 Streamlit 伺服器，並**自動在預設瀏覽器（Edge / Chrome 等）中開啟儀表板網頁**！

### 🍎 macOS 使用者：
直接用滑鼠雙擊資料夾內的 **`run_dashboard.command`** 檔案：
1. 自動開啟 Terminal 終端機並檢查環境。
2. **自動在預設瀏覽器（Safari / Chrome 等）中跳出儀表板網頁**！

---

## 💻 手動命令列啟動

如果您偏好使用命令列：

### 1. 建立並啟用虛擬環境
```bash
# macOS / Linux
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Windows (Command Prompt / PowerShell)
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 啟動 Dashboard
```bash
# macOS / Linux
./run_dashboard.sh

# Windows
venv\Scripts\streamlit.exe run app.py
```

開啟瀏覽器造訪 [http://localhost:8501](http://localhost:8501) 即可開始使用！

---

## 🛡️ 安全注意事項

本專案之 `.gitignore` 已預設排除 `config.json` 與 `bills/*.pdf` 等敏感個人資料檔，請勿將包含個人財務與密碼的檔案提交至 Git 倉庫。
