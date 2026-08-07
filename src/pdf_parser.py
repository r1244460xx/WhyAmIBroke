import os
import re
from datetime import datetime
import pypdf
try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class CreditCardPDFParser:
    def __init__(self, password=None):
        self.password = password

    def extract_text_from_pdf(self, pdf_path):
        """Extract all text lines from PDF using pypdf / pdfplumber."""
        lines = []
        if pdfplumber:
            try:
                with pdfplumber.open(pdf_path, password=self.password if self.password else None) as pdf:
                    for page in pdf.pages:
                        text = page.extract_text()
                        if text:
                            lines.extend(text.split("\n"))
            except Exception as e:
                print(f"pdfplumber failed ({e}), falling back to pypdf...")
                lines = []

        if not lines:
            try:
                reader = pypdf.PdfReader(pdf_path)
                if reader.is_encrypted and self.password:
                    reader.decrypt(self.password)
                for page in reader.pages:
                    text = page.extract_text()
                    if text:
                        lines.extend(text.split("\n"))
            except Exception as e:
                print(f"pypdf extraction failed: {e}")

        return [line.strip() for line in lines if line.strip()]

    def parse_pdf(self, pdf_path):
        file_name = os.path.basename(pdf_path)
        lines = self.extract_text_from_pdf(pdf_path)

        statement_month = self._detect_statement_month(file_name, lines)
        transactions = self._parse_transactions(lines)

        return {
            "file_name": file_name,
            "statement_month": statement_month,
            "total_lines": len(lines),
            "transactions": transactions,
            "raw_lines": lines
        }

    def _detect_statement_month(self, file_name, lines):
        # 1. From filename (e.g. TSB_Creditcard_Estatement_202601.pdf)
        m = re.search(r'(20\d{2})[-_]?([01]\d)', file_name)
        if m:
            return f"{m.group(1)}-{m.group(2)}"

        # 2. From text lines (ROC year or AD year)
        for line in lines:
            m2 = re.search(r'(1\d{2})[/年-]([01]?\d)[/月-]', line)
            if m2:
                year = str(int(m2.group(1)) + 1911)
                month = m2.group(2).zfill(2)
                return f"{year}-{month}"
            
            m3 = re.search(r'(20\d{2})[/年-]([01]?\d)[/月-]', line)
            if m3:
                return f"{m3.group(1)}-{m3.group(2).zfill(2)}"

        return datetime.now().strftime("%Y-%m")

    def _parse_transactions(self, lines):
        transactions = []
        current_card = ""

        # Pattern for Taishin / ROC year transactions:
        # 114/12/05 114/12/08 連加＊LINEPAY*noneTAIPEI 30 TW
        # 114/12/08 114/12/09 網路銀行繳款 -39,893
        # 114/12/22 114/12/24 ALP*Beijing MetroBeijin 22 1222 CN CNY 5.00
        
        # Matches:
        # Group 1: 消費日 (e.g. 114/12/05 or 2026/01/05 or 01/05)
        # Group 2: 入帳日 (e.g. 114/12/08)
        # Group 3: 交易說明 & 金額 & 備註
        
        date_pair_pattern = r'^(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s+(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s+(.+)$'

        idx = 0
        while idx < len(lines):
            line = lines[idx]

            # Check if line indicates card number info e.g. (卡號末四碼:9306)
            card_match = re.search(r'卡號末四碼[:：]?\s*(\d{4})', line)
            if card_match:
                current_card = card_match.group(1)
                idx += 1
                continue

            match = re.search(date_pair_pattern, line)
            if match:
                trans_date_raw = match.group(1)
                post_date_raw = match.group(2)
                rest = match.group(3).strip()

                # Extract amount from rest of line
                # In rest: Description Amount [TW/CN/etc] [Currency...]
                # Find amount string: e.g. -39,893 or 30 or 1,470 or -799
                # Pattern searching for monetary amount in rest
                
                # Split rest to find amount
                tokens = rest.split()
                amount = None
                desc_parts = []
                
                for i, token in enumerate(tokens):
                    # Check if token is a valid amount e.g. -39,893 or 30 or 1,470.50
                    clean_token = token.replace(",", "")
                    if re.match(r'^-?\d+(\.\d+)?$', clean_token):
                        # Verify this isn't just a day/date code in foreign currency line
                        try:
                            val = float(clean_token)
                            # First numeric token in rest is typically the TWD Amount
                            amount = val
                            desc_parts = tokens[:i]
                            break
                        except ValueError:
                            pass

                if amount is not None:
                    desc = " ".join(desc_parts).strip() if desc_parts else rest
                    
                    # Clean up description (remove suffixes like TW, TAIPEI if attached to merchant name)
                    desc = self._clean_description(desc)

                    trans_date = self._format_roc_date(trans_date_raw)
                    post_date = self._format_roc_date(post_date_raw)

                    # Filter out payments/transfers if user only wants expenses, or keep payments as negative/payment type
                    transactions.append({
                        "trans_date": trans_date,
                        "post_date": post_date,
                        "description": desc,
                        "amount": amount,
                        "card_no": current_card,
                        "raw_line": line
                    })

            idx += 1

        return transactions

    def _clean_description(self, desc):
        # Remove trailing city/country codes like TAIPEI TW, Taipei, TAOYUA TW if stuck at end
        desc = re.sub(r'(?:TAIPEI|Taipei|TAOYUA|KAOHSI|NEW TAI)\s*(?:TW)?$', '', desc).strip()
        desc = re.sub(r'TW$', '', desc).strip()
        # Clean LINEPAY prefix formatting e.g. 連加＊LINEPAY*none -> LINE Pay / 連加
        return desc

    def _format_roc_date(self, date_str):
        parts = date_str.split("/")
        if len(parts) == 3:
            y = int(parts[0])
            m = int(parts[1])
            d = int(parts[2])
            if y < 1000:
                y += 1911 # Convert ROC year to AD
            return f"{y:04d}-{m:02d}-{d:02d}"
        elif len(parts) == 2:
            m = int(parts[0])
            d = int(parts[1])
            y = datetime.now().year
            return f"{y:04d}-{m:02d}-{d:02d}"
        return date_str
