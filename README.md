# GhostWriter

AI ghostwriting assistant that rewrites documents in a specific author's voice. It rewrites individual sentences with a similarity gate so the output keeps your meaning but avoids verbatim AI-sounding text.

## Features

- Rewrites pasted text or uploaded files (`.docx`, `.pdf`) in the author's voice
- Sentence-level rewriting with a similarity check: sentences too close to the original are regenerated
- Keeps headings, paragraphs and document structure intact for `.docx` output
- Rejoins sentences that were split across paragraphs (e.g. a continuation paragraph starting lowercase after one that doesn't end with punctuation)
- RAG retrieval over an embedded document library (ChromaDB + sentence-transformers)
- Model rotation with retry/fallback across Gemini and Groq
- Automatic fallback to Groq when the Gemini quota is exhausted (if `GROQ_API_KEY` is set)
- FastAPI service with auto-generated Swagger docs at `/docs`

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file:

```
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
GHOSTWRITER_CHUNK_SIZE=40
```

The style prompt lives in `data/style_prompt.txt` and the RAG vector DB in `data/vector_db/`. If the DB is missing, build it from `data/dataset/`:

```bash
python scripts/embed.py
```

## Run

```bash
uvicorn api.main:app --reload --port 8000
```

- Web UI: http://localhost:8000
- Swagger docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## API

### `POST /rewrite`

Accepts `multipart/form-data`. Provide exactly one of `draft` or `file`.

| Field | Type | Required | Description |
|---|---|---|---|
| `draft` | string | if no `file` | Document text to rewrite |
| `file` | file | if no `draft` | A `.docx` or `.pdf` file to rewrite |
| `system_prompt_override` | string | no | Replaces the default author-style prompt |

- **`draft` input** → JSON `{ "rewritten": "..." }`
- **`file` input** → downloadable `.docx` (attachment named `<original>_rewritten.docx`)

Examples:

```bash
curl -X POST http://localhost:8000/rewrite \
  -F 'draft=The quick brown fox jumps over the lazy dog.'

curl -X POST http://localhost:8000/rewrite \
  -F 'file=@draft.docx'
```

Errors return JSON with a `detail` field: `400` for missing/empty input or unsupported file types, `500` if the rewrite pipeline fails.

## Configuration (environment variables)

| Variable | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | — | Gemini API key |
| `GROQ_API_KEY` | — | Groq API key (fallback provider) |
| `GHOSTWRITER_PROVIDER` | `gemini` | Primary LLM provider |
| `GEMINI_MODEL` | `gemini-3.6-flash` | Gemini model name |
| `GHOSTWRITER_CHUNK_SIZE` | `8` | Sentences per rewrite request |
| `GHOSTWRITER_MAX_WORKERS` | `4` | Chunks rewritten in parallel (one LLM call per worker) |
| `GHOSTWRITER_KEEP_RATIO` | `0.4` | Fraction of sentences kept verbatim |
| `GHOSTWRITER_TEMPERATURE` | `0.8` | Sampling temperature |

## Performance / timeouts

Chunks are rewritten in parallel (`GHOSTWRITER_MAX_WORKERS`, default 4), so wall-clock time is roughly `chunks / workers × per-call latency` rather than `chunks × per-call latency`. A single synchronous request still must finish inside your proxy's timeout (e.g. Cloudflare's ~100s): for long documents set `GHOSTWRITER_CHUNK_SIZE` (e.g. `40`) and `GHOSTWRITER_MAX_WORKERS` (e.g. `4`) so the request completes well under that limit.

## Project layout

```
api/               FastAPI app
ghostwriter/       core rewrite engine (config, llm, rag, parse, style)
scripts/           data pipeline: extract, split, clean, embed
data/              style prompt, vector DB, inputs and rewritten output
```

## Deployment

Containerized deployment (Docker / Railway) docs coming soon. Note `data/vector_db` and `data/dataset/` are gitignored — rebuild or restore them on the server.
