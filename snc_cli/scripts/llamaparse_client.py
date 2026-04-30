#!/usr/bin/env python3
"""LlamaParse API client.

Uploads a PDF, polls for completion, and returns the parsed markdown.

Usage:
    from snc_cli.scripts.llamaparse_client import parse_pdf

    md_text = parse_pdf(Path("references/APR 17TH.pdf"), api_key="...")
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

LLAMAPARSE_BASE = "https://api.cloud.llamaindex.ai/api/v1/parsing"
POLL_INTERVAL_SECONDS = 3
POLL_TIMEOUT_SECONDS = 300


class LlamaParseError(RuntimeError):
    pass


def get_api_key(explicit: Optional[str] = None) -> Optional[str]:
    if explicit:
        return explicit
    return os.environ.get("LLAMAPARSE_API_KEY", "").strip() or None


def _headers(api_key: str) -> dict:
    return {"Authorization": f"Bearer {api_key}"}


def upload_pdf(pdf_path: Path, api_key: str) -> str:
    """Upload PDF, return job_id."""
    url = f"{LLAMAPARSE_BASE}/upload"
    with open(pdf_path, "rb") as fh:
        files = {"file": (pdf_path.name, fh, "application/pdf")}
        resp = requests.post(url, headers=_headers(api_key), files=files, timeout=60)
    if resp.status_code >= 400:
        raise LlamaParseError(f"Upload failed ({resp.status_code}): {resp.text[:300]}")
    body = resp.json()
    job_id = body.get("id") or body.get("job_id")
    if not job_id:
        raise LlamaParseError(f"No job id in response: {body}")
    return job_id


def poll_status(job_id: str, api_key: str,
                interval: int = POLL_INTERVAL_SECONDS,
                timeout: int = POLL_TIMEOUT_SECONDS) -> None:
    """Poll until status is SUCCESS (or raise on ERROR/timeout)."""
    url = f"{LLAMAPARSE_BASE}/job/{job_id}"
    deadline = time.time() + timeout
    last_status = None
    while time.time() < deadline:
        resp = requests.get(url, headers=_headers(api_key), timeout=30)
        if resp.status_code >= 400:
            raise LlamaParseError(f"Status check failed ({resp.status_code}): {resp.text[:300]}")
        status = (resp.json().get("status") or "").upper()
        if status != last_status:
            print(f"  LlamaParse status: {status}", file=sys.stderr)
            last_status = status
        if status in ("SUCCESS", "COMPLETED", "READY"):
            return
        if status in ("ERROR", "FAILED", "CANCELLED"):
            raise LlamaParseError(f"Job {job_id} ended with status {status}")
        time.sleep(interval)
    raise LlamaParseError(f"Job {job_id} did not complete within {timeout}s")


def fetch_markdown(job_id: str, api_key: str) -> str:
    url = f"{LLAMAPARSE_BASE}/job/{job_id}/result/markdown"
    resp = requests.get(url, headers=_headers(api_key), timeout=60)
    if resp.status_code >= 400:
        raise LlamaParseError(f"Result fetch failed ({resp.status_code}): {resp.text[:300]}")
    body = resp.json()
    md = body.get("markdown")
    if md is None:
        raise LlamaParseError(f"No markdown field in result: {list(body.keys())}")
    return md


def parse_pdf(pdf_path: Path, api_key: Optional[str] = None) -> str:
    """End-to-end: upload PDF, poll, return markdown text."""
    key = get_api_key(api_key)
    if not key:
        raise LlamaParseError("LLAMAPARSE_API_KEY not set")
    if not pdf_path.exists():
        raise LlamaParseError(f"PDF not found: {pdf_path}")

    print(f"Uploading {pdf_path.name} to LlamaParse...", file=sys.stderr)
    job_id = upload_pdf(pdf_path, key)
    print(f"  job_id: {job_id}", file=sys.stderr)
    poll_status(job_id, key)
    return fetch_markdown(job_id, key)
