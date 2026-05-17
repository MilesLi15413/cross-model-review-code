"""Environment preflight checks for CLI/model combinations."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List

from harness.core.cli_runner import CLIRunner, cli_model_key


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PreflightCheck:
    cli: str
    model: str
    effort: str
    cli_version: str
    ok: bool
    response_text: str
    checked_at: str


def build_preflight_runners(conditions: Iterable[dict], paused_sentinel_path: str = "") -> List[CLIRunner]:
    """Deduplicate runner definitions across all conditions."""

    runners: Dict[str, CLIRunner] = {}
    for condition in conditions:
        writer = condition["writer"]
        key = cli_model_key(writer["cli"], writer["model"], writer.get("effort"))
        runners.setdefault(
            key,
            CLIRunner(
                cli=writer["cli"],
                model=writer["model"],
                effort=writer.get("effort"),
                timeout_s=writer.get("timeout_s", 300),
                paused_sentinel_path=paused_sentinel_path or None,
            ),
        )

        reviewer = condition.get("reviewer")
        if reviewer:
            key = cli_model_key(reviewer["cli"], reviewer["model"], reviewer.get("effort"))
            runners.setdefault(
                key,
                CLIRunner(
                    cli=reviewer["cli"],
                    model=reviewer["model"],
                    effort=reviewer.get("effort"),
                    timeout_s=reviewer.get("timeout_s", 300),
                    paused_sentinel_path=paused_sentinel_path or None,
                ),
            )

    return list(runners.values())


def run_preflight(runners: Iterable[CLIRunner], output_path: str) -> Dict[str, object]:
    """Run a tiny live smoke test against each unique CLI/model pair."""

    checks: List[PreflightCheck] = []
    cli_versions: Dict[str, str] = {}
    prompt = "Reply exactly with OK"

    for runner in runners:
        result = runner.run(prompt, task_id="preflight", condition_id="preflight", turn="preflight")
        ok = result.response_text.strip() == "OK"
        if not ok:
            raise RuntimeError(
                f"Preflight response for {runner.cli}/{runner.model!s} was not 'OK': "
                f"{result.response_text!r}"
            )

        version = runner.get_version()
        cli_versions[runner.cli] = version
        checks.append(
            PreflightCheck(
                cli=runner.cli,
                model=runner.model,
                effort=runner.effort or "",
                cli_version=version,
                ok=ok,
                response_text=result.response_text.strip(),
                checked_at=_now_iso(),
            )
        )

    report = {
        "checked_at": _now_iso(),
        "cli_versions": cli_versions,
        "checks": [asdict(check) for check in checks],
    }

    report_path = Path(output_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2))
    return report
