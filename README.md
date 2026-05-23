# Aibys Legal Analyzer

Aibys Legal Analyzer helps you understand legal documents faster.

Upload a contract, NDA, MoU, agreement, terms, or another legal document. The app summarizes each section, highlights risky clauses, explains them in plain language, and gives an overall risk score.

Runs locally with Ollama. No cloud AI API required.

> This tool is for informational purposes only and does not provide legal advice.

## Features

- Upload one or more PDF or TXT documents
- Extract PDF text with PyMuPDF
- Analyze documents with a local Ollama model
- Save original uploads in `uploads/`
- Append full history to `data/analyses.json`
- Append flattened rows to `data/analyses.csv`
- Save per-document Markdown reports in `reports/`
- Load saved history when the app starts
- Export full JSON history, combined CSV, and individual Markdown reports
- Responsive vanilla HTML/CSS/JS interface

## Setup

1. Install Python dependencies:

```bash
pip install -r requirements.txt
```

2. Start Ollama and make sure a model is available:

```bash
ollama pull gemma4:31b-cloud
ollama serve
```

3. Run the app:

```bash
uvicorn main:app --reload
```

4. Open `http://127.0.0.1:8000`.

## Configuration

Environment variables:

- `OLLAMA_URL`: defaults to `http://localhost:11434`
- `OLLAMA_MODEL`: defaults to `gemma4:31b-cloud`
- `MAX_ANALYSIS_CHARS`: defaults to `30000`

## Storage

The app keeps local workspace files:

- `uploads/`: original uploaded documents
- `data/analyses.json`: full saved analysis history
- `data/analyses.csv`: flattened export rows
- `reports/`: readable Markdown reports

These files survive app restarts and can be used across different days.
