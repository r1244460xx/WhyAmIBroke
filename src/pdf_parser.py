import os
import re
import unicodedata
from datetime import datetime
from abc import ABC, abstractmethod
import pypdf

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class BaseBankParserStrategy(ABC):
    """Abstract Base Class for Bank Statement Parsing Strategies."""

    @abstractmethod
    def get_bank_name(self) -> str:
        """Return the bank display name."""
        pass

    @abstractmethod
    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        """Determine if this strategy can parse the given PDF based on filename or text lines."""
        pass

    def detect_statement_month(self, file_name: str, lines: list[str]) -> str:
        """Detect statement year and month (YYYY-MM) from filename or text content."""
        m = re.search(r'(20\d{2})[-_]?([01]\d)', file_name)
        if m:
            return f"{m.group(1)}-{m.group(2)}"

        for line in lines[:60]:
            m2 = re.search(r'(1\d{2})[/年-]([01]?\d)[/月-]?', line)
            if m2:
                year = str(int(m2.group(1)) + 1911)
                month = m2.group(2).zfill(2)
                return f"{year}-{month}"

            m3 = re.search(r'(20\d{2})[/年-]([01]?\d)[/月-]?', line)
            if m3:
                return f"{m3.group(1)}-{m3.group(2).zfill(2)}"

        return datetime.now().strftime("%Y-%m")

    @abstractmethod
    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        """Extract transactions from text lines."""
        pass

    def clean_description(self, desc: str) -> str:
        """Normalize Unicode characters (NFKC) and clean trailing whitespace / country codes."""
        if not desc:
            return ""
        desc = unicodedata.normalize('NFKC', desc).strip()
        desc = re.sub(r'\s+TW$', '', desc).strip()
        return desc

    def format_roc_date(self, date_str: str) -> str:
        """Format ROC date (e.g. 115/07/24) into standard ISO YYYY-MM-DD string."""
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


class TaishinStrategy(BaseBankParserStrategy):
    """Parsing strategy for Taishin Bank (台新銀行)."""

    def get_bank_name(self) -> str:
        return "台新銀行"

    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        fn_upper = file_name.upper()
        if "TSB" in fn_upper or "台新" in file_name:
            return True
        for line in lines[:30]:
            if "台新" in line or "Richart" in line or "TAISHIN" in line.upper():
                return True
        return False

    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        transactions = []
        current_card = ""
        date_pair_pattern = r'^(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s+(\d{2,4}/\d{1,2}/\d{1,2}|\d{1,2}/\d{1,2})\s+(.+)$'

        idx = 0
        while idx < len(lines):
            line = lines[idx]

            card_match = re.search(r'卡號末[4四４]碼[:：]?\s*(\d{4})', line)
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

                    if not desc or re.match(r'^-?\d+(,\d+)*(\.\d+)?$', desc):
                        if idx > 0:
                            prev_line = lines[idx - 1]
                            if not re.search(r'^\d{2,4}/\d{1,2}/\d{1,2}', prev_line) and not any(kw in prev_line for kw in ["消費日", "交易日期", "卡號末四碼", "卡號末4碼", "頁數"]):
                                desc = prev_line

                    if not desc:
                        desc = rest

                    desc = self.clean_description(desc)
                    trans_date = self.format_roc_date(trans_date_raw)
                    post_date = self.format_roc_date(post_date_raw)

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


