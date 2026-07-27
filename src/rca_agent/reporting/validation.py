from __future__ import annotations

import csv
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..core.exceptions import QualityGateError
from ..quality import run_quality_gate

QualityGate = Callable[[dict[str, Any]], dict[str, Any]]

_ANALYSIS_SCRIPT = re.compile(
    r'<script id="rca-analysis" type="application/json">(.*?)</script>',
    flags=re.DOTALL,
)


def validate_report(
    report_path: str | Path,
    quality_gate: QualityGate = run_quality_gate,
) -> dict[str, Any]:
    """Validate the canonical analysis embedded in HTML against its CSV."""

    path = Path(report_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)

    analysis = _extract_analysis(path)
    gate = quality_gate(analysis)
    _validate_csv(path.with_name("bugs-normalized.csv"), len(analysis["bugs"]), gate)
    gate["status"] = "passed" if not gate["errors"] else "failed"
    if gate["status"] != "passed":
        raise QualityGateError("; ".join(item["message"] for item in gate["errors"]))
    return gate


def _extract_analysis(path: Path) -> dict[str, Any]:
    match = _ANALYSIS_SCRIPT.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise QualityGateError("HTML não contém o objeto canônico de análise.")
    return json.loads(match.group(1))


def _validate_csv(
    csv_path: Path,
    expected_count: int,
    gate: dict[str, Any],
) -> None:
    if not csv_path.exists():
        gate["errors"].append(
            {"code": "missing_normalized_csv", "message": "CSV normalizado não encontrado."}
        )
        return

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        actual_count = sum(1 for _ in csv.DictReader(handle))
    if actual_count != expected_count:
        gate["errors"].append(
            {
                "code": "csv_html_count_mismatch",
                "message": f"CSV tem {actual_count}; HTML tem {expected_count}.",
            }
        )
