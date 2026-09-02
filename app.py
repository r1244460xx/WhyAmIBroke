import os
import glob
import re
import unicodedata
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

# Custom CSS for modern dark design with strict uniform metric card styling
st.markdown("""
<style>
    .main {
        background-color: #0F172A;
    }
    .metric-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8));
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 16px 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        text-align: center;
        backdrop-filter: blur(10px);
        height: 130px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        box-sizing: border-box;
        overflow: hidden;
        user-select: text !important;
        -webkit-user-select: text !important;
    }
    .metric-title {
        font-size: 0.9rem !important;
        color: #94A3B8 !important;
        font-weight: 500 !important;
        margin: 0 0 6px 0 !important;
        line-height: 1.1 !important;
    }
    .metric-value {
        font-size: 1.75rem;
        font-weight: 700;
        color: #38BDF8;
        line-height: 1.2;
        margin: 0;
    }
    .metric-sub {
        color: #38BDF8;
        font-weight: 500;
        line-height: 1.2;
        margin-top: 4px;
        max-width: 95%;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .clickable-card {
        cursor: pointer !important;
    }

    /* Layer the native Streamlit button directly over the metric card using negative margin */
    .st-key-btn_count_dialog_trigger {
        margin-top: -130px !important;
        height: 130px !important;
        position: relative !important;
        z-index: 10 !important;
    }
    .st-key-btn_count_dialog_trigger button {
        width: 100% !important;
        height: 130px !important;
        min-height: 130px !important;
        max-height: 130px !important;
        opacity: 0 !important;
        cursor: pointer !important;
        margin: 0 !important;
        padding: 0 !important;
        border: none !important;
        background: transparent !important;
        box-shadow: none !important;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_resource
def get_config_manager():
    return ConfigManager("config.json")


def clean_merchant_name(desc):
    """Strip common refund/cancellation prefixes/suffixes for matching."""
    if not isinstance(desc, str):
        return ""
    d = unicodedata.normalize('NFKC', desc).strip()
    d = re.sub(r'^(退貨|刷退|退款|沖銷|退費|CANCEL|REFUND|REVERSAL)\s*[-－_]?\s*', '', d, flags=re.IGNORECASE)
    d = re.sub(r'\s*[-－_]?\s*(退貨|刷退|退款|沖銷|退費|CANCEL|REFUND|REVERSAL)$', '', d, flags=re.IGNORECASE)
    d = re.sub(r'G\d{4}$', '', d)
    return d.strip()


def process_refund_offsets(df):
    """
    Match refund transactions with corresponding original purchase transactions
    and remove both from the dataset before any statistics are computed.
    Enforces time causality (a refund on date T can only match a purchase on/before date T,
    selecting the closest prior purchase).
    """
    if df.empty:
        return df, pd.DataFrame()
    
    payment_keywords = ["繳款", "自動扣繳", "銀行轉帳", "跨行轉帳", "自動轉帳扣繳", "轉帳"]
    
    records = df.to_dict('records')
    n = len(records)
    matched_indices = set()
    
    # 1. Identify all refund candidate indices
    refund_indices = []
    for i in range(n):
        rec_i = records[i]
        desc_i = str(rec_i.get("交易說明", ""))
        amt_i = float(rec_i.get("金額 (NT$)", 0))
        
        is_payment_i = any(kw in desc_i for kw in payment_keywords)
        is_refund_cand = not is_payment_i and (
            amt_i < 0 or any(kw in desc_i for kw in ["退貨", "刷退", "退款", "沖銷", "退費", "CANCEL", "REFUND", "REVERSAL"])
        )
        if is_refund_cand:
            refund_indices.append(i)
            
    # 2. For each refund, find the closest matching prior purchase (T_purchase <= T_refund)
    for i in refund_indices:
        if i in matched_indices:
            continue
        rec_i = records[i]
        desc_i = str(rec_i.get("交易說明", ""))
        amt_i = float(rec_i.get("金額 (NT$)", 0))
        date_i = rec_i.get("交易日期")
        base_m_i = clean_merchant_name(desc_i)
        target_amt = abs(amt_i)
        
        best_j = None
        best_time_diff = None
        
        for j in range(n):
            if j == i or j in matched_indices or j in refund_indices:
                continue
            rec_j = records[j]
            desc_j = str(rec_j.get("交易說明", ""))
            amt_j = float(rec_j.get("金額 (NT$)", 0))
            date_j = rec_j.get("交易日期")
            
            is_payment_j = any(kw in desc_j for kw in payment_keywords)
            if not is_payment_j and amt_j > 0 and abs(amt_j - target_amt) < 0.01:
                # Time causality constraint: purchase must occur on or before the refund date (T_purchase <= T_refund)
                if pd.notna(date_i) and pd.notna(date_j):
                    if date_j > date_i:
                        continue  # Absolute constraint: cannot refund a future transaction!
                    time_diff = (date_i - date_j).total_seconds()
                else:
                    time_diff = 0
                
                base_m_j = clean_merchant_name(desc_j)
                if base_m_i == base_m_j or (base_m_i and base_m_j and (base_m_i in base_m_j or base_m_j in base_m_i)):
                    # Select the matching prior purchase that is closest in time to the refund
                    if best_time_diff is None or time_diff < best_time_diff:
                        best_time_diff = time_diff
                        best_j = j
                        
        if best_j is not None:
            matched_indices.add(i)
            matched_indices.add(best_j)
            
    remaining_records = [records[k] for k in range(n) if k not in matched_indices]
    matched_records = [records[k] for k in range(n) if k in matched_indices]
    
    return pd.DataFrame(remaining_records), pd.DataFrame(matched_records)


@st.cache_data(show_spinner="📂 正在讀取並解析 PDF 帳單...")
def load_and_parse_all_pdfs(pdf_dir, password):
    """
    Parse all PDF statements in directory and cache the result for instant UI responses.
    """
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


# Modal Popup Dialog for Transaction Details
@st.dialog("📋 納入統計的交易筆數明細", width="large")
def show_transaction_count_modal(filtered_df):
    total_cnt = len(filtered_df)
    st.write(f"目前共 **{total_cnt}** 筆符合條件的交易（預設順序排列，點擊視窗外區域即可關閉）：")
    if not filtered_df.empty:
        count_display = filtered_df[["帳單月份", "交易日期", "交易說明", "金額 (NT$)"]].copy()
        count_display["交易日期"] = count_display["交易日期"].dt.strftime('%Y-%m-%d')
        st.dataframe(count_display, use_container_width=True, hide_index=True, height=450)
    else:
        st.info("無任何交易紀錄")


def main():
    st.title("💳 信用卡帳單分析報表")
    
    config_mgr = get_config_manager()

    # Sidebar settings & filters
    with st.sidebar:
        st.header("⚙️ 設定與過濾")
        
        pdf_dir = st.text_input("帳單 PDF 目錄", value=config_mgr.get("bill_pdf_dir", "./bills"))
        pdf_password = st.text_input("PDF 解密密碼", value=config_mgr.get("pdf_password", ""), type="password")

        c_save, c_refresh = st.columns([1, 1])
        with c_save:
            if st.button("💾 儲存設定", use_container_width=True):
                config_mgr.set("bill_pdf_dir", pdf_dir)
                config_mgr.set("pdf_password", pdf_password)
                st.cache_data.clear()
                st.success("設定已儲存！")
                st.rerun()

        with c_refresh:
            if st.button("🔄 重新掃描", use_container_width=True, help="清除記憶體快取並重新掃描所有 PDF 帳單"):
                st.cache_data.clear()
                st.success("快取已清除，正在重新掃描...")
                st.rerun()

        st.divider()
        st.subheader("🔍 交易過濾設定")
        
        # Default refund offset toggle (Enabled by default)
        auto_refund_offset = st.checkbox(
            "🔄 自動抵銷刷退與退款",
            value=True,
            help="自動比對刷退/退款與對應的原消費，抵消後兩者均不計入統計與明細"
        )

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

        if st.button("🔄 套用與更新過濾條件", use_container_width=True):
            config_mgr.set("min_amount_filter", max(0, int(min_amount)))
            st.success("已更新過濾條件並儲存！")
            st.rerun()

        # Auto-save min_amount if changed
        if min_amount != saved_min_amt:
            config_mgr.set("min_amount_filter", max(0, int(min_amount)))

    # Main logic
    if not os.path.exists(pdf_dir):
        st.warning(f"⚠️ 指定的 PDF 目錄不存在: `{pdf_dir}`")
        return

    df, scan_df = load_and_parse_all_pdfs(pdf_dir, pdf_password)

    if df.empty:
        st.info("ℹ️ 尚無可顯示的交易資料。請確認 `./bills` 目錄內是否有帳單 PDF 及密碼是否正確。")
        if not scan_df.empty:
            st.subheader("📋 帳單掃描狀態報告")
            st.dataframe(scan_df, use_container_width=True, hide_index=True)
        return

    # Process refund offset BEFORE any statistics or threshold filtering
    offset_df = pd.DataFrame()
    if auto_refund_offset and not df.empty:
        df, offset_df = process_refund_offsets(df)

    # Filter out amounts <= min_amount globally if min_amount > 0
    if min_amount > 0:
        df = df[df["金額 (NT$)"] > min_amount]

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 總覽報表", "📑 交易明細與搜尋", "📁 帳單檔案管理"])

    # TAB 1: OVERVIEW DASHBOARD
    with tab1:
        c_month, _ = st.columns([1, 2])
        
        # Filter strictly by 帳單月份 (Statement Month PDF file)
        months = sorted(list(df["帳單月份"].dropna().unique()), reverse=True)
        
        # Initialize session_state for active months if not set (default to only the most recent month)
        if "active_months" not in st.session_state:
            st.session_state["active_months"] = [months[0]] if months else []

        # Filter active months to only include existing months
        active_months = [m for m in st.session_state["active_months"] if m in months]
        if not active_months and months:
            active_months = [months[0]]
            st.session_state["active_months"] = active_months

        # Initialize individual checkbox state if not present
        for m in months:
            if f"cb_month_{m}" not in st.session_state:
                st.session_state[f"cb_month_{m}"] = (m in active_months)

        with c_month:
            with st.popover(f"🗓️ 選擇帳單月份 (已選 {len(active_months)} / {len(months)} 個月)", use_container_width=True):
                # Side-by-side [ 全選 ] and [ 全取消 ] buttons
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("🔘 全選", key="btn_select_all_months", use_container_width=True):
                        for m in months:
                            st.session_state[f"cb_month_{m}"] = True
                        st.rerun()
                with btn_col2:
                    if st.button("✖️ 全取消", key="btn_deselect_all_months", use_container_width=True):
                        for m in months:
                            st.session_state[f"cb_month_{m}"] = False
                        st.rerun()

                st.caption("勾選欲納入統計的帳單月份，確認後點擊「套用」：")
                
                with st.form("month_filter_form", border=False):
                    for m in months:
                        m_count = len(df[df["帳單月份"] == m])
                        st.checkbox(
                            f"📅 {m} 帳單 ({m_count} 筆交易)",
                            key=f"cb_month_{m}"
                        )

                    st.markdown("<br>", unsafe_allow_html=True)
                    apply_btn = st.form_submit_button("套用", use_container_width=True)
                    
                    if apply_btn:
                        st.session_state["active_months"] = [m for m in months if st.session_state.get(f"cb_month_{m}", False)]
                        st.rerun()
        
        selected_months = st.session_state.get("active_months", months)
        filtered_df = df[df["帳單月份"].isin(selected_months)] if selected_months else pd.DataFrame(columns=df.columns)

        # Always exclude payment records (only count positive purchases)
        if not filtered_df.empty:
            filtered_df = filtered_df[filtered_df["金額 (NT$)"] > 0]

        # KPI Metrics
        total_spend = filtered_df["金額 (NT$)"].sum() if not filtered_df.empty else 0
        total_count = len(filtered_df)
        avg_spend = total_spend / total_count if total_count > 0 else 0

        if not filtered_df.empty:
            sorted_df = filtered_df.sort_values(by="金額 (NT$)", ascending=False)
            top_row = sorted_df.iloc[0]
            max_spend = top_row["金額 (NT$)"]
            max_desc = str(top_row["交易說明"])
        else:
            max_spend = 0
            max_desc = "無"

        # Dynamic font sizes for card 3 (單筆最高金額)
        desc_len = len(max_desc)
        spend_str = f"NT$ {max_spend:,.0f}"
        spend_len = len(spend_str)

        if desc_len > 22 or spend_len > 12:
            amt_font_size = "1.45rem"
            desc_font_size = "0.8rem"
        elif desc_len > 14 or spend_len > 9:
            amt_font_size = "1.6rem"
            desc_font_size = "0.84rem"
        else:
            amt_font_size = "1.75rem"
            desc_font_size = "0.88rem"

        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f'<div class="metric-card"><div class="metric-title">總消費金額</div><div class="metric-value">NT$ {total_spend:,.0f}</div></div>', unsafe_allow_html=True)
        
        with col2:
            # 100% Identical HTML markup + Direct Native Streamlit Button Overlay
            st.markdown(
                f'<div class="metric-card clickable-card">'
                f'  <div class="metric-title">總消費筆數</div>'
                f'  <div class="metric-value">{total_count} 筆</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            if st.button(" ", key="btn_count_dialog_trigger", use_container_width=True):
                show_transaction_count_modal(filtered_df)

        with col3:
            st.markdown(
                f'<div class="metric-card">'
                f'  <div class="metric-title">單筆最高金額</div>'
                f'  <div class="metric-value" style="font-size: {amt_font_size};">NT$ {max_spend:,.0f}</div>'
                f'  <div class="metric-sub" style="font-size: {desc_font_size};" title="{max_desc}">📍 {max_desc}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

        st.markdown("<br>", unsafe_allow_html=True)

        if filtered_df.empty:
            st.warning("⚠️ 當前未勾選任何帳單月份或過濾條件下無任何交易資料。")
        else:
            # Charts Section
            c_left, c_right = st.columns([1, 1])

            with c_left:
                st.subheader("📈 每日消費金額分布")
                daily_df = filtered_df.groupby(filtered_df["交易日期"].dt.strftime('%Y-%m-%d'))["金額 (NT$)"].sum().reset_index()
                daily_df = daily_df.sort_values(by="交易日期", ascending=True)

                fig_bar = px.bar(
                    daily_df,
                    x="交易日期",
                    y="金額 (NT$)",
                    text_auto=',.0f',
                    color_discrete_sequence=["#38BDF8"]
                )
                
                # High-contrast value font above daily bars
                fig_bar.update_traces(
                    textposition="outside",
                    textfont=dict(
                        family="'JetBrains Mono', 'DIN Alternate', 'SF Pro Display', 'Inter', -apple-system, sans-serif",
                        size=14,
                        color="#FFFFFF"
                    ),
                    cliponaxis=False
                )

                max_daily = daily_df["金額 (NT$)"].max() if not daily_df.empty else 0
                fig_bar.update_layout(
                    margin=dict(t=25, b=20, l=20, r=20),
                    xaxis=dict(
                        type="category",
                        categoryorder="category ascending",
                        title="交易日期",
                        tickangle=-45 if len(daily_df) > 7 else 0
                    ),
                    yaxis=dict(
                        title="金額 (NT$)",
                        range=[0, max_daily * 1.18] if max_daily > 0 else None
                    )
                )
                st.plotly_chart(fig_bar, use_container_width=True)

            with c_right:
                st.subheader("🗓️ 帳單月份消費總額")
                monthly_summary = filtered_df.copy()
                monthly_df = monthly_summary.groupby("帳單月份")["金額 (NT$)"].sum().reset_index()
                monthly_df = monthly_df.sort_values(by="帳單月份", ascending=True)
                num_m = len(monthly_df)

                fig_monthly = px.bar(
                    monthly_df,
                    x="帳單月份",
                    y="金額 (NT$)",
                    text_auto=',.0f',
                    color_discrete_sequence=["#818CF8"]
                )
                
                # Enhanced high-contrast designer font for bar values
                fig_monthly.update_traces(
                    textposition="outside",
                    textfont=dict(
                        family="'JetBrains Mono', 'DIN Alternate', 'SF Pro Display', 'Inter', -apple-system, sans-serif",
                        size=16,
                        color="#FFFFFF"
                    ),
                    cliponaxis=False
                )

                # Enforce category type to ensure ONLY month labels appear, and order left-to-right
                xaxis_config = dict(
                    type="category",
                    categoryorder="category ascending",
                    title="帳單月份"
                )
                # When 5 months or fewer, set category range so bars start from left instead of being centered
                if num_m < 6:
                    xaxis_config["range"] = [-0.5, max(5, num_m) - 0.5]

                max_val = monthly_df["金額 (NT$)"].max() if not monthly_df.empty else 0
                fig_monthly.update_layout(
                    margin=dict(t=25, b=20, l=20, r=20),
                    xaxis=xaxis_config,
                    yaxis=dict(
                        title="總金額 (NT$)",
                        range=[0, max_val * 1.18] if max_val > 0 else None
                    )
                )
                st.plotly_chart(fig_monthly, use_container_width=True)

            # Top Transactions Table
            st.subheader("🔥 最高花費前 10 筆明細")
            top10_df = filtered_df.sort_values(by="金額 (NT$)", ascending=False).head(10)
            top10_display = top10_df[["帳單月份", "交易日期", "交易說明", "金額 (NT$)"]].copy()
            top10_display["交易日期"] = top10_display["交易日期"].dt.strftime('%Y-%m-%d')
            st.dataframe(top10_display, use_container_width=True, hide_index=True)

    # TAB 2: TRANSACTION DETAILS & SEARCH
    with tab2:
        st.subheader("🔍 交易明細查詢與篩選")
        
        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            m_options = ["全部"] + sorted(list(df["帳單月份"].unique()), reverse=True)
            sel_m = st.selectbox("篩選帳單月份", m_options)
        with f_col2:
            kw = st.text_input("搜尋交易說明關鍵字 (例如: 全聯 / 高鐵 / 露天)", "")

        detail_df = df.copy()
        if sel_m != "全部":
            detail_df = detail_df[detail_df["帳單月份"] == sel_m]
        if kw.strip():
            norm_kw = unicodedata.normalize('NFKC', kw.strip())
            detail_df = detail_df[detail_df["交易說明"].str.contains(norm_kw, case=False, na=False)]

        detail_display = detail_df[["帳單月份", "交易日期", "交易說明", "金額 (NT$)", "來源檔名"]].copy()
        detail_display["交易日期"] = detail_display["交易日期"].dt.strftime('%Y-%m-%d')

        st.dataframe(
            detail_display,
            use_container_width=True,
            hide_index=True
        )

        csv_data = detail_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 匯出搜尋結果為 CSV 檔案",
            data=csv_data,
            file_name="credit_card_transactions.csv",
            mime="text/csv"
        )

    # TAB 3: FILE MANAGEMENT & REFUND AUDIT
    with tab3:
        st.subheader("📁 本地 PDF 帳單掃描狀態")
        st.dataframe(scan_df, use_container_width=True, hide_index=True)

        if auto_refund_offset and not offset_df.empty:
            st.divider()
            st.subheader(f"🔄 已自動對銷的刷退明細 (共 {len(offset_df)} 筆項目)")
            st.caption("系統已將下列刷退/退款項目與對應之原消費對銷，這些項目均未計入上方任何統計與報表：")
            offset_display = offset_df[["帳單月份", "交易日期", "交易說明", "金額 (NT$)", "來源檔名"]].copy()
            offset_display["交易日期"] = offset_display["交易日期"].dt.strftime('%Y-%m-%d')
            st.dataframe(offset_display, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
