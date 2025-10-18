"""Utilities for extracting Cardholder Account Summary transactions."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, List, Optional

# NOTE: Some environments install the legacy ``fitz`` package instead of
# ``PyMuPDF``.  The legacy package exposes a different API and does not provide
# ``fitz.open`` which we rely on.  Try to import the modern PyMuPDF package and
# gracefully fall back to ``pymupdf`` when necessary.
try:  # pragma: no cover - import side effects only exercised at runtime
    import fitz  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - exercised when ``fitz`` is missing
    try:
        import pymupdf as fitz  # type: ignore[attr-defined]
    except ImportError as exc:  # pragma: no cover - surfacing clear guidance
        raise ImportError(
            "PyMuPDF is required for PDF extraction; install the 'pymupdf' package"
        ) from exc
else:  # pragma: no cover - executed during normal runtime
    if not hasattr(fitz, "open"):
        try:
            import pymupdf as fitz  # type: ignore[attr-defined]
        except ImportError as exc:  # pragma: no cover - surfacing clear guidance
            raise ImportError(
                "PyMuPDF is required for PDF extraction; install the 'pymupdf' package"
            ) from exc
from PIL import Image

# Section titles to detect relevant pages
SECTION_TITLES = (
    "CARDHOLDER ACCOUNT SUMMARY",
    "CARDHOLDER ACCOUNT SUMMARY CONTINUED",
)

# Row starts with two dates (MM/DD) and ends with a money amount
ROW_RE = re.compile(
    r"^(?P<trans>\d{2}/\d{2})\s+"
    r"(?P<post>\d{2}/\d{2})\s+"
    r"(?P<body>.+?)\s+"
    r"(?P<amt>-?\$?\d{1,3}(?:,\d{3})*\.\d{2})$"
)

# A line that ends with a currency amount
MONEY_TAIL_RE = re.compile(r"-?\$?\d{1,3}(?:,\d{3})*\.\d{2}$")


@dataclass(slots=True)
class ExtractedTransaction:
    """Lightweight container for extracted transaction data."""

    trans_date: str
    post_date: str
    reference_number: Optional[str]
    description: str
    amount: Decimal


def normalize_ocr_noise(text: str) -> str:
    """Fix common OCR confusions for digits to improve parsing reliability."""

    text = text.replace("O", "0").replace("o", "0")
    text = text.replace("S", "5")  # sometimes 5 looks like S
    text = text.replace("l", "1")  # lowercase L -> 1
    return text


def page_has_section(text: str) -> bool:
    upper_text = text.upper()
    return any(title in upper_text for title in SECTION_TITLES)


def _open_document(pdf_bytes: bytes) -> fitz.Document:
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def get_text_pages_with_fitz(pdf_bytes: bytes) -> List[tuple[int, str]]:
    """Use PyMuPDF to obtain per-page text for text-based PDFs."""

    doc = _open_document(pdf_bytes)
    pages: List[tuple[int, str]] = []
    try:
        for index, page in enumerate(doc):
            text = page.get_text("text") or ""
            pages.append((index + 1, text))
    finally:
        doc.close()
    return pages


def ocr_pages_with_pytesseract(pdf_bytes: bytes, zoom: float = 2.0) -> List[tuple[int, str]]:
    """OCR fallback for scanned/image-based PDFs."""

    try:
        import pytesseract  # type: ignore
    except Exception:
        return []

    doc = _open_document(pdf_bytes)
    pages: List[tuple[int, str]] = []
    try:
        for index, page in enumerate(doc):
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            image_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(image_bytes))
            text = pytesseract.image_to_string(image) or ""
            pages.append((index + 1, text))
    finally:
        doc.close()
    return pages


def stitch_rows(raw_lines: Iterable[str]) -> List[str]:
    """Build complete transaction rows by merging wrapped/continuation lines."""

    rows: List[str] = []
    buffer: List[str] = []
    for raw_line in raw_lines:
        line = normalize_ocr_noise(" ".join(raw_line.split()))
        if not line:
            continue

        if re.match(r"^\d{2}/\d{2}\s+\d{2}/\d{2}\b", line):
            if buffer:
                merged = " ".join(buffer)
                if ROW_RE.match(merged):
                    rows.append(merged)
                buffer = []
            buffer = [line]
        else:
            if buffer:
                buffer.append(line)
            else:
                continue

        merged = " ".join(buffer)
        if MONEY_TAIL_RE.search(merged) and ROW_RE.match(merged):
            rows.append(merged)
            buffer = []

    if buffer:
        merged = " ".join(buffer)
        if ROW_RE.match(merged):
            rows.append(merged)
    return rows


def split_body_for_ref_and_desc(body: str) -> tuple[Optional[str], Optional[str], str]:
    """Separate the reference number and description from the row body."""

    tokens = body.split()
    reference = None
    for index, token in enumerate(tokens):
        digits = re.sub(r"\D+", "", token)
        if len(digits) >= 10:
            reference = digits
            description = " ".join(tokens[index + 1 :]).strip()
            return None, reference, description
    return None, None, body.strip()


def clean_money_to_decimal(value: str) -> Decimal:
    return Decimal(value.replace("$", "").replace(",", "").strip())


def extract_transactions(pdf_bytes: bytes) -> List[ExtractedTransaction]:
    """Extract transactions from the Cardholder Account Summary tables."""

    text_pages = get_text_pages_with_fitz(pdf_bytes)
    raw_lines: List[str] = []
    for _, text in text_pages:
        if page_has_section(text):
            for raw_line in text.splitlines():
                raw_line = raw_line.rstrip()
                if raw_line:
                    raw_lines.append(raw_line)

    if not raw_lines:
        for _, text in ocr_pages_with_pytesseract(pdf_bytes, zoom=2.0):
            if page_has_section(text):
                for raw_line in text.splitlines():
                    raw_line = raw_line.rstrip()
                    if raw_line:
                        raw_lines.append(raw_line)

    if not raw_lines:
        return []

    candidate_rows = stitch_rows(raw_lines)
    results: List[ExtractedTransaction] = []
    for row in candidate_rows:
        match = ROW_RE.match(row)
        if not match:
            continue
        trans_date = match.group("trans")
        post_date = match.group("post")
        body = match.group("body")

        amounts = MONEY_TAIL_RE.findall(row)
        if not amounts:
            continue
        amount_str = amounts[-1]

        _, reference, description = split_body_for_ref_and_desc(body)

        amount = clean_money_to_decimal(amount_str)
        if any(keyword in description.upper() for keyword in ("PAYMENT", "CREDIT", "REFUND")) and amount > 0:
            amount = -amount

        results.append(
            ExtractedTransaction(
                trans_date=trans_date,
                post_date=post_date,
                reference_number=reference,
                description=description,
                amount=amount,
            )
        )
    return results


__all__ = ["ExtractedTransaction", "extract_transactions"]

