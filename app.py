import os
import glob
import re
import unicodedata
import pandas as pd
import streamlit as st
import plotly.express as px

import importlib
from src.config_manager import ConfigManager
import src.pdf_parser
importlib.reload(src.pdf_parser)
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

    /* Floating Sticky Adder column & Top Border Alignment */
    div[data-testid="column"]:has(.top10-adder-marker) {
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 80px !important;
        align-self: flex-start !important;
        z-index: 30 !important;
    }
    div[data-testid="column"]:has(.top10-adder-marker) > div {
        position: -webkit-sticky !important;
        position: sticky !important;
        top: 80px !important;
        margin-top: 0 !important;
        padding-top: 0 !important;
    }
    div[data-testid="column"]:has(.top10-adder-marker) div[data-testid="stVerticalBlockBorderWrapper"] {
        margin-top: 0 !important;
        background: #1E293B !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4) !important;
    }

    /* Ensure page canvas maintains sufficient scrollable height even when empty */
    .main .block-container {
        min-height: 80vh !important;
        padding-bottom: 6rem !important;
    }

    /* Popover body smoothness and overscroll containment to prevent macOS elastic bounce */
    div[data-testid="stPopoverBody"] {
        overscroll-behavior: contain !important;
    }

    /* Hide Streamlit default "Press Enter to apply / submit form" instructions */
    div[data-testid="InputInstructions"], span[data-testid="InputInstructions"] {
        display: none !important;
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
def load_and_parse_all_pdfs(pdf_dir, password_configs, _cache_version="v2.2_strategy"):
    """
    Parse all PDF statements in directory using prefix-matched passwords and cache the result.
    """
    pdf_files = glob.glob(os.path.join(pdf_dir, "*.pdf")) + glob.glob(os.path.join(pdf_dir, "*.PDF"))
    pdf_files = sorted(list(set(pdf_files)))

    all_records = []
    scan_results = []

    # Sort password_configs by prefix length descending so the most specific prefix is matched first
    sorted_pw_configs = sorted(password_configs or [], key=lambda x: len(x.get("prefix", "")), reverse=True)

    for pdf_path in pdf_files:
        file_name = os.path.basename(pdf_path)
        matched_pw = None
        matched_prefix = None

        # 1. Match by prefix
        for item in sorted_pw_configs:
            pfx = item.get("prefix", "").strip()
            if pfx and file_name.lower().startswith(pfx.lower()):
                matched_pw = item.get("password", "")
                matched_prefix = pfx
                break

        # 2. Universal fallback (empty prefix)
        if matched_pw is None:
            for item in sorted_pw_configs:
                pfx = item.get("prefix", "").strip()
                if not pfx and item.get("password", ""):
                    matched_pw = item.get("password", "")
                    matched_prefix = "(通用預設)"
                    break

        try:
            parser = CreditCardPDFParser(password=matched_pw)
            parsed = parser.parse_pdf(pdf_path)
            transactions = parsed.get("transactions", [])
            bank_name = parsed.get("bank_name", "未知")
            
            for t in transactions:
                all_records.append({
                    "銀行": bank_name,
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
                "銀行": bank_name,
                "解析狀態": "✅ 解析成功" if transactions else "⚠️ 無交易明細",
                "提取筆數": len(transactions),
                "帳單月份": parsed.get("statement_month", "未知"),
                "配對前綴": matched_prefix if matched_prefix else "無"
            })
        except Exception as e:
            scan_results.append({
                "檔案名稱": file_name,
                "銀行": "未知",
                "解析狀態": f"❌ 失敗: {str(e)}",
                "提取筆數": 0,
                "帳單月份": "未知",
                "配對前綴": matched_prefix if matched_prefix else "未配對"
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
        cnt_cols = ["帳單月份", "銀行", "交易日期", "交易說明", "金額 (NT$)"] if "銀行" in filtered_df.columns else ["帳單月份", "交易日期", "交易說明", "金額 (NT$)"]
        count_display = filtered_df[cnt_cols].copy()
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
        
        pdf_dir = "./bills"
        if not os.path.exists(pdf_dir):
            os.makedirs(pdf_dir, exist_ok=True)

        st.markdown(
            '<div style="padding: 8px 12px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; margin-bottom: 12px; font-size: 0.85rem; color: #94A3B8;">'
            '📂 <b>帳單目錄：</b> <code>./bills</code> <span style="font-size: 0.75rem; color: #64748B;">(固定路徑)</span>'
            '</div>',
            unsafe_allow_html=True
        )

        pdf_passwords = config_mgr.get("pdf_passwords", [])

        with st.popover(f"🔑 帳單密碼管理 ({len(pdf_passwords)} 組)", use_container_width=True):
            # First button is always "➕ 帳單密碼"
            if st.button("➕ 帳單密碼", key="btn_toggle_add_pw", use_container_width=True):
                st.session_state["show_add_pw_input"] = not st.session_state.get("show_add_pw_input", False)
                st.rerun()

            # Inline add password input area
            if st.session_state.get("show_add_pw_input", False):
                with st.form("form_add_pw_rule", border=False):
                    st.caption("請輸入檔名前綴與對應解密密碼：")
                    add_c_pfx = st.text_input("檔名前綴", placeholder="前綴 (例如: TSB_ / 富邦)...", label_visibility="collapsed")
                    add_c_pwd = st.text_input("解密密碼", placeholder="PDF 密碼...", type="password", label_visibility="collapsed")
                    
                    btn_add_col, btn_cancel_col = st.columns([1, 1])
                    with btn_add_col:
                        add_pw_submit = st.form_submit_button("+", help="確認新增密碼設定", use_container_width=True)
                    with btn_cancel_col:
                        cancel_pw_submit = st.form_submit_button("✖", help="取消", use_container_width=True)

                    if add_pw_submit:
                        clean_pfx = add_c_pfx.strip()
                        clean_pwd = add_c_pwd.strip()
                        if clean_pwd:
                            cur_pws = config_mgr.get("pdf_passwords", [])
                            # If prefix already exists, update password; otherwise append
                            match_item = next((item for item in cur_pws if item.get("prefix", "").strip().lower() == clean_pfx.lower()), None)
                            if match_item:
                                match_item["password"] = clean_pwd
                            else:
                                cur_pws.append({"prefix": clean_pfx, "password": clean_pwd})
                            config_mgr.set("pdf_passwords", cur_pws)
                            st.cache_data.clear()
                            st.session_state.pop("active_months", None)
                            st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                            st.session_state["show_add_pw_input"] = False
                            st.rerun()
                    elif cancel_pw_submit:
                        st.session_state["show_add_pw_input"] = False
                        st.rerun()

            st.markdown("<div style='margin: 8px 0; border-top: 1px solid rgba(255,255,255,0.08);'></div>", unsafe_allow_html=True)

            if not pdf_passwords:
                st.caption("目前尚無密碼設定。請點擊上方「➕ 帳單密碼」新增。")
            else:
                st.caption("依檔名前綴自動配對對應解密密碼：")
                editing_pw_idx = st.session_state.get("editing_pw_idx", None)

                for idx, pw_item in enumerate(pdf_passwords):
                    cur_pfx = pw_item.get("prefix", "")
                    cur_pwd = pw_item.get("password", "")
                    pfx_label = cur_pfx if cur_pfx else "(通用預設)"

                    if editing_pw_idx == idx:
                        # Inline Edit Mode (no navigation)
                        with st.form(f"form_edit_pw_{idx}", border=False):
                            edit_pfx = st.text_input("編輯前綴", value=cur_pfx, placeholder="前綴...", label_visibility="collapsed")
                            edit_pwd = st.text_input("編輯密碼", value=cur_pwd, placeholder="PDF 密碼...", type="password", label_visibility="collapsed")
                            
                            e_save_col, e_cancel_col = st.columns([1, 1])
                            with e_save_col:
                                save_pw_submit = st.form_submit_button("💾", help="儲存變更", use_container_width=True)
                            with e_cancel_col:
                                cancel_edit_pw_submit = st.form_submit_button("✖", help="取消編輯", use_container_width=True)

                            if save_pw_submit:
                                clean_pfx = edit_pfx.strip()
                                clean_pwd = edit_pwd.strip()
                                if clean_pwd:
                                    cur_pws = config_mgr.get("pdf_passwords", [])
                                    cur_pws[idx] = {"prefix": clean_pfx, "password": clean_pwd}
                                    config_mgr.set("pdf_passwords", cur_pws)
                                    st.cache_data.clear()
                                    st.session_state.pop("active_months", None)
                                    st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                                st.session_state.pop("editing_pw_idx", None)
                                st.rerun()
                            elif cancel_edit_pw_submit:
                                st.session_state.pop("editing_pw_idx", None)
                                st.rerun()
                    else:
                        # Normal Display Mode
                        row_info_col, row_edit_col, row_del_col = st.columns([3.2, 1, 1])
                        with row_info_col:
                            masked_pw = "•" * min(6, len(cur_pwd)) if cur_pwd else "(無)"
                            st.markdown(
                                f'<div style="padding: 7px 10px; background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 6px; font-size: 0.84rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">'
                                f'<b style="color: #38BDF8;">🏷️ {pfx_label}</b> <span style="color: #94A3B8; margin-left: 6px; letter-spacing: 2px;">{masked_pw}</span>'
                                f'</div>',
                                unsafe_allow_html=True
                            )
                        with row_edit_col:
                            if st.button("✏️", key=f"btn_edit_pw_{idx}", help="行內編輯", use_container_width=True):
                                st.session_state["editing_pw_idx"] = idx
                                st.rerun()
                        with row_del_col:
                            if st.button("🗑️", key=f"btn_del_pw_{idx}", help="刪除密碼設定", use_container_width=True):
                                cur_pws = config_mgr.get("pdf_passwords", [])
                                if 0 <= idx < len(cur_pws):
                                    cur_pws.pop(idx)
                                    config_mgr.set("pdf_passwords", cur_pws)
                                    st.cache_data.clear()
                                    st.session_state.pop("active_months", None)
                                    st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                                    st.session_state.pop("editing_pw_idx", None)
                                    st.rerun()

        if st.button("🔄 重新掃描帳單", use_container_width=True, help="清除快取並重新掃描所有 PDF 帳單"):
            st.cache_data.clear()
            st.session_state.pop("active_months", None)
            st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
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
            st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
            st.success("已更新過濾條件並儲存！")
            st.rerun()

        # Auto-save min_amount if changed
        if min_amount != saved_min_amt:
            config_mgr.set("min_amount_filter", max(0, int(min_amount)))

    # Main logic
    df, scan_df = load_and_parse_all_pdfs(pdf_dir, pdf_passwords)

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

    # Tabs
    tab1, tab2, tab3 = st.tabs(["📊 總覽報表", "📑 交易明細與搜尋", "📁 帳單檔案管理"])

    # TAB 1: OVERVIEW DASHBOARD
    with tab1:
        excluded_keywords = config_mgr.get("excluded_keywords", [])

        c_month, c_exclude, _ = st.columns([1.2, 1.2, 1.6])
        
        # Filter strictly by 帳單月份 (Statement Month PDF file)
        months = sorted(list(df["帳單月份"].dropna().unique()), reverse=True)
        
        # Initialize session_state for active months on first run (default to only the most recent month)
        if "active_months" not in st.session_state:
            st.session_state["active_months"] = [months[0]] if months else []
            for m in months:
                st.session_state[f"cb_month_{m}"] = (m == months[0])

        # Filter active months to only include existing months in dataset
        active_months = [m for m in st.session_state["active_months"] if m in months]

        # Apply excluded keywords and min_amount threshold exclusively to Tab 1 (Overview Dashboard)
        overview_df = df.copy()
        if excluded_keywords:
            valid_kws = [k.strip() for k in excluded_keywords if k and k.strip()]
            if valid_kws:
                pattern = "|".join([re.escape(k) for k in valid_kws])
                overview_df = overview_df[~overview_df["交易說明"].astype(str).str.contains(pattern, case=False, na=False)]

        if min_amount > 0:
            overview_df = overview_df[overview_df["金額 (NT$)"] > min_amount]

        # Ensure any newly discovered months have checkbox state initialized
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
                        m_count = len(overview_df[overview_df["帳單月份"] == m])
                        banks_in_m = sorted(overview_df[overview_df["帳單月份"] == m]["銀行"].dropna().unique())
                        bank_tag = f" 【{'、'.join(banks_in_m)}】" if banks_in_m else ""
                        st.checkbox(
                            f"📅 {m} 帳單{bank_tag} ({m_count} 筆交易)",
                            key=f"cb_month_{m}"
                        )

                    st.markdown("<br>", unsafe_allow_html=True)
                    apply_btn = st.form_submit_button("套用", use_container_width=True)
                    
                    if apply_btn:
                        st.session_state["active_months"] = [m for m in months if st.session_state.get(f"cb_month_{m}", False)]
                        # Reset Top 10 table checkboxes and adder calculator state
                        st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                        st.rerun()

        with c_exclude:
            with st.popover(f"🚫 項目排除名單 ({len(excluded_keywords)} 項)", use_container_width=True):
                # The very first button is always "排除關鍵字"
                if st.button("➕ 排除關鍵字", key="btn_add_exclude_kw_toggle", use_container_width=True):
                    st.session_state["show_add_exclude_input"] = not st.session_state.get("show_add_exclude_input", False)
                    st.rerun()

                # Inline add keyword input area
                if st.session_state.get("show_add_exclude_input", False):
                    with st.form("form_add_exclude_kw", border=False):
                        st.caption("請輸入欲排除的交易說明關鍵字：")
                        c_in, c_add, c_cancel = st.columns([3.2, 1, 1])
                        with c_in:
                            new_kw = st.text_input("新增排除關鍵字", placeholder="輸入排除關鍵字...", label_visibility="collapsed")
                        with c_add:
                            add_submitted = st.form_submit_button("+", help="新增排除關鍵字", use_container_width=True)
                        with c_cancel:
                            cancel_submitted = st.form_submit_button("✖", help="取消", use_container_width=True)

                        if add_submitted:
                            clean_kw = new_kw.strip()
                            if clean_kw:
                                cur_kws = config_mgr.get("excluded_keywords", [])
                                if clean_kw not in cur_kws:
                                    cur_kws.append(clean_kw)
                                    config_mgr.set("excluded_keywords", cur_kws)
                                    st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                                    st.session_state["show_add_exclude_input"] = False
                                    st.rerun()
                        elif cancel_submitted:
                            st.session_state["show_add_exclude_input"] = False
                            st.rerun()

                st.markdown("<div style='margin: 8px 0; border-top: 1px solid rgba(255,255,255,0.08);'></div>", unsafe_allow_html=True)

                if not excluded_keywords:
                    st.caption("目前尚無排除關鍵字。點擊上方「➕ 排除關鍵字」即可新增。")
                else:
                    st.caption("若交易說明包含以下任一關鍵字，統計時將自動排除：")
                    editing_idx = st.session_state.get("editing_exclude_idx", None)

                    for idx, kw in enumerate(excluded_keywords):
                        if editing_idx == idx:
                            # Inline Edit Mode (no navigation)
                            with st.form(f"form_edit_exclude_{idx}", border=False):
                                e_col_in, e_col_save, e_col_cancel = st.columns([3.2, 1, 1])
                                with e_col_in:
                                    edit_val = st.text_input(
                                        f"編輯關鍵字_{idx}",
                                        value=kw,
                                        placeholder="輸入排除關鍵字...",
                                        label_visibility="collapsed"
                                    )
                                with e_col_save:
                                    save_submitted = st.form_submit_button("💾", help="儲存變更", use_container_width=True)
                                with e_col_cancel:
                                    cancel_edit_submitted = st.form_submit_button("✖", help="取消編輯", use_container_width=True)

                                if save_submitted:
                                    clean_edit = edit_val.strip()
                                    if clean_edit and clean_edit != kw:
                                        cur_kws = config_mgr.get("excluded_keywords", [])
                                        cur_kws[idx] = clean_edit
                                        config_mgr.set("excluded_keywords", cur_kws)
                                        st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                                    st.session_state.pop("editing_exclude_idx", None)
                                    st.rerun()
                                elif cancel_edit_submitted:
                                    st.session_state.pop("editing_exclude_idx", None)
                                    st.rerun()
                        else:
                            # Normal Display Mode
                            row_col_kw, row_col_edit, row_col_del = st.columns([3, 1.2, 1])
                            with row_col_kw:
                                st.markdown(
                                    f'<div style="padding: 7px 10px; background: rgba(239, 68, 68, 0.08); border: 1px solid rgba(239, 68, 68, 0.2); border-radius: 6px; color: #FCA5A5; font-size: 0.86rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{kw}">'
                                    f'🚫 {kw}'
                                    f'</div>',
                                    unsafe_allow_html=True
                                )
                            with row_col_edit:
                                if st.button("✏️", key=f"btn_edit_exclude_{idx}", help="行內編輯", use_container_width=True):
                                    st.session_state["editing_exclude_idx"] = idx
                                    st.rerun()
                            with row_col_del:
                                if st.button("🗑️", key=f"btn_del_exclude_{idx}", help="刪除排除關鍵字", use_container_width=True):
                                    cur_kws = config_mgr.get("excluded_keywords", [])
                                    if 0 <= idx < len(cur_kws):
                                        cur_kws.pop(idx)
                                        config_mgr.set("excluded_keywords", cur_kws)
                                        st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                                        st.session_state.pop("editing_exclude_idx", None)
                                        st.rerun()
        
        selected_months = active_months
        filtered_df = overview_df[overview_df["帳單月份"].isin(selected_months)] if selected_months else pd.DataFrame(columns=overview_df.columns)

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
            st.markdown(
                '<div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.5), rgba(15, 23, 42, 0.6)); '
                'border: 1px dashed rgba(148, 163, 184, 0.25); border-radius: 12px; padding: 48px 24px; '
                'text-align: center; margin: 20px 0; min-height: 260px; display: flex; flex-direction: column; '
                'justify-content: center; align-items: center;">'
                '<div style="font-size: 2.8rem; margin-bottom: 12px;">🗓️</div>'
                '<div style="font-size: 1.15rem; font-weight: 600; color: #F1F5F9; margin-bottom: 8px;">當前未勾選任何帳單月份</div>'
                '<div style="font-size: 0.88rem; color: #94A3B8; max-width: 480px; line-height: 1.6;">'
                '請點擊右上角「<b>🗓️ 選擇帳單月份</b>」下拉選單勾選欲統計之月份，或點擊「<b>🔘 全選</b>」後按「<b>套用</b>」即可即時呈現消費明細與統計圖表。'
                '</div>'
                '</div>',
                unsafe_allow_html=True
            )
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

            # All Filtered Transactions Table & Floating Sticky Adder
            if "top10_adder_open" not in st.session_state:
                st.session_state["top10_adder_open"] = True
            adder_open = st.session_state["top10_adder_open"]

            # Sort all items in range strictly by date descending, then amount descending
            table_df = filtered_df.sort_values(by=["交易日期", "金額 (NT$)"], ascending=[False, False])
            table_cols = ["帳單月份", "銀行", "交易日期", "交易說明", "金額 (NT$)"] if "銀行" in table_df.columns else ["帳單月份", "交易日期", "交易說明", "金額 (NT$)"]
            table_display = table_df[table_cols].copy().reset_index(drop=True)
            table_display["交易日期"] = table_display["交易日期"].dt.strftime('%Y-%m-%d')

            table_title = f"🧾 範圍內消費明細清單 (共 {len(table_display)} 筆)"

            if not adder_open:
                t_col_title, t_col_btn = st.columns([5, 1.2])
                with t_col_title:
                    st.subheader(table_title)
                with t_col_btn:
                    if st.button("🧮 開啟加法器", key="btn_open_adder", use_container_width=True):
                        st.session_state["top10_adder_open"] = True
                        st.rerun()
            else:
                st.subheader(table_title)

            if "adder_reset_id" not in st.session_state:
                st.session_state["adder_reset_id"] = 0

            df_key = f"table_df_sel_{st.session_state['adder_reset_id']}"

            col_config = {
                "金額 (NT$)": st.column_config.NumberColumn("金額 (NT$)", format="NT$ %,d"),
                "銀行": st.column_config.TextColumn("銀行"),
                "交易日期": st.column_config.TextColumn("交易日期"),
                "交易說明": st.column_config.TextColumn("交易說明"),
                "帳單月份": st.column_config.TextColumn("帳單月份")
            }

            # Set table height dynamically so rows display naturally and the outer page scrolls,
            # allowing the sticky floating adder to smoothly track the user's viewport
            tbl_height = max(450, (len(table_display) + 1) * 36 + 10) if len(table_display) > 0 else 400

            if adder_open:
                col_tbl, col_add = st.columns([3, 1], gap="medium")
                with col_tbl:
                    selection_event = st.dataframe(
                        table_display,
                        height=tbl_height,
                        use_container_width=True,
                        hide_index=True,
                        on_select="rerun",
                        selection_mode="multi-row",
                        column_config=col_config,
                        key=df_key
                    )
                with col_add:
                    selected_rows = []
                    if selection_event and hasattr(selection_event, "selection"):
                        sel = selection_event.selection
                        if hasattr(sel, "rows"):
                            selected_rows = list(sel.rows)
                        elif isinstance(sel, dict):
                            selected_rows = list(sel.get("rows", []))
                    elif isinstance(selection_event, dict) and "selection" in selection_event:
                        selected_rows = list(selection_event["selection"].get("rows", []))

                    selected_items = table_display.iloc[selected_rows] if selected_rows else pd.DataFrame()
                    total_sum = selected_items["金額 (NT$)"].sum() if not selected_items.empty else 0
                    sel_count = len(selected_rows)

                    with st.container(border=True):
                        c_h_title, c_h_btn = st.columns([4, 1])
                        with c_h_title:
                            st.markdown("##### 🧮 即時加法器 <span class='top10-adder-marker'></span>", unsafe_allow_html=True)
                        with c_h_btn:
                            if st.button("✖", key="btn_close_adder", help="收合加法器", use_container_width=True):
                                st.session_state["top10_adder_open"] = False
                                st.rerun()

                        if total_sum > 0:
                            v_color = "#38BDF8"
                            b_bg = "rgba(56, 189, 248, 0.12)"
                            b_color = "#38BDF8"
                            b_border = "1px solid rgba(56, 189, 248, 0.3)"
                            b_text = f"● 已勾選 {sel_count} 筆"
                        else:
                            v_color = "#94A3B8"
                            b_bg = "rgba(148, 163, 184, 0.1)"
                            b_color = "#94A3B8"
                            b_border = "1px solid rgba(148, 163, 184, 0.2)"
                            b_text = "○ 請勾選左側項目"

                        card_html = (
                            f'<div style="text-align: center; padding: 14px 8px; margin: 4px 0 6px 0; '
                            f'background: rgba(255, 255, 255, 0.02); border-radius: 8px; border: 1px solid rgba(255, 255, 255, 0.05);">'
                            f'<div style="font-size: 0.76rem; font-weight: 600; color: #94A3B8; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px;">勾選總額 (SUM)</div>'
                            f'<div style="font-family: \'JetBrains Mono\', monospace; font-size: 1.85rem; font-weight: 700; color: {v_color}; line-height: 1.2; text-shadow: 0 2px 10px rgba(56, 189, 248, 0.2);">'
                            f'NT$ {total_sum:,.0f}'
                            f'</div>'
                            f'<div style="display: inline-block; margin-top: 10px; padding: 3px 12px; font-size: 0.75rem; font-weight: 500; color: {b_color}; background: {b_bg}; border: {b_border}; border-radius: 12px;">'
                            f'{b_text}'
                            f'</div>'
                            f'</div>'
                        )
                        st.markdown(card_html, unsafe_allow_html=True)

                        if total_sum > 0:
                            if st.button("🔄 全部重選", key="btn_clear_adder_sel", use_container_width=True, help="清空當前所有勾選項"):
                                st.session_state["adder_reset_id"] = st.session_state.get("adder_reset_id", 0) + 1
                                st.rerun()
            else:
                st.dataframe(
                    table_display,
                    height=tbl_height,
                    use_container_width=True,
                    hide_index=True,
                    column_config=col_config
                )

    # TAB 2: TRANSACTION DETAILS & SEARCH
    with tab2:
        st.subheader("🔍 交易明細查詢與篩選")
        
        f_col1, f_col2 = st.columns([1, 2])
        with f_col1:
            m_options = ["全部"] + sorted(list(df["帳單月份"].unique()), reverse=True)
            default_m_idx = 1 if len(m_options) > 1 else 0
            sel_m = st.selectbox("篩選帳單月份", m_options, index=default_m_idx)
        with f_col2:
            kw = st.text_input("搜尋交易說明關鍵字 (例如: 全聯 / 高鐵 / 露天)", "")

        detail_df = df.copy()
        # Always exclude payment records (only keep positive purchase transactions)
        if not detail_df.empty:
            detail_df = detail_df[detail_df["金額 (NT$)"] > 0]

        if sel_m != "全部":
            detail_df = detail_df[detail_df["帳單月份"] == sel_m]
        if kw.strip():
            norm_kw = unicodedata.normalize('NFKC', kw.strip())
            detail_df = detail_df[detail_df["交易說明"].str.contains(norm_kw, case=False, na=False)]

        cols = ["帳單月份", "銀行", "交易日期", "交易說明", "金額 (NT$)", "來源檔名"] if "銀行" in detail_df.columns else ["帳單月份", "交易日期", "交易說明", "金額 (NT$)", "來源檔名"]
        detail_display = detail_df[cols].copy()
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
            off_cols = ["帳單月份", "銀行", "交易日期", "交易說明", "金額 (NT$)", "來源檔名"] if "銀行" in offset_df.columns else ["帳單月份", "交易日期", "交易說明", "金額 (NT$)", "來源檔名"]
            offset_display = offset_df[off_cols].copy()
            offset_display["交易日期"] = offset_display["交易日期"].dt.strftime('%Y-%m-%d')
            st.dataframe(offset_display, use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
