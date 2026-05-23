import csv
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
DATA_DIR = BASE_DIR / "data"
REPORT_DIR = BASE_DIR / "reports"
ANALYSES_JSON = DATA_DIR / "analyses.json"
ANALYSES_CSV = DATA_DIR / "analyses.csv"

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud")
MAX_CHARS = int(os.getenv("MAX_ANALYSIS_CHARS", "30000"))

CSV_FIELDS = [
    "id",
    "created_at",
    "source_file",
    "stored_file",
    "report_file",
    "document_type",
    "title",
    "risk_score",
    "risk_level",
    "party_names",
]

app = FastAPI(title="Aibys Legal Analyzer")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def ensure_storage() -> None:
    for directory in [UPLOAD_DIR, DATA_DIR, REPORT_DIR]:
        directory.mkdir(parents=True, exist_ok=True)
    if not ANALYSES_JSON.exists():
        ANALYSES_JSON.write_text("[]\n", encoding="utf-8")
    if not ANALYSES_CSV.exists():
        with ANALYSES_CSV.open("w", newline="", encoding="utf-8") as handle:
            csv.DictWriter(handle, fieldnames=CSV_FIELDS).writeheader()


@app.on_event("startup")
def on_startup() -> None:
    ensure_storage()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/api/history")
def get_history() -> dict[str, Any]:
    return {"analyses": load_history()}


@app.post("/api/analyze")
async def analyze(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="Upload at least one PDF or TXT file.")

    ensure_storage()
    results = []
    errors = []

    for upload in files:
        try:
            record = await process_upload(upload)
            append_record(record)
            results.append(record)
        except Exception as exc:
            errors.append({"file": upload.filename, "message": str(exc)})

    if not results and errors:
        raise HTTPException(status_code=502, detail={"message": "Analysis failed.", "errors": errors})

    return {"results": results, "errors": errors, "history": load_history()}


@app.get("/api/export/json")
def export_json() -> FileResponse:
    ensure_storage()
    return FileResponse(
        ANALYSES_JSON,
        media_type="application/json",
        filename="aibys-legal-analyses.json",
    )


@app.get("/api/export/csv")
def export_csv() -> FileResponse:
    ensure_storage()
    return FileResponse(
        ANALYSES_CSV,
        media_type="text/csv",
        filename="aibys-legal-analyses.csv",
    )


@app.get("/api/reports/{filename}")
def download_report(filename: str) -> FileResponse:
    safe_name = Path(filename).name
    report_path = REPORT_DIR / safe_name
    if not report_path.exists():
        raise HTTPException(status_code=404, detail="Report not found.")
    return FileResponse(report_path, media_type="text/markdown", filename=safe_name)


async def process_upload(upload: UploadFile) -> dict[str, Any]:
    source_name = upload.filename or "document"
    suffix = Path(source_name).suffix.lower()
    if suffix not in {".pdf", ".txt"}:
        raise ValueError("Only PDF and TXT files are supported.")

    analysis_id = uuid.uuid4().hex[:12]
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    stored_name = f"{timestamp}_{slugify(Path(source_name).stem)}_{analysis_id}{suffix}"
    stored_path = UPLOAD_DIR / stored_name

    with stored_path.open("wb") as handle:
        shutil.copyfileobj(upload.file, handle)

    extracted_text = extract_text(stored_path)
    if not extracted_text.strip():
        raise ValueError("No readable text was found in this document.")

    analysis = await analyze_with_ollama(extracted_text[:MAX_CHARS])
    normalized = normalize_analysis(analysis)

    created_at = datetime.now(timezone.utc).isoformat()
    report_name = f"{timestamp}_contract-risk-report_{analysis_id}.md"
    report_path = REPORT_DIR / report_name

    record = {
        "id": analysis_id,
        "source_file": source_name,
        "stored_file": stored_name,
        "report_file": report_name,
        "created_at": created_at,
        "document_type": normalized["document_type"],
        "title": normalized["title"],
        "risk_score": normalized["risk_score"],
        "risk_level": normalized["risk_level"],
        "party_names": party_names(normalized),
        "analysis": normalized,
    }
    report_path.write_text(render_markdown_report(record), encoding="utf-8")
    return record


