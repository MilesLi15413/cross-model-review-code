"""Structured parsing for writer/reviewer outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_SOLUTION_RE = re.compile(r"<solution>(.*?)</solution>", re.DOTALL | re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
_CONFIDENCE_SENTENCE_RE = re.compile(
    r"([^.!\n]*\bconfidence\b[^.!\n]*[.!\n]?)",
    re.IGNORECASE,
)
_CONFIDENCE_LABEL_RE = re.compile(r"\b(high|medium|low)\b", re.IGNORECASE)
_WRAPPED_CODE_BLOCK_RE = re.compile(r"^\s*```(?:\w+)?\s*\n(.*?)\n?```\s*$", re.DOTALL)


@dataclass
class ParseResult:
    artifact: str
    parse_method: str
    has_solution_tag: bool
    parse_failed: bool
    confidence_note: Optional[str] = None
    confidence_label: Optional[str] = None


def _extract_confidence_note(text: str) -> tuple[Optional[str], Optional[str]]:
    redacted = _SOLUTION_RE.sub(" ", text)
    match = _CONFIDENCE_SENTENCE_RE.search(redacted)
    if not match:
        return None, None

    note = " ".join(match.group(1).split()).strip()
    label_match = _CONFIDENCE_LABEL_RE.search(note)
    label = label_match.group(1).lower() if label_match else None
    return note or None, label


def normalize_code_artifact(text: str) -> str:
    """Remove a single Markdown code fence wrapped around an extracted artifact."""

    stripped = text.strip()
    wrapped = _WRAPPED_CODE_BLOCK_RE.match(stripped)
    if wrapped:
        return wrapped.group(1).strip()
    return stripped


def parse_model_response(text: str) -> ParseResult:
    """Parse the solution artifact and any confidence note from a model reply."""

    stripped = text.strip()
    if not stripped:
        return ParseResult(
            artifact="",
            parse_method="empty",
            has_solution_tag=False,
            parse_failed=True,
        )

    confidence_note, confidence_label = _extract_confidence_note(text)

    tag_match = _SOLUTION_RE.search(text)
    if tag_match:
        return ParseResult(
            artifact=normalize_code_artifact(tag_match.group(1)),
            parse_method="tag",
            has_solution_tag=True,
            parse_failed=False,
            confidence_note=confidence_note,
            confidence_label=confidence_label,
        )

    code_match = _CODE_BLOCK_RE.search(text)
    if code_match:
        return ParseResult(
            artifact=code_match.group(1).strip(),
            parse_method="codeblock",
            has_solution_tag=False,
            parse_failed=True,
            confidence_note=confidence_note,
            confidence_label=confidence_label,
        )

    return ParseResult(
        artifact=stripped,
        parse_method="full",
        has_solution_tag=False,
        parse_failed=True,
        confidence_note=confidence_note,
        confidence_label=confidence_label,
    )
