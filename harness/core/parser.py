"""Structured parsing for writer/reviewer outputs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional


_SOLUTION_RE = re.compile(r"<solution>(.*?)</solution>", re.DOTALL | re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)
_CONFIDENCE_SENTENCE_RE = re.compile(
    r"([^.!\n]*\bconfidence\b[^.!\n]*[.!\n]?)",
    re.IGNORECASE,
)
_CONFIDENCE_LABEL_RE = re.compile(r"\b(high|medium|low)\b", re.IGNORECASE)
_WRAPPED_CODE_BLOCK_RE = re.compile(r"^\s*```(?:\w+)?\s*\n(.*?)\n?```\s*$", re.DOTALL)
_ISSUES_RE = re.compile(r"<issues>(.*?)</issues>", re.DOTALL | re.IGNORECASE)
_HELP_REQUEST_RE = re.compile(
    r"<help_request\b([^>]*)>(.*?)</help_request>",
    re.DOTALL | re.IGNORECASE,
)
_HELP_TYPE_RE = re.compile(r"""type\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_HELP_OPEN_RE = re.compile(r"<help_request\b", re.IGNORECASE)

HELP_REQUEST_TYPES = (
    "unclear_instructions",
    "missing_information",
    "wants_execution",
    "clarification",
    "uncertainty",
    "other",
)

UNTAGGED_HELP_PATTERNS = [
    r"\b(?:could|can|would) you (?:please )?(?:clarify|confirm|provide|share|explain)\b",
    r"\bplease (?:clarify|confirm|provide)\b",
    r"\bneed(?:s)? (?:more |further |some )?(?:clarification|information|details)\b",
    r"\bmissing (?:information|details)\b",
    r"\bi (?:can't|cannot|can not|am unable to|am not able to|'m unable to|'m not able to) "
    r"(?:run|execute|test|verify)\b",
    r"\bi (?:would like|want|need) to (?:run|execute|test)\b",
]
_UNTAGGED_HELP_RES = [re.compile(pattern, re.IGNORECASE) for pattern in UNTAGGED_HELP_PATTERNS]


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


def parse_issues(text: str) -> Dict[str, object]:
    """Read the reviewer's tagged issue list; `count` is None when the tag is missing."""

    match = _ISSUES_RE.search(_SOLUTION_RE.sub(" ", text))
    if not match:
        return {"status": "missing", "count": None, "issues": []}

    body = match.group(1).strip()
    if body.lower() in {"", "none", "none."}:
        return {"status": "none_reported", "count": 0, "issues": []}

    lines = [line.strip() for line in body.splitlines() if line.strip()]
    bullets = [line[1:].strip() for line in lines if line.startswith("-")]
    issues = bullets or lines
    return {"status": "tagged", "count": len(issues), "issues": issues}


def parse_help_requests(text: str, parsed: ParseResult) -> Dict[str, object]:
    """Count tagged and untagged help requests, and flag replies that contain no code."""

    requests: List[Dict[str, str]] = []
    for attributes, body in _HELP_REQUEST_RE.findall(text):
        type_match = _HELP_TYPE_RE.search(attributes)
        raw_type = type_match.group(1).strip() if type_match else ""
        requests.append(
            {
                "type": raw_type if raw_type in HELP_REQUEST_TYPES else "other",
                "raw_type": raw_type,
                "text": " ".join(body.split()),
            }
        )

    prose = _HELP_REQUEST_RE.sub(" ", _SOLUTION_RE.sub(" ", text))
    untagged: List[str] = []
    for pattern in _UNTAGGED_HELP_RES:
        for match in pattern.finditer(prose):
            untagged.append(match.group(0))

    return {
        "tagged_count": len(requests),
        "tagged_requests": requests,
        "malformed_tags": len(_HELP_OPEN_RE.findall(text)) - len(requests),
        "untagged_count": len(untagged),
        "untagged_matches": untagged,
        "no_code": parsed.parse_method in {"empty", "full"},
    }
