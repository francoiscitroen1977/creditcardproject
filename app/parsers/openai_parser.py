from __future__ import annotations

import json
import os
from typing import List, Optional

from app.models.transaction import Transaction

from .base import BaseParser, ParserError

try:  # pragma: no cover - optional dependency
    from openai import OpenAI
except Exception:  # pragma: no cover - fallback when package missing
    OpenAI = None


class OpenAIParser(BaseParser):
    name = "openai"

    def __init__(self, client: Optional[OpenAI] = None, model: Optional[str] = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        if client is not None:
            self.client = client
        elif api_key and OpenAI is not None:
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = None

    def is_available(self) -> bool:
        return self.client is not None

    def parse(self, pdf_bytes: bytes) -> List[Transaction]:
        if not self.client:
            raise ParserError("OpenAI client is not configured")

        from app.utils.pdf import extract_text_from_pdf

        text = extract_text_from_pdf(pdf_bytes)
        prompt = (
            "You will receive the raw text of a credit card statement. "
            "Return a JSON array with objects that contain the following keys: "
            "trans_date, post_date, reference_number, description, amount. "
            "Only include rows that represent paid transactions (they contain an amount). "
            "Amounts should be numbers where charges are negative (money spent) and payments are positive."
        )
        response = self.client.responses.create(
            model=self.model,
            input=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
        )
        try:
            raw = response.output[0].content[0].text  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - API surface safety
            raise ParserError(f"Unexpected OpenAI response format: {exc}") from exc

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ParserError(f"Failed to decode JSON from OpenAI: {exc}") from exc

        transactions_data = payload.get("transactions") or payload
        if not isinstance(transactions_data, list):
            raise ParserError("OpenAI response does not contain a list of transactions")

        transactions: List[Transaction] = []
        for item in transactions_data:
            try:
                transactions.append(Transaction(**item))
            except Exception as exc:
                raise ParserError(f"Invalid transaction payload: {exc}") from exc
        if not transactions:
            raise ParserError("OpenAI did not return any transactions")
        return transactions
