# Aibys Legal Analyzer

<img width="1920" height="1080" alt="Screenshot (1093)" src="https://github.com/user-attachments/assets/238e8134-b1aa-4805-9211-655f5cb9d564" />
<img width="1920" height="1080" alt="Screenshot (1092)" src="https://github.com/user-attachments/assets/f3d1f252-156f-4676-b84b-b6aa301945f1" />


AI-powered legal document analyzer. Upload contracts, NDAs, MoUs, agreements, terms, or other legal documents, then get plain-language summaries, risky clause highlights, missing terms, questions to ask, and a document risk score.

Part of the **Aibys Document Intelligence** series.

> This tool is for informational purposes only and does not provide legal advice.

## Features

- Upload multiple PDF or TXT files in one batch
- PDF text extraction with PyMuPDF
- AI analyzes legal documents with Ollama
- Overall document summary and risk score
- Section-by-section summaries
- Risk classification: `low`, `medium`, or `high`
- Risky clause highlights with plain-language explanations
- Missing or unclear terms list
- Suggested questions to ask a lawyer or contract counterparty
- Structured result view with saved analysis history
- Raw JSON output for each record
- Persistent local storage using plain files, no SQL database
- CSV is appended to the same `data/analyses.csv` file across sessions and days
- Markdown report is generated for each analyzed document
- Download saved CSV, JSON history, or individual Markdown reports from the UI
- Runs locally with Ollama
- Responsive UI with no frontend build step

## How It Works

1. Upload one or many legal documents.
2. FastAPI validates each file and stores the original upload in `uploads/`.
3. PDF files are extracted into text with PyMuPDF.
4. Extracted text is sent to Ollama with a structured legal analysis prompt.
5. Full analysis records are saved into `data/analyses.json`.
6. Flattened summary rows are appended into `data/analyses.csv`.
7. A readable Markdown report is saved into `reports/`.
8. The UI renders the latest batch and the saved history.

## Quick Start

### Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) running locally
- An Ollama model, for example:

```bash
ollama pull gemma4:31b-cloud
```

### Install & Run

```bash
git clone https://github.com/Arlchoose-code/aibys-legal-analyzer.git
cd aibys-legal-analyzer
pip install -r requirements.txt
uvicorn main:app --reload
```

Open:

```text
http://localhost:8000
```

## Configuration

Set environment variables as needed:

```bash
OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=gemma4:31b-cloud
MAX_ANALYSIS_CHARS=30000
```

## Local Data Files

The app creates these files and folders automatically:

| Path | Purpose |
|---|---|
| `uploads/` | Original uploaded files |
| `data/analyses.json` | Full structured analysis history |
| `data/analyses.csv` | Append-only CSV export for spreadsheet use |
| `reports/` | Individual Markdown reports |

This project intentionally uses JSON, CSV, and Markdown files instead of SQL so it stays simple and portable.

## API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Web UI |
| `GET` | `/api/history` | Return saved JSON analysis records |
| `POST` | `/api/analyze` | Analyze one or more files using multipart field `files` |
| `GET` | `/api/export/json` | Download saved JSON history |
| `GET` | `/api/export/csv` | Download combined CSV report |
| `GET` | `/api/reports/{filename}` | Download an individual Markdown report |

## Tech Stack

- **Backend:** FastAPI + Python
- **AI:** Ollama
- **PDF Processing:** PyMuPDF
- **Storage:** JSON + CSV + Markdown files
- **Frontend:** Vanilla HTML/CSS/JS

## Analyzed Fields

| Category | Fields |
|---|---|
| Document Info | Document type, title, source file, created date |
| Parties | Party names and roles |
| Summary | Overall summary and section summaries |
| Risk | Risk score, risk level, risky clauses |
| Clauses | Clause text, why it matters, plain-language explanation, suggested action |
| Review Prep | Red flags, missing or unclear terms, questions to ask |

## Aibys Document Intelligence Series

| Repo | Description |
|---|---|
| Aibys Invoice Extractor | Extract invoice and receipt data |
| **Aibys Legal Analyzer** | Highlight risky clauses in contracts |
| Aibys Medical Explainer | Explain medical reports in plain language |
| Aibys Research Summarizer | Summarize academic papers |

## Author

**Syahril Haryono** - [github.com/Arlchoose-code](https://github.com/Arlchoose-code)

## License

MIT License
