import os
import glob
import pandas as pd
import streamlit as st
import plotly.express as px

from src.config_manager import ConfigManager
from src.pdf_parser import CreditCardPDFParser

# Page setup
st.set_page_config(
    page_title="信用卡帳單分析報表",
    page_icon="💳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern dark design
st.markdown("""
<style>
    .main {
        background-color: #0F172A;
    }
    .metric-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8));
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        text-align: center;
        backdrop-filter: blur(10px);
    }
    .metric-card h4 {
        margin: 0;
        font-size: 0.95rem;
        color: #94A3B8;
        font-weight: 500;
    }
    .metric-card h2 {
        margin: 10px 0 0 0;
        font-size: 2rem;
        font-weight: 700;
        color: #38BDF8;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_config_manager():
    return ConfigManager("config.json")


def load_and_parse_all_pdfs(pdf_dir, password):
    parser = CreditCardPDFParser(password=password)

    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf")) + glob.glob(os.path.join(pdf_dir, "*.PDF"))
    pdf_files = sorted(list(set(pdf_files)))

    all_records = []
    scan_results = []

    for pdf_path in pdf_files:
        file_name = os.path.basename(pdf_path)
        try:
            parsed = parser.parse_pdf(pdf_path)
            transactions = parsed.get("transactions", [])
            
            for t in transactions:
                all_records.append({
                    "帳單月份": parsed.get("statement_month", "未知"),
                    "交易日期": t["trans_date"],
                    "入帳日期": t["post_date"],
                    "交易說明": t["description"],
                    "金額 (NT$)": t["amount"],
                    "卡號末四碼": t["card_no"],
                    "來源檔名": file_name
                })

            scan_results.append({
                "檔案名稱": file_name,
                "解析狀態": "✅ 解析成功" if transactions else "⚠️ 無交易明細",
                "提取筆數": len(transactions),
                "帳單月份": parsed.get("statement_month", "未知")
            })
        except Exception as e:
            scan_results.append({
                "檔案名稱": file_name,
                "解析狀態": f"❌ 失敗: {str(e)}",
                "提取筆數": 0,
                "帳單月份": "未知"
            })

    df = pd.DataFrame(all_records)
    if not df.empty:
        df["交易日期"] = pd.to_datetime(df["交易日期"], errors="coerce")
        df = df.sort_values(by="交易日期", ascending=False)
    
    return df, pd.DataFrame(scan_results)


def main():
    st.title("💳 信用卡帳單分析報表")
    
    config_mgr = get_config_manager()

    # Sidebar settings & filters
    with st.sidebar:
        st.header("⚙️ 設定與過濾")
        
        pdf_dir = st.text_input("帳單 PDF 目錄", value=config_mgr.get("bill_pdf_dir", "./bills"))
        pdf_password = st.text_input("PDF 解密密碼", value=config_mgr.get("pdf_password", ""), type="password")

        st.divider()
        st.subheader("🔍 交易過濾設定")
        
        # Load min_amount_filter from config. Default 0 if missing or negative
        saved_min_amt = config_mgr.get("min_amount_filter", 0)
        if not isinstance(saved_min_amt, (int, float)) or saved_min_amt < 0:
            saved_min_amt = 0

        min_amount = st.number_input(
            "過濾小於等於此金額的項目 (NT$)",
            min_value=0,
            value=int(saved_min_amt),
            step=100,
            help="設定例如 500，則所有金額 <= 500 的交易將不會納入統計與報表"
        )

        # Auto-save min_amount if changed
        if min_amount != saved_min_amt:
            config_mgr.set("min_amount_filter", max(0, int(min_amount)))

        if st.button("💾 儲存所有設定", use_container_width=True):
            config_mgr.set("bill_pdf_dir", pdf_dir)
            config_mgr.set("pdf_password", pdf_password)
            config_mgr.set("min_amount_filter", max(0, int(min_amount)))
            st.success("設定已儲存至 config.json！")
            st.rerun()

    # Main logic
    if not os.path.exists(pdf_dir):
        st.warning(f"⚠️ 指定的 PDF 目錄不存在: `{pdf_dir}`")
        return

    df, scan_df = load_and_parse_all_pdfs(pdf_dir, pdf_password)

    if df.empty:
        st.info("ℹ️ 尚無可顯示的交易資料。請確認 `./bills` 目錄內是否有帳單 PDF 及密碼是否正確。")
        if not scan_df.empty:
            st.subheader("📋 帳單掃描狀態報告")
            st.dataframe(scan_df, use_container_width=True)
        return

    # Filter out amounts <= min_amount globally if min_amount > 0
    if min_amount > 0:
        df = df[df["金額 (NT$)"] > min_amount]

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 總覽報表", "📑 交易明細與搜尋", "📁 帳單檔案管理"])

    # TAB 1: OVERVIEW DASHBOARD
    with tab1:
        c_filter1, c_filter2 = st.columns([2, 1])
        with c_filter1:
            months = sorted(list(df["帳單月份"].dropna().unique()), reverse=True)
            selected_months = st.multiselect("🗓️ 選擇帳單月份", options=months, default=months)
        with c_filter2:
            exclude_payments = st.checkbox("扣除 [網路銀行繳款/自動扣繳] (負數金額)", value=True)
        
        filtered_df = df[df["帳單月份"].isin(selected_months)] if selected_months else df

        if exclude_payments:
            filtered_df = filtered_df[filtered_df["金額 (NT$)"] > 0]

        # KPI Metrics
        total_spend = filtered_df["金額 (NT$)"].sum()
        total_count = len(filtered_df)
        avg_spend = total_spend / total_count if total_count > 0 else 0
        max_spend = filtered_df["金額 (NT$)"].max() if not filtered_df.empty else 0

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown(f'<div class="metric-card"><h4>總消費金額</h4><h2>NT$ {total_spend:,.0f}</h2></div>', unsafe_allow_html=True)
        with col2:
            st.markdown(f'<div class="metric-card"><h4>總消費筆數</h4><h2>{total_count} 筆</h2></div>', unsafe_allow_html=True)
        with col3:
            st.markdown(f'<div class="metric-card"><h4>平均單筆消費</h4><h2>NT$ {avg_spend:,.0f}</h2></div>', unsafe_allow_html=True)
        with col4:
            st.markdown(f'<div class="metric-card"><h4>單筆最高金額</h4><h2>NT$ {max_spend:,.0f}</h2></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        if filtered_df.empty:
            st.warning("⚠️ 當前過濾條件下無任何交易資料。")
        else:
            # Charts Section
            c_left, c_right = st.columns([1, 1])

            with c_left:
                st.subheader("📈 每日消費金額分布")
                daily_df = filtered_df.groupby(filtered_df["交易日期"].dt.strftime('%Y-%m-%d'))["金額 (NT$)"].sum().reset_index()
                fig_bar = px.bar(
                    daily_df,
                    x="交易日期",
                    y="金額 (NT$)",
                    color_discrete_sequence=["#38BDF8"]
                )
                fig_bar.update_layout(margin=dict(t=20, b=20, l=20, r=20), xaxis_title="日期", yaxis_title="金額 (NT$)")
                st.plotly_chart(fig_bar, use_container_width=True)

            with c_right:
                st.subheader("🗓️ 各月總花費對比")
                monthly_summary = df.copy()
                if exclude_payments:
                    monthly_summary = monthly_summary[monthly_summary["金額 (NT$)"] > 0]
                monthly_df = monthly_summary.groupby("帳單月份")["金額 (NT$)"].sum().reset_index()
                fig_monthly = px.bar(
                    monthly_df,
                    x="帳單月份",
                    y="金額 (NT$)",
                    text_auto=',.0f',
                    color_discrete_sequence=["#818CF8"]
                )
                fig_monthly.update_layout(margin=dict(t=20, b=20, l=20, r=20), xaxis_title="帳單月份", yaxis_title="總金額 (NT$)")
                st.plotly_chart(fig_monthly, use_container_width=True)

            # Top Transactions Table
            st.subheader("🔥 最高花費前 10 筆明細")
            top10_df = filtered_df.sort_values(by="金額 (NT$)", ascending=False).head(10)
            top10_display = top10_df[["帳單月份", "交易日期", "交易說明", "金額 (NT$)", "卡號末四碼"]].copy()
            top10_display["交易日期"] = top10_display["交易日期"].dt.strftime('%Y-%m-%d')
            st.dataframe(top10_display, use_container_width=True)

    # TAB 2: TRANSACTION DETAILS & SEARCH
    with tab2:
        st.subheader("🔍 交易明細查詢與篩選")
        
        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            m_options = ["全部"] + sorted(list(df["帳單月份"].unique()), reverse=True)
            sel_m = st.selectbox("篩選帳單月", m_options)
        with f_col2:
            kw = st.text_input("搜尋交易說明關鍵字 (例如: 全聯 / 高鐵 / 露天)", "")

        detail_df = df.copy()
        if sel_m != "全部":
            detail_df = detail_df[detail_df["帳單月份"] == sel_m]
        if kw.strip():
            detail_df = detail_df[detail_df["交易說明"].str.contains(kw.strip(), case=False, na=False)]

        detail_display = detail_df[["帳單月份", "交易日期", "交易說明", "金額 (NT$)", "卡號末四碼", "來源檔名"]].copy()
        detail_display["交易日期"] = detail_display["交易日期"].dt.strftime('%Y-%m-%d')

        st.dataframe(
            detail_display,
            use_container_width=True
        )

        csv_data = detail_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 匯出搜尋結果為 CSV 檔案",
            data=csv_data,
            file_name="credit_card_transactions.csv",
            mime="text/csv"
        )

    # TAB 3: FILE MANAGEMENT
    with tab3:
        st.subheader("📁 本地 PDF 帳單掃描狀態")
        st.dataframe(scan_df, use_container_width=True)


if __name__ == "__main__":
    main()
