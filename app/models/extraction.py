from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from .transaction import Transaction


class ExtractionResult(BaseModel):
    """Container for extraction results."""

    parser_name: str = Field(..., description="Name of the parser that generated the result")
    transactions: List[Transaction] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    errors: Optional[List[str]] = Field(default=None)

    @property
    def has_transactions(self) -> bool:
        return bool(self.transactions)