class FubonStrategy(BaseBankParserStrategy):
    """Parsing strategy for Taipei Fubon Bank (台北富邦銀行)."""

    def get_bank_name(self) -> str:
        return "台北富邦"

    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        if "富邦" in file_name or "FUBON" in file_name.upper():
            return True
        for line in lines[:30]:
            if "富邦" in line or "fubon" in line.lower():
                return True
        return False

    def detect_statement_month(self, file_name: str, lines: list[str]) -> str:
        for line in lines[:20]:
            m = re.search(r'(1\d{2})[/年-]([01]?\d)\s+\d{1,3}(?:,\d{3})*', line)
            if m:
                year = str(int(m.group(1)) + 1911)
                month = m.group(2).zfill(2)
                return f"{year}-{month}"
        return super().detect_statement_month(file_name, lines)

    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        transactions = []
        current_card = ""

        # Format: 115/07/22 富邦momo-EC 115/07/24 TWD 1,438
        line_pattern = re.compile(
            r'^(\d{2,4}/\d{1,2}/\d{1,2})\s+(.+?)\s+(\d{2,4}/\d{1,2}/\d{1,2})\s+(?:[A-Za-z]{3}\s+)?(-?[\d,]+(?:\.\d+)?)$'
        )

        for line in lines:
            card_match = re.search(r'末[4四４]碼\s*(\d{4})', line)
            if card_match:
                current_card = card_match.group(1)
                continue

            match = line_pattern.match(line)
            if match:
                trans_date_raw, desc_raw, post_date_raw, amt_raw = match.groups()
                amount = float(amt_raw.replace(",", ""))
                desc = self.clean_description(desc_raw)
                trans_date = self.format_roc_date(trans_date_raw)
                post_date = self.format_roc_date(post_date_raw)

                transactions.append({
                    "trans_date": trans_date,
                    "post_date": post_date,
                    "description": desc,
                    "amount": amount,
                    "card_no": current_card,
                    "raw_line": line
                })

        return transactions


class SinopacStrategy(BaseBankParserStrategy):
    """Parsing strategy for Bank SinoPac (永豐銀行)."""

    def get_bank_name(self) -> str:
        return "永豐銀行"

    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        if "永豐" in file_name or "SINOPAC" in file_name.upper():
            return True
        for line in lines[:30]:
            if "永豐" in line or "sinopac" in line.lower() or "DAWHO" in line or "SPORT" in line:
                return True
        return False

    def detect_statement_month(self, file_name: str, lines: list[str]) -> str:
        for line in lines[:20]:
            m = re.search(r'(20\d{2})年\s*([01]?\d)月', line)
            if m:
                return f"{m.group(1)}-{m.group(2).zfill(2)}"
        return super().detect_statement_month(file_name, lines)

    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        transactions = []
        stmt_year = datetime.now().year
        stmt_month = datetime.now().month
        if statement_month and "-" in statement_month:
            try:
                y, m = statement_month.split("-")
                stmt_year, stmt_month = int(y), int(m)
            except ValueError:
                pass

        # Pattern: MM/DD MM/DD [CARD_4?] DESC... AMOUNT
        line_pattern = re.compile(
            r'^(\d{1,2}/\d{1,2})\s+(\d{1,2}/\d{1,2})(?:\s+(\d{4}))?\s+(.+?)\s+(-?[\d,]+(?:\.\d+)?)$'
        )

        for line in lines:
            if "應繳金額合計" in line or "分期說明" in line:
                continue

            match = line_pattern.match(line)
            if match:
                t_date_raw, p_date_raw, inline_card, desc_raw, amt_raw = match.groups()
                amount = float(amt_raw.replace(",", ""))

                # Strip primary card indicator A- / B-
                desc = re.sub(r'^[A-Za-z]-\s*', '', desc_raw.strip())
                desc = self.clean_description(desc)

                trans_date = self._format_mmdd(t_date_raw, stmt_year, stmt_month)
                post_date = self._format_mmdd(p_date_raw, stmt_year, stmt_month)

                transactions.append({
                    "trans_date": trans_date,
                    "post_date": post_date,
                    "description": desc,
                    "amount": amount,
                    "card_no": inline_card if inline_card else "",
                    "raw_line": line
                })

        return transactions

    def _format_mmdd(self, mmdd_str: str, stmt_year: int, stmt_month: int) -> str:
        parts = mmdd_str.split("/")
        m = int(parts[0])
        d = int(parts[1])
        y = stmt_year
        if stmt_month == 1 and m == 12:
            y -= 1
        elif stmt_month == 12 and m == 1:
            y += 1
        return f"{y:04d}-{m:02d}-{d:02d}"


