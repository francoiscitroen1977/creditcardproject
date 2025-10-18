from __future__ import annotations

from typing import List

from app.models.transaction import Transaction
from app.utils.cardholder_summary import extract_transactions

from .base import BaseParser, ParserError


class HeuristicParser(BaseParser):
    name = "heuristic"

    def parse(self, pdf_bytes: bytes) -> List[Transaction]:
        extracted = extract_transactions(pdf_bytes)
        if not extracted:
            raise ParserError("No Cardholder Account Summary transactions found")

        transactions: List[Transaction] = []
        for item in extracted:
            amount = item.amount
            if amount == 0:
                continue
            try:
                transactions.append(
                    Transaction(
                        trans_date=item.trans_date,
                        post_date=item.post_date,
                        reference_number=item.reference_number,
                        description=item.description,
                        amount=amount,
                    )
                )
            except Exception as exc:  # pragma: no cover - defensive
                raise ParserError(f"Invalid transaction extracted: {exc}") from exc

        if not transactions:
            raise ParserError("No valid transactions extracted")
        return transactions
