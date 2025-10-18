from __future__ import annotations

import csv
import io
import json
from typing import Iterable, List, Optional

from app.models.extraction import ExtractionResult
from app.models.transaction import Transaction
from app.parsers.base import BaseParser, ParserError
from app.parsers.heuristic_parser import HeuristicParser
from app.parsers.openai_parser import OpenAIParser


class ExtractionService:
    """Coordinates PDF parsing and exporting."""

    def __init__(self, parsers: Optional[Iterable[BaseParser]] = None) -> None:
        if parsers is not None:
            self.parsers: List[BaseParser] = list(parsers)
        else:
            openai_parser = OpenAIParser()
            self.parsers = []
            if openai_parser.is_available():
                self.parsers.append(openai_parser)
            self.parsers.append(HeuristicParser())

    def extract(self, pdf_bytes: bytes) -> ExtractionResult:
        errors: List[str] = []
        for parser in self.parsers:
            try:
                transactions = parser.parse(pdf_bytes)
            except ParserError as exc:
                errors.append(f"{parser.name}: {exc}")
                continue
            return ExtractionResult(parser_name=parser.name, transactions=transactions, errors=errors or None)
        raise ParserError("All parsers failed to extract transactions: " + "; ".join(errors))

    def to_json(self, transactions: Iterable[Transaction]) -> str:
        return json.dumps([t.model_dump() for t in transactions], indent=2, default=str)

    def to_csv(self, transactions: Iterable[Transaction]) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Trans Date", "Post Date", "Reference Number", "Description", "Amount"])
        for transaction in transactions:
            writer.writerow(
                [
                    transaction.trans_date,
                    transaction.post_date,
                    transaction.reference_number,
                    transaction.description,
                    transaction.amount,
                ]
            )
        return buffer.getvalue()
