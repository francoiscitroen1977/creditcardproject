from __future__ import annotations

import inspect
from io import BytesIO
from pathlib import Path
from typing import List, Optional

from nicegui import ui
from nicegui.events import UploadEventArguments

from app.models.transaction import Transaction
from app.services.extraction_service import ExtractionService


class UploadPage:
    """NiceGUI page that handles PDF uploads and displays results."""

    def __init__(self) -> None:
        self.service = ExtractionService()
        self.transactions: List[Transaction] = []
        self.openai_status = ui.label().props("class=mb-2")
        self.result_message = ui.label().props("class=mb-2")
        columns = [
            {
                "name": "trans_date",
                "label": "Trans Date",
                "field": "trans_date",
            },
            {
                "name": "post_date",
                "label": "Post Date",
                "field": "post_date",
            },
            {
                "name": "reference_number",
                "label": "Reference Number",
                "field": "reference_number",
            },
            {
                "name": "description",
                "label": "Description",
                "field": "description",
            },
            {
                "name": "amount",
                "label": "Amount",
                "field": "amount",
            },
        ]

        self.table = ui.table(
            columns=columns,
            rows=[],
            row_key="reference_number",
        ).classes("w-full")

        with ui.row():
            ui.button("Download JSON", on_click=self.download_json).props("color=primary")
            ui.button("Download CSV", on_click=self.download_csv)

        ui.upload(on_upload=self.handle_upload, label="Upload PDF Statement", auto_upload=True)

        self._update_openai_status()

    async def handle_upload(self, e: UploadEventArguments) -> None:
        pdf_bytes = await self._read_event_bytes(e)
        if pdf_bytes is None:  # pragma: no cover - defensive
            raise AttributeError("Upload event does not provide file content")

        try:
            result = self.service.extract(pdf_bytes)
        except Exception as exc:  # pragma: no cover - UI error path
            self.transactions = []
            self.table.update_rows([])
            self.result_message.set_text(f"Extraction failed: {exc}")
            self.result_message.props("color=negative")
            return

        self.transactions = result.transactions
        self.table.update_rows([t.model_dump() for t in self.transactions])
        parser_label = result.parser_name.capitalize()
        message = f"{len(self.transactions)} transactions extracted using {parser_label} parser."
        if result.errors:
            message += f" Fallback messages: {'; '.join(result.errors)}"
        self.result_message.set_text(message)
        self.result_message.props("color=positive")

    def download_json(self) -> None:
        if not self.transactions:
            ui.notify("No transactions to export", color="warning")
            return
        content = self.service.to_json(self.transactions)
        ui.download(content.encode("utf-8"), filename="transactions.json")

    def download_csv(self) -> None:
        if not self.transactions:
            ui.notify("No transactions to export", color="warning")
            return
        content = self.service.to_csv(self.transactions)
        ui.download(content.encode("utf-8"), filename="transactions.csv")

    async def _read_event_bytes(self, e: UploadEventArguments) -> Optional[bytes]:
        content = getattr(e, "content", None)
        if content is not None:
            if hasattr(content, "read"):
                return await self._read_stream(content)
            if isinstance(content, (bytes, bytearray)):
                return bytes(content)
            return bytes(content)

        file_obj = getattr(e, "file", None)
        if file_obj is not None and hasattr(file_obj, "read"):
            return await self._read_stream(file_obj)

        files = getattr(e, "files", None)
        if files:
            first = files[0]
            if hasattr(first, "read"):
                return await self._read_stream(first)

        path = getattr(e, "path", None)
        if path:
            try:
                return Path(path).read_bytes()
            except Exception:  # pragma: no cover - defensive
                pass

        if hasattr(e, "read"):
            data = await e.read()
            return data if isinstance(data, (bytes, bytearray)) else bytes(data)

        if hasattr(e, "save"):
            buffer = BytesIO()
            try:
                await e.save(buffer)
                return buffer.getvalue()
            except Exception:  # pragma: no cover - defensive
                return None

        return None

    def _update_openai_status(self) -> None:
        ok, message = self.service.openai_status()
        self.openai_status.set_text(message)
        color = "positive" if ok else "negative"
        self.openai_status.props(f"color={color}")

    async def _read_stream(self, reader) -> Optional[bytes]:
        data = reader.read()
        if inspect.isawaitable(data):
            data = await data
        if data is None:
            return None
        try:
            reader.seek(0)
        except Exception:  # pragma: no cover - in-memory uploads
            pass
        return data if isinstance(data, (bytes, bytearray)) else bytes(data)


def create_page() -> None:
    ui.page("/")(lambda: UploadPage())
