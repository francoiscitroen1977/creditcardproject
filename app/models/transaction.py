from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, validator


class Transaction(BaseModel):
    """Represents a single paid credit card transaction."""

    trans_date: str = Field(..., description="Transaction date as it appears on the statement")
    post_date: str = Field(..., description="Posting date from the statement")
    reference_number: Optional[str] = Field(
        default=None,
        description="Reference number supplied by the issuer (may be missing for fees)",
    )
    description: str = Field(..., description="Transaction description")
    amount: Decimal = Field(..., description="Amount charged (positive = payment made by card holder)")

    @validator("trans_date", "post_date", pre=True)
    def _strip_strings(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("value must not be None")
        if isinstance(value, str):
            return value.strip()
        return str(value)

    @validator("reference_number", pre=True, always=True)
    def _normalise_reference(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = str(value).strip()
        return value or None

    @validator("description", pre=True)
    def _normalise_description(cls, value: Optional[str]) -> str:
        if value is None:
            raise ValueError("description must not be None")
        return " ".join(str(value).split())

    class Config:
        json_schema_extra = {
            "example": {
                "trans_date": "01/05",
                "post_date": "01/06",
                "reference_number": "1234567890",
                "description": "COFFEE SHOP NYC",
                "amount": "-4.95",
            }
        }
