from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from app.models.transaction import Transaction


class ParserError(RuntimeError):
    """Raised when a parser cannot extract transactions."""


class BaseParser(ABC):
    name: str

    @abstractmethod
    def parse(self, pdf_bytes: bytes) -> List[Transaction]:
        """Return a list of transactions extracted from the PDF."""

    def is_available(self) -> bool:
        return True