class DBSStrategy(BaseBankParserStrategy):
    """Parsing strategy for DBS Bank (星展銀行)."""

    def get_bank_name(self) -> str:
        return "星展銀行"

    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        if "星展" in file_name or "DBS" in file_name.upper():
            return True
        for line in lines[:30]:
            if "星展" in line or "DBS" in line.upper():
                return True
        return False

    def detect_statement_month(self, file_name: str, lines: list[str]) -> str:
        for line in lines[:20]:
            m = re.search(r'(20\d{2})年\s*([01]?\d)月', line)
            if m:
                return f"{m.group(1)}-{m.group(2).zfill(2)}"
        return super().detect_statement_month(file_name, lines)

    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        transactions = []
        current_card = ""

        card_pattern = re.compile(r'卡號末[4四４]碼\s*(\d{4})')
        line_pattern = re.compile(
            r'^(\d{4}/\d{1,2}/\d{1,2})\s+(\d{4}/\d{1,2}/\d{1,2})\s+(.+?)\s+(-?[\d,]+(?:\.\d+)?)(?:\s+[A-Z]{2})?$'
        )

        for line in lines:
            card_match = card_pattern.search(line)
            if card_match:
                current_card = card_match.group(1)
                continue

            match = line_pattern.match(line)
            if match:
                t_date_raw, p_date_raw, desc_raw, amt_raw = match.groups()
                amount = float(amt_raw.replace(",", ""))
                desc = self.clean_description(desc_raw)

                trans_date = t_date_raw.replace("/", "-")
                post_date = p_date_raw.replace("/", "-")

                transactions.append({
                    "trans_date": trans_date,
                    "post_date": post_date,
                    "description": desc,
                    "amount": amount,
                    "card_no": current_card,
                    "raw_line": line
                })

        return transactions


class MegaStrategy(BaseBankParserStrategy):
    """Parsing strategy for Mega International Commercial Bank (兆豐銀行)."""

    def get_bank_name(self) -> str:
        return "兆豐銀行"

    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        if "MEGA" in file_name.upper() or "兆豐" in file_name:
            return True
        for line in lines[:30]:
            if "兆豐" in line or "MEGA" in line.upper():
                return True
        return False

    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        return TaishinStrategy().parse_transactions(lines, statement_month)


class GenericBankStrategy(BaseBankParserStrategy):
    """Fallback strategy for unknown banks."""

    def get_bank_name(self) -> str:
        return "通用銀行"

    def can_handle(self, file_name: str, lines: list[str]) -> bool:
        return True

    def parse_transactions(self, lines: list[str], statement_month: str = "") -> list[dict]:
        txs = TaishinStrategy().parse_transactions(lines, statement_month)
        if txs:
            return txs
        txs = FubonStrategy().parse_transactions(lines, statement_month)
        if txs:
            return txs
        txs = SinopacStrategy().parse_transactions(lines, statement_month)
        return txs


class CreditCardPDFParser:
    """
    Context class for credit card PDF parsing using Strategy Pattern.
    Delegates parsing to specialized bank strategies.
    """

    def __init__(self, password=None, strategies=None):
        self.password = password
        self.strategies = strategies or [
            TaishinStrategy(),
            FubonStrategy(),
            SinopacStrategy(),
            DBSStrategy(),
            MegaStrategy(),
            GenericBankStrategy()
        ]

    def extract_text_from_pdf(self, pdf_path):
        """Extract all text lines from PDF using pdfplumber with fallback to pypdf."""
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
        """Parse a statement PDF and return structured metadata and transaction list."""
        file_name = os.path.basename(pdf_path)
        lines = self.extract_text_from_pdf(pdf_path)

        strategy = self._select_strategy(file_name, lines)
        statement_month = strategy.detect_statement_month(file_name, lines)
        transactions = strategy.parse_transactions(lines, statement_month)

        return {
            "bank_name": strategy.get_bank_name(),
            "file_name": file_name,
            "statement_month": statement_month,
            "total_lines": len(lines),
            "transactions": transactions,
            "raw_lines": lines
        }

    def _select_strategy(self, file_name: str, lines: list[str]) -> BaseBankParserStrategy:
        for strategy in self.strategies:
            if strategy.can_handle(file_name, lines):
                return strategy
        return GenericBankStrategy()

    # Legacy delegation helpers for backwards compatibility
    def _detect_statement_month(self, file_name, lines):
        return self._select_strategy(file_name, lines).detect_statement_month(file_name, lines)

    def _parse_transactions(self, lines):
        return self._select_strategy("", lines).parse_transactions(lines)

    def _clean_description(self, desc):
        return BaseBankParserStrategy.clean_description(self, desc)

    def _format_roc_date(self, date_str):
        return BaseBankParserStrategy.format_roc_date(self, date_str)
