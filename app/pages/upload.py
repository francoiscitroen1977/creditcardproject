from __future__ import annotations

from typing import List

from nicegui import ui
from nicegui.events import UploadEventArguments

from app.models.transaction import Transaction
from app.services.extraction_service import ExtractionService


class UploadPage:
    """NiceGUI page that handles PDF uploads and displays results."""

    def __init__(self) -> None:
        self.service = ExtractionService()
        self.transactions: List[Transaction] = []
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

    async def handle_upload(self, e: UploadEventArguments) -> None:
        content = e.content
        if hasattr(content, "read"):
            pdf_bytes = content.read()
            try:
                content.seek(0)
            except Exception:  # pragma: no cover - in-memory uploads
                pass
        elif isinstance(content, (bytes, bytearray)):
            pdf_bytes = bytes(content)
        else:  # pragma: no cover - defensive
            pdf_bytes = bytes(content)

        try:
            result = self.service.extract(pdf_bytes)
        except Exception as exc:  # pragma: no cover - UI error path
            self.transactions = []
            self.table.update_rows([])
            self.result_message.set_text(f"Extraction failed: {exc}").props("color=negative")
            return

        self.transactions = result.transactions
        self.table.update_rows([t.model_dump() for t in self.transactions])
        parser_label = result.parser_name.capitalize()
        message = f"{len(self.transactions)} transactions extracted using {parser_label} parser."
        if result.errors:
            message += f" Fallback messages: {'; '.join(result.errors)}"
        self.result_message.set_text(message).props("color=positive")

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


def create_page() -> None:
    ui.page("/")(lambda: UploadPage())
