from __future__ import annotations

import csv
import io
import json
from typing import Iterable, List, Optional

from app.models.extraction import ExtractionResult
from app.models.transaction import Transaction
from app.parsers.base import BaseParser, ParserError
from app.parsers.statement_parser import StatementParser


class ExtractionService:
    """Coordinates PDF parsing and exporting."""

    def __init__(self, parsers: Optional[Iterable[BaseParser]] = None, default_parser_name: str = "statement") -> None:
        self._parsers_by_name: dict[str, BaseParser] = {}
        self.selected_parser_name: str = default_parser_name

        if parsers is not None:
            provided_parsers: List[BaseParser] = list(parsers)
            for parser in provided_parsers:
                name = parser.name.lower()
                self._parsers_by_name[name] = parser
        else:
            statement_parser = StatementParser()
            self._parsers_by_name[statement_parser.name.lower()] = statement_parser

        if self.selected_parser_name not in self._parsers_by_name:
            # fall back to the statement parser if the desired default isn't available
            self.selected_parser_name = "statement"

        self._refresh_parser_order()

    @property
    def parser_options(self) -> List[str]:
        return list(self._parsers_by_name.keys())

    def set_active_parser(self, parser_name: str) -> None:
        parser_key = parser_name.lower()
        if parser_key not in self._parsers_by_name:
            raise ParserError(f"Unknown parser: {parser_name}")
        self.selected_parser_name = parser_key
        self._refresh_parser_order()

    def _refresh_parser_order(self) -> None:
        selected = self._parsers_by_name.get(self.selected_parser_name)
        remaining = [p for name, p in self._parsers_by_name.items() if name != self.selected_parser_name]
        self.parsers = [selected] if selected else []
        self.parsers.extend(remaining)

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