def extract_text(path: Path) -> str:
    if path.suffix.lower() == ".txt":
        raw = path.read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1", errors="replace")

    text_parts = []
    with fitz.open(path) as document:
        for page in document:
            text_parts.append(page.get_text("text"))
    return "\n\n".join(text_parts)


async def analyze_with_ollama(document_text: str) -> dict[str, Any]:
    prompt = build_prompt(document_text)
    content = await generate_with_ollama(prompt)
    try:
        return parse_json_response(content)
    except ValueError:
        repair_prompt = build_json_repair_prompt(content)
        repaired_content = await generate_with_ollama(repair_prompt)
        try:
            return parse_json_response(repaired_content)
        except ValueError as exc:
            raise RuntimeError(
                "Ollama returned invalid JSON after a repair attempt. Try rerunning the same file."
            ) from exc


async def generate_with_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0},
    }

    try:
        async with httpx.AsyncClient(timeout=240) as client:
            response = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
            response.raise_for_status()
    except httpx.ConnectError as exc:
        raise RuntimeError("Ollama is offline. Start Ollama and make sure the model is available.") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Ollama request failed: {exc}") from exc

    body = response.json()
    return str(body.get("response", ""))


def parse_json_response(content: str) -> dict[str, Any]:
    cleaned = strip_code_fence(content).strip()
    candidates = [cleaned]

    extracted = extract_first_json_object(cleaned)
    if extracted and extracted != cleaned:
        candidates.append(extracted)

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("No valid JSON object found in Ollama response.")


