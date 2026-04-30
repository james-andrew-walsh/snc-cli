#!/usr/bin/env python3
"""Daily Dispatch PDF Ingestion (CR-B01).

Wraps the full daily-dispatch pipeline behind a single command:
  - Resolve the dispatch PDF for the given date (locally or via Gmail)
  - Convert PDF -> markdown via LlamaParse (or Gemini fallback)
  - Parse the markdown into structured JSON
  - Write references/dispatch-YYYY-MM-DD.json

Usage:
    python3 snc_cli/scripts/ingest_dispatch.py 2026-04-17
    python3 snc_cli/scripts/ingest_dispatch.py --date 2026-04-17 --dry-run
    python3 snc_cli/scripts/ingest_dispatch.py 2026-04-17 --fetch-email
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date as date_cls, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

REFERENCES_DIR = Path(
    "/Users/james/.openclaw/workspace/projects/snc/equipment-tracking/references"
)

MONTH_ABBR = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}

DISPATCH_SENDERS = ["tduran@sierra-nv.com", "dispatch@sierra-nv.com"]


# ---------------------------------------------------------------------------
# Date / filename helpers
# ---------------------------------------------------------------------------


def day_suffix(day: int) -> str:
    if day in (11, 12, 13):
        return "TH"
    last = day % 10
    if last == 1:
        return "ST"
    if last == 2:
        return "ND"
    if last == 3:
        return "RD"
    return "TH"


def snc_pdf_name(d: date_cls) -> str:
    return f"{MONTH_ABBR[d.month]} {d.day}{day_suffix(d.day)}.pdf"


def find_pdf(d: date_cls, refs_dir: Path) -> Optional[Path]:
    """Find dispatch PDF for date, case-insensitively."""
    target = snc_pdf_name(d)
    target_lower = target.lower()
    target_dashed = target_lower.replace(" ", "-")
    if not refs_dir.exists():
        return None
    for p in refs_dir.iterdir():
        if not p.is_file():
            continue
        name_lower = p.name.lower()
        if name_lower == target_lower or name_lower == target_dashed:
            return p
    return None


def parse_input_date(value: str) -> date_cls:
    return datetime.strptime(value, "%Y-%m-%d").date()


# ---------------------------------------------------------------------------
# LlamaParse markdown -> JSON  (copied from extract_dispatch_llamaparse.py)
# ---------------------------------------------------------------------------


def clean(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.strip().replace("\n", " ").replace("  ", " ").strip()
    return text


def parse_resource_type(description: str) -> str:
    d = description.upper()
    if d.startswith("SUB,"):
        return "subcontractor"
    if re.search(r"^[A-Z]+,\s+[A-Z]", description):
        return "personnel"
    if description.startswith("AT-"):
        return "attachment"
    return "equipment"


def parse_role(description: str) -> Optional[str]:
    m = re.search(
        r"-\s+(FOREMAN|SUPT|OPERATOR|LAB-4MAN|OE-4MAN|LABORER|CARPENTER)$",
        description, re.IGNORECASE)
    return m.group(1).upper() if m else None


def clean_resource_id(rid: str) -> str:
    return re.sub(r"^\|__+", "", rid).strip()


def parse_status(s: str) -> Optional[str]:
    s = s.strip().upper()
    return s if s in ("STAND", "AVAIL", "DOWN") else None


def parse_llamaparse(md_text: str) -> Dict[str, Any]:
    raw = md_text

    output: Dict[str, Any] = {
        "metadata": {
            "company": "Sierra Nevada Construction, Inc.",
            "reportDate": None,
            "printedDate": None,
            "reportType": "Daily Schedule Report",
        },
        "jobs": [],
        "equipmentStatus": {"repairs": [], "yard": []},
    }

    dm = re.search(r"#\s+(\d{2}/\d{2}/\d{4})", raw)
    if dm:
        mm, dd, yyyy = dm.group(1).split("/")
        output["metadata"]["reportDate"] = f"{yyyy}-{mm}-{dd}"
    pm = re.search(r"Printed on:\s+(\d{2}/\d{2}/\d{4})", raw)
    if pm:
        mm, dd, yyyy = pm.group(1).split("/")
        output["metadata"]["printedDate"] = f"{yyyy}-{mm}-{dd}"

    def find_headings():
        results: List[Dict[str, Any]] = []
        pos = 0
        while True:
            idx = raw.find("#", pos)
            if idx == -1:
                break
            remaining = raw[idx:]
            if remaining.startswith("# Daily Schedule"):
                pos = idx + 1
                continue
            if remaining.startswith("# "):
                m = re.match(r"# (\d+):\s*([^\n]+)", remaining)
                if m:
                    results.append({
                        "type": "job", "level": 1,
                        "job_id": m.group(1),
                        "name": m.group(2).strip(),
                        "pos": idx,
                        "end": idx + m.end(),
                    })
                pos = idx + 1
                continue
            if remaining.startswith("## "):
                if remaining.startswith("## 2055REPAIRS"):
                    m = re.match(r"## 2055REPAIRS[^\n]*", remaining)
                    results.append({"type": "repair", "pos": idx, "end": idx + m.end()})
                elif remaining.startswith("## 2055YARD"):
                    m = re.match(r"## 2055YARD[^\n]*", remaining)
                    results.append({"type": "yard", "pos": idx, "end": idx + m.end()})
                else:
                    m = re.match(r"## (\d+):\s*([^\n]+)", remaining)
                    if m:
                        results.append({
                            "type": "job", "level": 2,
                            "job_id": m.group(1),
                            "name": m.group(2).strip(),
                            "pos": idx,
                            "end": idx + m.end(),
                        })
                pos = idx + 1
                continue
            pos = idx + 1
        return sorted(results, key=lambda x: x["pos"])

    headings = find_headings()
    current_job: Optional[Dict[str, Any]] = None
    mode = "main"

    def parse_tables_in(text: str):
        nonlocal mode
        soup = BeautifulSoup(text, "html.parser")

        if re.search(r"<td[^>]*>\s*(?:Rentals)\s*</td>", text, re.I):
            mode = "rentals"

        for table in soup.find_all("table"):
            for row in table.find_all("tr"):
                cells = row.find_all(["td", "th"])
                if len(cells) >= 1:
                    first_text = clean(cells[0].get_text())
                    if "2055YARD" in first_text.upper():
                        mode = "yard"
                        continue
                    if "2055REPAIRS" in first_text.upper():
                        mode = "repair"
                        continue
                    if re.match(r"^\d{4,}:\s", first_text):
                        continue

                if len(cells) < 2:
                    continue

                rid = clean_resource_id(clean(cells[0].get_text()))
                desc = clean(cells[1].get_text())

                if not rid or not desc:
                    continue
                if rid.upper() in ("RESOURCE", "") or desc.upper() in ("DESCRIPTION", ""):
                    continue

                start = clean(cells[2].get_text()) if len(cells) > 2 else ""
                end_t = clean(cells[3].get_text()) if len(cells) > 3 else ""
                status = parse_status(cells[4].get_text()) if len(cells) > 4 else None

                if mode == "repair":
                    output["equipmentStatus"]["repairs"].append({
                        "resourceId": rid, "description": desc, "status": "DOWN",
                    })
                elif mode == "yard":
                    output["equipmentStatus"]["yard"].append({
                        "resourceId": rid, "description": desc, "status": "AVAIL",
                    })
                elif current_job is not None:
                    current_job["resources"].append({
                        "resourceId": rid,
                        "description": desc,
                        "startTime": start,
                        "endTime": end_t,
                        "status": status,
                        "resourceType": parse_resource_type(desc),
                        "role": parse_role(desc),
                    })

    def parse_meta(text: str):
        if current_job is None:
            return
        first_table = text.find("<table>")
        if first_table >= 0:
            text = text[:first_table]
        plain = clean(text)

        m = re.search(r"Daily Location Notes[*:\s]*(.+?)(?=LOCATION:|$)",
                      plain, re.IGNORECASE | re.DOTALL)
        if m and not current_job.get("dailyNotes"):
            current_job["dailyNotes"] = m.group(1).strip()

        m = re.search(r"LOCATION:\s*(.+?)(?=CONTACT:|$)",
                      plain, re.IGNORECASE | re.DOTALL)
        if m and not current_job.get("location"):
            current_job["location"] = m.group(1).strip()

        contact_match = re.search(r"CONTACT:\s*(.+?)$",
                                  plain, re.IGNORECASE | re.MULTILINE)
        if contact_match and not current_job.get("contact"):
            contact_line = contact_match.group(1).strip()
            parts = re.split(r"\s{2,}", contact_line)
            parts = [p.strip() for p in parts if p.strip()]
            parts = [p for p in parts if not re.match(r"^\d[\d\- ]+$", p)]
            if parts:
                current_job["contact"] = " ".join(parts)

    for i, h in enumerate(headings):
        start = h["end"]
        end = headings[i + 1]["pos"] if i + 1 < len(headings) else len(raw)
        body = raw[start:end]

        if h["type"] == "repair":
            if current_job:
                if current_job["resources"]:
                    output["jobs"].append(current_job)
                current_job = None
            mode = "repair"
            parse_tables_in(body)
        elif h["type"] == "yard":
            if current_job:
                if current_job["resources"]:
                    output["jobs"].append(current_job)
                current_job = None
            mode = "yard"
            parse_tables_in(body)
        else:
            if current_job and current_job["resources"]:
                output["jobs"].append(current_job)
            current_job = {
                "jobId": h["job_id"],
                "name": clean(h["name"]),
                "location": None,
                "contact": None,
                "dailyNotes": None,
                "resources": [],
            }
            mode = "main"
            parse_meta(body)
            parse_tables_in(body)

    if current_job and current_job["resources"]:
        output["jobs"].append(current_job)

    return output


# ---------------------------------------------------------------------------
# PDF -> markdown
# ---------------------------------------------------------------------------


def pdf_to_markdown(pdf_path: Path, refs_dir: Path) -> str:
    """Produce a markdown rendering of the dispatch PDF.

    Tries LlamaParse first (if LLAMAPARSE_API_KEY set), then falls back to
    Gemini (extract_dispatch.py). Caches LlamaParse output alongside the PDF
    as APR 17TH_llamaparse.md when possible.
    """
    cached_md = refs_dir / f"{pdf_path.stem}_llamaparse.md"
    if cached_md.exists():
        print(f"  Using cached markdown: {cached_md.name}", file=sys.stderr)
        return cached_md.read_text(encoding="utf-8")

    if os.environ.get("LLAMAPARSE_API_KEY", "").strip():
        from snc_cli.scripts.llamaparse_client import parse_pdf, LlamaParseError
        try:
            md = parse_pdf(pdf_path)
            cached_md.write_text(md, encoding="utf-8")
            print(f"  Wrote: {cached_md.name}", file=sys.stderr)
            return md
        except LlamaParseError as e:
            print(f"  LlamaParse failed: {e}", file=sys.stderr)
            print("  Falling back to Gemini...", file=sys.stderr)

    return _gemini_fallback(pdf_path, refs_dir)


def _gemini_fallback(pdf_path: Path, refs_dir: Path) -> str:
    """Use Gemini (via extract_dispatch.py) and convert its JSON back into
    a minimal markdown the LlamaParse parser understands.

    The Gemini path already returns a structured JSON, so we serialize a
    simple markdown shell that parse_llamaparse() can re-extract.
    """
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError(
            "Neither LLAMAPARSE_API_KEY nor GEMINI_API_KEY is set; cannot parse PDF"
        )

    sibling_scripts = Path(
        "/Users/james/.openclaw/workspace/projects/snc/equipment-tracking/scripts"
    )
    if str(sibling_scripts) not in sys.path:
        sys.path.insert(0, str(sibling_scripts))
    import extract_dispatch  # type: ignore

    print("  Running Gemini extraction...", file=sys.stderr)
    output_path = extract_dispatch.extract_dispatch(pdf_path, output_dir=refs_dir)
    data = json.loads(Path(output_path).read_text())
    return _json_to_markdown_shell(data)


def _json_to_markdown_shell(data: Dict[str, Any]) -> str:
    """Convert Gemini JSON output to a minimal LlamaParse-style markdown
    so parse_llamaparse() can re-parse it consistently.
    """
    lines: List[str] = ["# Daily Schedule Report"]
    rd = (data.get("metadata") or {}).get("reportDate")
    if rd:
        yyyy, mm, dd = rd.split("-")
        lines.append(f"# {mm}/{dd}/{yyyy}")
    pd_ = (data.get("metadata") or {}).get("printedDate")
    if pd_:
        yyyy, mm, dd = pd_.split("-")
        lines.append(f"Printed on: {mm}/{dd}/{yyyy}")

    for job in data.get("jobs", []):
        lines.append(f"# {job.get('jobId')}: {job.get('name', '')}")
        if job.get("dailyNotes"):
            lines.append(f"Daily Location Notes: {job['dailyNotes']}")
        if job.get("location"):
            lines.append(f"LOCATION: {job['location']}")
        if job.get("contact"):
            lines.append(f"CONTACT: {job['contact']}")
        lines.append("<table>")
        lines.append("<tr><th>Resource</th><th>Description</th><th>Start</th><th>End</th><th>Status</th></tr>")
        for r in job.get("resources", []):
            lines.append(
                f"<tr><td>{r.get('resourceId','')}</td>"
                f"<td>{r.get('description','')}</td>"
                f"<td>{r.get('startTime','')}</td>"
                f"<td>{r.get('endTime','')}</td>"
                f"<td>{r.get('status') or ''}</td></tr>"
            )
        lines.append("</table>")

    repairs = (data.get("equipmentStatus") or {}).get("repairs", [])
    if repairs:
        lines.append("## 2055REPAIRS")
        lines.append("<table>")
        for r in repairs:
            lines.append(
                f"<tr><td>{r.get('resourceId','')}</td>"
                f"<td>{r.get('description','')}</td></tr>"
            )
        lines.append("</table>")

    yard = (data.get("equipmentStatus") or {}).get("yard", [])
    if yard:
        lines.append("## 2055YARD")
        lines.append("<table>")
        for r in yard:
            lines.append(
                f"<tr><td>{r.get('resourceId','')}</td>"
                f"<td>{r.get('description','')}</td></tr>"
            )
        lines.append("</table>")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Gmail (stub)
# ---------------------------------------------------------------------------


def gmail_query_for(d: date_cls) -> str:
    senders = " OR ".join(f"from:{s}" for s in DISPATCH_SENDERS)
    subj = f"{MONTH_ABBR[d.month].title()} {d.day}"
    return f"({senders}) subject:({subj}) has:attachment filename:pdf"


def fetch_dispatch_email(d: date_cls) -> None:
    print("Gmail fetch not yet implemented", file=sys.stderr)
    print(f"  Would run query: {gmail_query_for(d)}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def ingest(d: date_cls, refs_dir: Path, dry_run: bool, fetch_email: bool) -> int:
    print(f"Date: {d.isoformat()}  →  PDF: {snc_pdf_name(d)}", file=sys.stderr)

    if fetch_email:
        if dry_run:
            print(f"[dry-run] Would query Gmail: {gmail_query_for(d)}", file=sys.stderr)
        else:
            fetch_dispatch_email(d)

    pdf_path = find_pdf(d, refs_dir)
    if not pdf_path:
        print(f"Error: PDF not found in {refs_dir} (expected {snc_pdf_name(d)})",
              file=sys.stderr)
        return 1
    print(f"Found PDF: {pdf_path}", file=sys.stderr)

    output_path = refs_dir / f"dispatch-{d.isoformat()}.json"

    if dry_run:
        cached_md = refs_dir / f"{pdf_path.stem}_llamaparse.md"
        engine = "cached markdown" if cached_md.exists() else (
            "LlamaParse" if os.environ.get("LLAMAPARSE_API_KEY")
            else ("Gemini" if os.environ.get("GEMINI_API_KEY") else "NONE — no API key")
        )
        print(f"[dry-run] Would convert PDF via: {engine}", file=sys.stderr)
        print(f"[dry-run] Would write: {output_path}", file=sys.stderr)
        return 0

    md_text = pdf_to_markdown(pdf_path, refs_dir)
    data = parse_llamaparse(md_text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2))

    n_jobs = len(data["jobs"])
    n_resources = sum(len(j["resources"]) for j in data["jobs"])
    n_repairs = len(data["equipmentStatus"]["repairs"])
    n_yard = len(data["equipmentStatus"]["yard"])
    report_date = data["metadata"].get("reportDate") or "(none)"

    print(f"\nSummary:", file=sys.stderr)
    print(f"  reportDate : {report_date}", file=sys.stderr)
    print(f"  jobs       : {n_jobs}", file=sys.stderr)
    print(f"  resources  : {n_resources}", file=sys.stderr)
    print(f"  repairs    : {n_repairs}", file=sys.stderr)
    print(f"  yard       : {n_yard}", file=sys.stderr)
    print(f"  output     : {output_path}", file=sys.stderr)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest daily SNC dispatch PDF")
    parser.add_argument("date", nargs="?", help="Report date (YYYY-MM-DD)")
    parser.add_argument("--date", dest="date_flag", help="Report date (YYYY-MM-DD)")
    parser.add_argument("--references-dir", default=str(REFERENCES_DIR),
                        help="Directory containing dispatch PDFs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without writing files")
    parser.add_argument("--fetch-email", action="store_true",
                        help="Fetch the dispatch PDF from Gmail before parsing")
    args = parser.parse_args()

    raw_date = args.date or args.date_flag
    if not raw_date:
        parser.error("date is required (positional or --date)")
    try:
        d = parse_input_date(raw_date)
    except ValueError:
        print(f"Error: invalid date '{raw_date}' (expected YYYY-MM-DD)", file=sys.stderr)
        return 2

    refs_dir = Path(args.references_dir)
    return ingest(d, refs_dir, args.dry_run, args.fetch_email)


if __name__ == "__main__":
    sys.exit(main())
