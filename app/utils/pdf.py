from __future__ import annotations

from io import BytesIO

from PyPDF2 import PdfReader


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract text from a PDF file represented as bytes."""

    buffer = BytesIO(pdf_bytes)
    reader = PdfReader(buffer)
    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_parts.append(page_text)
    return "\n".join(text_parts)
