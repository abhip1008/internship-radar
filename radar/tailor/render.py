"""Render selected bullets to .tex and, if a LaTeX engine is present, .pdf
(spec §10.2 render()).

Uses tectonic or pdflatex when available; always writes the .tex so the pipeline
is useful even without a LaTeX toolchain installed.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..config import ROOT, files_path
from .bank import load_bank

_ENV = Environment(
    loader=FileSystemLoader(str(ROOT / "templates")),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

# Characters LaTeX treats specially.
_LATEX_ESCAPES = {
    "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
}


def latex_escape(text: str) -> str:
    return "".join(_LATEX_ESCAPES.get(c, c) for c in text)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40]


def _fmt_grad(value: Any) -> str:
    try:
        dt = datetime.strptime(str(value), "%Y-%m")
        return dt.strftime("%b %Y")
    except (ValueError, TypeError):
        return str(value)


def build_context(company: str, role: str, selection: dict[str, Any], rephrased: dict[str, str]) -> dict[str, Any]:
    bank = load_bank()
    ident = bank["identity"]
    edu = ident.get("education", {})

    by_id = {it["id"]: it for section in ("experiences", "projects") for it in bank.get(section, [])}

    def render_group(section_key: str) -> list[dict[str, Any]]:
        items = []
        for sid, bullets in selection.get(section_key, {}).items():
            src = by_id.get(sid, {})
            entry: dict[str, Any] = {
                "org": latex_escape(src.get("org", "")),
                "name": latex_escape(src.get("name", "")),
                "role": latex_escape(src.get("role", "")),
                "location": latex_escape(src.get("location", "")),
                "dates": latex_escape(_dates(src)),
                "stack": [latex_escape(s) for s in src.get("stack", [])],
                "award": latex_escape(src.get("award", "")),
                "bullets": [latex_escape(rephrased.get(b.id, b.text)) for b in bullets],
            }
            items.append(entry)
        return items

    return {
        "company": latex_escape(company),
        "role": latex_escape(role),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "identity": ident,
        "education": {
            "school": latex_escape(edu.get("school", "")),
            "degree": latex_escape(edu.get("degree", "")),
            "grad_display": _fmt_grad(edu.get("grad")),
            "coursework": [latex_escape(c) for c in edu.get("coursework", [])],
        },
        "experiences": render_group("experiences"),
        "projects": render_group("projects"),
        "skills": {k: [latex_escape(s) for s in v] for k, v in selection.get("skills_order", {}).items()},
    }


def _dates(src: dict[str, Any]) -> str:
    start, end = src.get("start"), src.get("end")
    if not start:
        return ""
    end = "Present" if end == "present" else (end or "")
    return f"{start} – {end}" if end else str(start)


def render(company: str, role: str, selection: dict[str, Any], rephrased: dict[str, str]) -> dict[str, Any]:
    ctx = build_context(company, role, selection, rephrased)
    tex = _ENV.get_template("resume.tex.j2").render(**ctx)

    out_dir = files_path("resumes")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{_slug(company)}_{_slug(role)}_{datetime.now(timezone.utc):%Y%m%d}"
    tex_path = out_dir / f"{stem}.tex"
    tex_path.write_text(tex, encoding="utf-8")

    pdf_path = _compile_pdf(tex_path)
    return {"tex_path": str(tex_path), "pdf_path": str(pdf_path) if pdf_path else None, "tex": tex}


def _compile_pdf(tex_path: Path) -> Path | None:
    engine = shutil.which("tectonic") or shutil.which("pdflatex")
    if not engine:
        return None
    try:
        if "tectonic" in engine:
            subprocess.run([engine, str(tex_path)], cwd=tex_path.parent, capture_output=True, timeout=120, check=True)
        else:
            subprocess.run(
                [engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
                cwd=tex_path.parent, capture_output=True, timeout=120, check=True,
            )
    except (subprocess.SubprocessError, OSError):
        return None
    pdf = tex_path.with_suffix(".pdf")
    return pdf if pdf.exists() else None
