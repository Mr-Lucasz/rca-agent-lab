from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from ..core.utils import UNKNOWN


def write_normalized_csv(path: Path, analysis: dict[str, Any]) -> None:
    bugs = analysis["bugs"]
    cluster_by_id = {item["cluster_id"]: item for item in analysis["clusters"]}
    hypotheses_by_cluster: dict[str, list[dict[str, Any]]] = {}
    actions_by_cluster: dict[str, list[dict[str, Any]]] = {}
    for item in analysis["hypotheses"]:
        hypotheses_by_cluster.setdefault(item["cluster_id"], []).append(item)
    for item in analysis["actions"]:
        actions_by_cluster.setdefault(item["cluster_id"], []).append(item)
    rows: list[dict[str, Any]] = []
    for bug in bugs:
        cluster = cluster_by_id.get(bug["cluster_id"], {})
        row = dict(bug)
        row.update(
            {
                "cluster_name": cluster.get("name", UNKNOWN),
                "cluster_investigation_score": cluster.get("investigation_score", UNKNOWN),
                "hypothesis_ids": "|".join(
                    item["hypothesis_id"]
                    for item in hypotheses_by_cluster.get(bug["cluster_id"], [])
                )
                or UNKNOWN,
                "hypothesis_summary": " | ".join(
                    item["statement"]
                    for item in hypotheses_by_cluster.get(bug["cluster_id"], [])
                )
                or UNKNOWN,
                "action_ids": "|".join(
                    item["action_id"] for item in actions_by_cluster.get(bug["cluster_id"], [])
                )
                or UNKNOWN,
                "requires_human_review": "true",
            }
        )
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
