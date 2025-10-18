# Credit Card Statement Extractor (NiceGUI)

Upload a PDF credit card statement and extract **paid transactions** into JSON/CSV.

**Captured columns:** Trans Date, Post Date, Reference Number, Description, Amount.  
Rows **without Amount** are ignored.

## Why this repo?
- Clean separation of UI, services, parsers, and models
- Heuristic parser that works entirely locally (no third-party APIs)

## Quickstart
```bash
# 1) Create your venv and install deps
pip install -e .

# 2) Run
python -m app.main  # or: uvicorn app.main:fastapi_app --reload
```

Then open http://localhost:8080

## Structure
- `app/pages` NiceGUI pages
- `app/services` orchestration (validation, exports)
- `app/parsers` extraction strategies (heuristic parser)
- `app/models` Pydantic schemas
- `app/utils` PDF helpers
- `data/outputs` exports (gitignored)

## Notes
- Put test PDFs in `data/samples/` (avoid committing sensitive files).
- All parsing happens locally using heuristics, so no API keys are required.
