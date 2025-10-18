from __future__ import annotations

import re
from decimal import Decimal
from typing import List

from app.models.transaction import Transaction

from .base import BaseParser, ParserError


TRANSACTION_PATTERN = re.compile(
    r"""
    ^\s*
    (?P<trans_date>\d{1,2}/\d{1,2})\s+
    (?P<post_date>\d{1,2}/\d{1,2})\s+
    (?P<reference_number>[A-Za-z0-9\-]+)\s+
    (?P<description>.*?)\s+
    (?P<amount>-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{2})?)
    \s*$
    """,
    re.VERBOSE,
)


class HeuristicParser(BaseParser):
    name = "heuristic"

    def parse(self, pdf_bytes: bytes) -> List[Transaction]:
        from app.utils.pdf import extract_text_from_pdf

        text = extract_text_from_pdf(pdf_bytes)
        lines = text.splitlines()
        transactions: List[Transaction] = []
        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue
            match = TRANSACTION_PATTERN.match(line)
            if not match:
                continue
            amount_raw = match.group("amount").replace("$", "").replace(",", "")
            try:
                amount = Decimal(amount_raw)
            except Exception as exc:  # pragma: no cover - defensive
                raise ParserError(f"Unable to parse amount '{amount_raw}': {exc}") from exc
            if amount == 0:
                continue
            transaction = Transaction(
                trans_date=match.group("trans_date"),
                post_date=match.group("post_date"),
                reference_number=match.group("reference_number"),
                description=match.group("description"),
                amount=amount,
            )
            transactions.append(transaction)
        if not transactions:
            raise ParserError("No transactions matched the heuristic pattern")
        return transactions
