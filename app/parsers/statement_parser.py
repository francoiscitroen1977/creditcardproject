from __future__ import annotations

import re
from decimal import Decimal
from typing import List, Optional

from app.models.transaction import Transaction
from app.utils.pdf import extract_text_from_pdf

from .base import BaseParser, ParserError

# Regular expressions to detect relevant pieces of data
DATE_PREFIX_RE = re.compile(r"^\d{2}/\d{2}")
AMOUNT_RE = re.compile(
    r"(?P<value>\(?-?\$?\d[\d,]*\.\d{2}\)?)(?:\s*(?P<credit>CR))?$"
)

# Phrases that signal the table header or the end of the summary section
HEADER_TOKENS = ("TRANS DATE", "POST DATE", "AMOUNT")
SECTION_TITLES = (
    "CARDHOLDER ACCOUNT SUMMARY",
    "CARDHOLDER ACCOUNT SUMMARY CONTINUED",
)
SECTION_END_PREFIXES = (
    "TOTAL",
    "STATEMENT",
    "CONTINUED ON NEXT PAGE",
    "SEE YOUR ACCOUNT",
)


class StatementParser(BaseParser):
    """Parse credit card statements using a deterministic table reader."""

    name = "statement"

    def parse(self, pdf_bytes: bytes) -> List[Transaction]:
        text = extract_text_from_pdf(pdf_bytes)
        if not text.strip():
            raise ParserError("PDF does not contain extractable text")

        raw_rows = self._collect_raw_rows(text)
        if not raw_rows:
            raise ParserError("No Cardholder Account Summary rows found")

        transactions: List[Transaction] = []
        for row in raw_rows:
            transaction = self._parse_row(row)
            if transaction is not None:
                transactions.append(transaction)

        if not transactions:
            raise ParserError("No valid transactions extracted")
        return transactions

    def _collect_raw_rows(self, text: str) -> List[str]:
        rows: List[str] = []
        in_section = False
        header_seen = False

        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            upper_line = line.upper()

            if any(title in upper_line for title in SECTION_TITLES):
                in_section = True
                header_seen = False
                continue

            if not in_section:
                continue

            if all(token in upper_line for token in HEADER_TOKENS):
                header_seen = True
                continue

            if not header_seen:
                continue

            if any(upper_line.startswith(prefix) for prefix in SECTION_END_PREFIXES):
                in_section = False
                header_seen = False
                continue

            if DATE_PREFIX_RE.match(line):
                rows.append(line)
            elif rows:
                # Continuation of the previous row (multi-line descriptions)
                rows[-1] = f"{rows[-1]} {line}"

        return rows

    def _parse_row(self, row: str) -> Transaction:
        amount_match = AMOUNT_RE.search(row)
        if not amount_match:
            raise ParserError(f"Unable to locate amount in row: {row}")

        amount_text = amount_match.group("value")
        credit_marker = bool(amount_match.group("credit"))
        amount = self._parse_amount(amount_text, credit_marker)

        line_body = row[: amount_match.start()].rstrip()
        tokens = line_body.split()
        if len(tokens) < 3:
            raise ParserError(f"Row does not contain enough columns: {row}")

        trans_date, post_date = tokens[0], tokens[1]
        reference, description = self._split_reference_and_description(tokens[2:])
        if not description:
            raise ParserError(f"Missing description in row: {row}")

        try:
            return Transaction(
                trans_date=trans_date,
                post_date=post_date,
                reference_number=reference,
                description=description,
                amount=amount,
            )
        except Exception as exc:  # pragma: no cover - validation safety net
            raise ParserError(f"Invalid transaction row: {exc}") from exc

    def _split_reference_and_description(self, tokens: List[str]) -> tuple[Optional[str], str]:
        if not tokens:
            return None, ""

        first_token = tokens[0]
        digits = re.sub(r"\D", "", first_token)
        reference: Optional[str] = None
        description_tokens = tokens
        if len(digits) >= 6:
            reference = digits
            description_tokens = tokens[1:]

        description = " ".join(description_tokens).strip()
        return reference, description

    def _parse_amount(self, value: str, credit_marker: bool) -> Decimal:
        cleaned = value.replace("$", "").replace(",", "").strip()
        negative = credit_marker

        if cleaned.endswith("-"):
            negative = True
            cleaned = cleaned[:-1].strip()
        if cleaned.startswith("-"):
            negative = True
            cleaned = cleaned[1:].strip()
        if cleaned.startswith("(") and cleaned.endswith(")"):
            negative = True
            cleaned = cleaned[1:-1].strip()

        amount = Decimal(cleaned)
        return -amount if negative else amount


__all__ = ["StatementParser"]
