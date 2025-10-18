# Credit Card Statement Extractor (NiceGUI + OpenAI)

Upload a PDF credit card statement and extract **paid transactions** into JSON/CSV.

**Captured columns:** Trans Date, Post Date, Reference Number, Description, Amount.  
Rows **without Amount** are ignored.

## Why this repo?
- Clean separation of UI, services, parsers, and models
- **OpenAI-based** parsing (no Tesseract). API key is read from `.env`
- Optional heuristic fallback for local parsing without a key

## Quickstart
```bash
# 1) Create your venv and install deps
pip install -e .

# 2) Add your API key
cp .env.example .env
# create .env with your OPENAI_API_KEY = 1234 and OPENAI_MODEL

# 3) Run
python -m app.main  # or: uvicorn app.main:fastapi_app --reload
```

Then open http://localhost:8080

## Structure
- `app/pages` NiceGUI pages
- `app/services` orchestration (validation, exports)
- `app/parsers` extraction strategies (OpenAI + heuristic fallback)
- `app/models` Pydantic schemas
- `app/utils` PDF helpers
- `data/outputs` exports (gitignored)

## Notes
- Put test PDFs in `data/samples/` (avoid committing sensitive files).
- Extraction prefers OpenAI when `OPENAI_API_KEY` is present; otherwise uses heuristic fallback.
