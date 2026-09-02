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
        m = re.search(r'(20\d{2})[-_]?([01]\d)', file_name)
        if m:
            return f"{m.group(1)}-{m.group(2)}"

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

        date_pair_pattern = r'^(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s+(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s+(.+)$'

        idx = 0
        while idx < len(lines):
            line = lines[idx]

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

                tokens = rest.split()
                amount = None
                desc_parts = []
                
                for i, token in enumerate(tokens):
                    clean_token = token.replace(",", "")
                    if re.match(r'^-?\d+(\.\d+)?$', clean_token):
                        try:
                            val = float(clean_token)
                            amount = val
                            desc_parts = tokens[:i]
                            break
                        except ValueError:
                            pass

                if amount is not None:
                    desc = " ".join(desc_parts).strip() if desc_parts else ""

                    # If description is empty or numeric (e.g. "5,825"), check the line right above!
                    if not desc or re.match(r'^-?\d+(,\d+)*(\.\d+)?$', desc):
                        if idx > 0:
                            prev_line = lines[idx - 1]
                            # Make sure prev_line is not a header, not a date line, and not a card info line
                            if not re.search(r'^\d{2,4}/\d{1,2}/\d{1,2}', prev_line) and not any(kw in prev_line for kw in ["消費日", "交易日期", "卡號末四碼", "頁數"]):
                                desc = prev_line

                    if not desc:
                        desc = rest

                    desc = self._clean_description(desc)

                    trans_date = self._format_roc_date(trans_date_raw)
                    post_date = self._format_roc_date(post_date_raw)

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
        if not desc:
            return ""
        import unicodedata
        desc = unicodedata.normalize('NFKC', desc).strip()
        # Clean trailing country code TW if separated by space
        desc = re.sub(r'\s+TW$', '', desc).strip()
        return desc

    def _format_roc_date(self, date_str):
        parts = date_str.split("/")
        if len(parts) == 3:
            y = int(parts[0])
            m = int(parts[1])
            d = int(parts[2])
            if y < 1000:
                y += 1911
            return f"{y:04d}-{m:02d}-{d:02d}"
        elif len(parts) == 2:
            m = int(parts[0])
            d = int(parts[1])
            y = datetime.now().year
            return f"{y:04d}-{m:02d}-{d:02d}"
        return date_str