def strip_code_fence(content: str) -> str:
    fenced = re.match(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", content, re.DOTALL | re.IGNORECASE)
    return fenced.group(1) if fenced else content


def extract_first_json_object(content: str) -> str | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(content):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(content[index:])
            return content[index : index + end]
        except json.JSONDecodeError:
            continue
    return None


def build_prompt(document_text: str) -> str:
    return f"""
You are a first-pass legal document analyzer for non-lawyers.
Return one valid JSON object and nothing else. Do not wrap it in markdown.
Use double quotes for all strings. Do not add comments or trailing commas.
Match this schema:
{{
  "document_type": "contract",
  "title": "",
  "parties": [{{"name": "", "role": ""}}],
  "overall_summary": "",
  "risk_score": 0,
  "risk_level": "low",
  "sections": [
    {{
      "title": "",
      "summary": "",
      "risk_level": "low",
      "important_points": [],
      "risky_clauses": [
        {{
          "clause_text": "",
          "risk_level": "medium",
          "why_it_matters": "",
          "plain_language_explanation": "",
          "suggested_action": ""
        }}
      ]
    }}
  ],
  "red_flags": [],
  "missing_or_unclear_terms": [],
  "questions_to_ask": [],
  "not_legal_advice_disclaimer": "This tool is for informational purposes only and does not provide legal advice."
}}

Classify risk_level as low, medium, or high. Use a 0-100 risk_score.
Explain clauses in plain language. Do not provide legal advice.

Document:
{document_text}
""".strip()


def build_json_repair_prompt(content: str) -> str:
    return f"""
Convert the following model output into one valid JSON object only.
Do not add markdown, explanations, comments, or trailing commas.
Preserve the intended legal analysis fields. If a field is missing, fill it with a safe empty value.

Required top-level keys:
document_type, title, parties, overall_summary, risk_score, risk_level, sections,
red_flags, missing_or_unclear_terms, questions_to_ask, not_legal_advice_disclaimer.

Model output to repair:
{content[:20000]}
""".strip()


def normalize_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    risk_score = raw.get("risk_score", 0)
    try:
        risk_score = max(0, min(100, int(risk_score)))
    except (TypeError, ValueError):
        risk_score = 0

    risk_level = str(raw.get("risk_level") or risk_level_from_score(risk_score)).lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = risk_level_from_score(risk_score)

    return {
        "document_type": str(raw.get("document_type") or "legal document"),
        "title": str(raw.get("title") or "Untitled legal document"),
        "parties": list_or_empty(raw.get("parties")),
        "overall_summary": str(raw.get("overall_summary") or ""),
        "risk_score": risk_score,
        "risk_level": risk_level,
        "sections": list_or_empty(raw.get("sections")),
        "red_flags": list_or_empty(raw.get("red_flags")),
        "missing_or_unclear_terms": list_or_empty(raw.get("missing_or_unclear_terms")),
        "questions_to_ask": list_or_empty(raw.get("questions_to_ask")),
        "not_legal_advice_disclaimer": str(
            raw.get("not_legal_advice_disclaimer")
            or "This tool is for informational purposes only and does not provide legal advice."
        ),
    }


def append_record(record: dict[str, Any]) -> None:
    history = load_history()
    history.append(record)
    ANALYSES_JSON.write_text(json.dumps(history, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    row = {field: record.get(field, "") for field in CSV_FIELDS}
    row["party_names"] = ", ".join(record.get("party_names", []))
    with ANALYSES_CSV.open("a", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=CSV_FIELDS).writerow(row)


def load_history() -> list[dict[str, Any]]:
    ensure_storage()
    try:
        return json.loads(ANALYSES_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def render_markdown_report(record: dict[str, Any]) -> str:
    analysis = record["analysis"]
    lines = [
        f"# {analysis['title']}",
        "",
        f"- Source file: {record['source_file']}",
        f"- Created at: {record['created_at']}",
        f"- Document type: {analysis['document_type']}",
        f"- Risk score: {analysis['risk_score']}/100",
        f"- Risk level: {analysis['risk_level'].upper()}",
        "",
        "> This tool is for informational purposes only and does not provide legal advice.",
        "",
        "## Overall Summary",
        "",
        analysis.get("overall_summary", ""),
        "",
        "## Parties",
        "",
    ]

    parties = analysis.get("parties") or []
    lines.extend([f"- {p.get('name', '')} ({p.get('role', 'party')})" for p in parties if isinstance(p, dict)] or ["- Not identified"])

    lines.extend(["", "## Red Flags", ""])
    lines.extend(format_list(analysis.get("red_flags")))

    lines.extend(["", "## Missing or Unclear Terms", ""])
    lines.extend(format_list(analysis.get("missing_or_unclear_terms")))

    lines.extend(["", "## Questions to Ask", ""])
    lines.extend(format_list(analysis.get("questions_to_ask")))

    lines.extend(["", "## Section Analysis", ""])
    for section in analysis.get("sections") or []:
        if not isinstance(section, dict):
            continue
        lines.extend(
            [
                f"### {section.get('title', 'Untitled section')}",
                "",
                f"Risk: {str(section.get('risk_level', 'low')).upper()}",
                "",
                str(section.get("summary", "")),
                "",
                "Important points:",
            ]
        )
        lines.extend(format_list(section.get("important_points")))
        risky_clauses = section.get("risky_clauses") or []
        if risky_clauses:
            lines.extend(["", "Risky clauses:"])
            for clause in risky_clauses:
                if isinstance(clause, dict):
                    lines.extend(
                        [
                            f"- {clause.get('clause_text', '')}",
                            f"  - Risk: {clause.get('risk_level', '')}",
                            f"  - Why it matters: {clause.get('why_it_matters', '')}",
                            f"  - Plain-language explanation: {clause.get('plain_language_explanation', '')}",
                            f"  - Suggested action: {clause.get('suggested_action', '')}",
                        ]
                    )
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def format_list(items: Any) -> list[str]:
    values = list_or_empty(items)
    if not values:
        return ["- None identified"]
    return [f"- {item}" if not isinstance(item, dict) else f"- {json.dumps(item, ensure_ascii=True)}" for item in values]


def party_names(analysis: dict[str, Any]) -> list[str]:
    names = []
    for party in analysis.get("parties") or []:
        if isinstance(party, dict) and party.get("name"):
            names.append(str(party["name"]))
    return names


def list_or_empty(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def risk_level_from_score(score: int) -> str:
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return cleaned[:60] or "document"
