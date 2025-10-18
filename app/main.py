from __future__ import annotations

from dotenv import load_dotenv
from nicegui import app, ui

from app.pages.upload import create_page


def configure_ui() -> None:
    if getattr(configure_ui, "_configured", False):
        return
    create_page()
    configure_ui._configured = True  # type: ignore[attr-defined]


def run() -> None:
    load_dotenv()
    configure_ui()
    ui.run(reload=False, port=8080)


load_dotenv()
configure_ui()
fastapi_app = app


if __name__ == "__main__":
    run()
