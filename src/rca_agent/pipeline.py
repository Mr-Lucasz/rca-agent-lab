from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .classification import classify_rules
from .clustering import build_clusters
from .config import load_yaml, schema_path
from .ingestion import ingest
from .metrics import calculate_metrics
from .normalization import normalize
from .quality import run_quality_gate
from .report_bug import render_bug_markdown
from .reasoning import (
    build_evidence,
    build_rule_actions,
    build_rule_hypotheses,
    build_rule_insights,
)
from .reporting import write_html, write_normalized_csv
from .utils import project_root, read_json, slug, stable_hash, utc_now, write_json


class QualityGateError(RuntimeError):
    pass


def _validate_schema(value: Any, name: str) -> None:
    path = schema_path(name)
    schema = read_json(path)
    if name == "agent-review.schema.json":
        schema["properties"]["evidence"]["items"] = read_json(schema_path("evidence.schema.json"))
    if name == "analysis.schema.json":
        schema["properties"]["bugs"]["items"] = read_json(schema_path("bug.schema.json"))
        schema["properties"]["evidence"]["items"] = read_json(schema_path("evidence.schema.json"))
    errors = sorted(
        Draft202012Validator(schema).iter_errors(value),
        key=lambda item: list(item.absolute_path),
    )
    if errors:
        details = "; ".join(
            f"{'/'.join(map(str, error.absolute_path)) or '<root>'}: {error.message}"
            for error in errors[:10]
        )
        raise ValueError(f"{name} inválido: {details}")


def _review_template(analysis: dict[str, Any]) -> dict[str, Any]:
    return {
        "reviewed_by": "replace-with-agent-name",
        "model": "replace-with-model",
        "sources_consulted": analysis["metadata"]["sources_consulted"],
        "triage": [],
        "evidence": [],
        "insights": analysis["insights"],
        "hypotheses": analysis["hypotheses"],
        "actions": analysis["actions"],
        "narrative": {
            "headline": "Substitua por uma manchete executiva curta, escrita pelo agente.",
            "executive_summary": "Escreva uma leitura executiva em linguagem natural, técnica e direta, sem repetir os cards do dashboard.",
            "key_findings": [
                "Substitua por um achado prioritário baseado em volume, criticidade e evidência.",
                "Substitua por um segundo achado que explique impacto, recorrência ou risco operacional.",
            ],
            "systemic_patterns": [
                "Substitua por um padrão sistêmico que explique por que os bugs continuam reaparecendo.",
                "Substitua por outro padrão sistêmico sustentado pelas notas de QA e Dev.",
            ],
            "kpi_reviews": [],
            "root_cause_reviews": [],
        },
    }


def _narrative_inputs(
    bugs: list[dict[str, Any]], evidence: list[dict[str, Any]], metrics: dict[str, Any]
) -> dict[str, Any]:
    catalog = load_yaml("root-causes.yml").get("canonical", {})
    evidence_by_bug: dict[str, list[dict[str, Any]]] = {}
    for item in evidence:
        evidence_by_bug.setdefault(item["bug_id"], []).append(item)

    briefs: list[dict[str, Any]] = []
    for profile in metrics.get("root_cause_profiles", [])[:5]:
        cause = profile["root_cause_category"]
        entry = catalog.get(cause, catalog.get("unknown", {}))
        group = [bug for bug in bugs if bug.get("root_cause_category") == cause]
        note_highlights = []
        for bug in group[:4]:
            for field, source in (("qa_analysis_notes", "qa"), ("dev_analysis_notes", "dev")):
                value = bug.get(field)
                if value and value != "unknown":
                    note_highlights.append(
                        {
                            "bug_id": bug["bug_id"],
                            "source": source,
                            "excerpt": value,
                        }
                    )
        evidence_ids = [
            item["evidence_id"]
            for bug in group
            for item in evidence_by_bug.get(bug["bug_id"], [])
            if item["source_type"] in {"dev_note", "qa_note", "actual_behavior"}
        ][:6]
        briefs.append(
            {
                "root_cause_category": cause,
                "display_name": entry.get("display_name", cause),
                "analysis_lens": entry.get("analysis_lens", {}),
                "related_bug_ids": [bug["bug_id"] for bug in group],
                "top_modules": profile.get("top_modules", []),
                "predominant_severity": profile.get("predominant_severity"),
                "avg_detect_hours": profile.get("avg_detect_hours"),
                "reopened_total": profile.get("reopened_total"),
                "production_total": profile.get("production_total"),
                "note_highlights": note_highlights,
                "evidence_ids": evidence_ids,
            }
        )
    return {
        "review_goal": "Escrever uma análise executiva natural, técnica e útil, sem frases de template e sem repetir o dashboard.",
        "writing_preferences": [
            "Priorize leitura humana: diagnóstico, impacto, mecanismo provável e por que persiste.",
            "Aproveite principalmente notas de QA e Dev para sintetizar comportamento recorrente.",
            "Evite jargão gratuito, repetições e frases genéricas de consultoria.",
        ],
        "kpi_briefs": [
            {
                "kpi_id": item["id"],
                "label": item["label"],
                "value": item["value"],
                "unit": item["unit"],
                "formula": item["formula"],
                "sample_size": item["sample_size"],
                "definition": item["definition"],
                "deterministic_insight": item["insight"],
                "deterministic_analysis": item["detailed_analysis"],
                "supporting_bug_ids": item["supporting_bug_ids"],
                "limitations": item["limitations"],
            }
            for item in metrics.get("kpis", [])
        ],
        "root_cause_briefs": briefs,
    }


def prepare(input_path: str | Path, output_hint: str | Path) -> dict[str, str]:
    source = Path(input_path).expanduser().resolve()
    raw = ingest(source)
    bugs, data_quality = normalize(raw, source)
    classify_rules(bugs)
    clusters = build_clusters(bugs)
    metrics = calculate_metrics(bugs)
    evidence = build_evidence(bugs)
    insights = build_rule_insights(bugs, clusters, evidence)
    hypotheses = build_rule_hypotheses(bugs, clusters, evidence)
    actions = build_rule_actions(hypotheses, bugs)
    run_id = f"{slug(source.stem)}-{stable_hash([str(source), len(raw)])}"
    work_dir = project_root() / ".rca-work" / run_id
    analysis = {
        "metadata": {
            "run_id": run_id,
            "input_path": str(source),
            "prepared_at": utc_now(),
            "mode": "rules-baseline",
            "output_hint": str(Path(output_hint)),
            "sources_consulted": [
                {"source": "input_file", "status": "consulted", "details": str(source)},
                {"source": "codebase", "status": "not_requested", "details": ""},
                {"source": "git", "status": "not_requested", "details": ""},
                {"source": "observability", "status": "not_requested", "details": ""},
            ],
        },
        "data_quality": data_quality,
        "bugs": bugs,
        "metrics": metrics,
        "clusters": clusters,
        "evidence": evidence,
        "insights": insights,
        "hypotheses": hypotheses,
        "actions": actions,
        "narrative": {},
        "narrative_inputs": _narrative_inputs(bugs, evidence, metrics),
        "quality_gate": {},
    }
    analysis["quality_gate"] = run_quality_gate(analysis)
    work_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = work_dir / "analysis.json"
    template_path = work_dir / "agent-review.template.json"
    write_json(analysis_path, analysis)
    write_json(template_path, _review_template(analysis))
    write_json(
        work_dir / "run.json",
        {"input": str(source), "output": str(Path(output_hint)), "analysis": str(analysis_path)},
    )
    return {
        "work_dir": str(work_dir),
        "analysis": str(analysis_path),
        "review_template": str(template_path),
    }


def apply_review(analysis: dict[str, Any], review: dict[str, Any]) -> None:
    _validate_schema(review, "agent-review.schema.json")
    existing_evidence = {item["evidence_id"]: item for item in analysis["evidence"]}
    for item in review["evidence"]:
        if item["evidence_id"] in existing_evidence and existing_evidence[item["evidence_id"]] != item:
            raise ValueError(f"Review tenta redefinir {item['evidence_id']}. Use um novo ID.")
        existing_evidence[item["evidence_id"]] = item
    analysis["evidence"] = list(existing_evidence.values())

    triage = {item["bug_id"]: item for item in review["triage"]}
    for bug in analysis["bugs"]:
        item = triage.get(bug["bug_id"])
        if not item:
            continue
        bug["agent_suggested_severity"] = item.get(
            "suggested_severity", bug["agent_suggested_severity"]
        )
        bug["agent_suggested_bug_type"] = item.get(
            "suggested_bug_type", bug["agent_suggested_bug_type"]
        )
        bug["agent_suggested_root_cause_category"] = item.get(
            "suggested_root_cause_category", bug["agent_suggested_root_cause_category"]
        )
        bug["agent_suggestion_confidence"] = item["confidence"]
        bug["agent_suggestion_rationale"] = item["rationale"]
        bug["agent_review_status"] = item["review_status"]

    if review["insights"]:
        analysis["insights"] = review["insights"]
    if review["hypotheses"]:
        analysis["hypotheses"] = review["hypotheses"]
    if review["actions"]:
        analysis["actions"] = review["actions"]
    if review.get("narrative"):
        analysis["narrative"] = review["narrative"]
        reviews = {
            item["kpi_id"]: item for item in review["narrative"].get("kpi_reviews", [])
        }
        for kpi in analysis.get("metrics", {}).get("kpis", []):
            item = reviews.get(kpi["id"])
            if not item:
                continue
            kpi["insight"] = item["insight"]
            kpi["detailed_analysis"] = item["detailed_analysis"]
            if item.get("limitations"):
                kpi["limitations"] = item["limitations"]
            if item.get("supporting_bug_ids"):
                kpi["supporting_bug_ids"] = item["supporting_bug_ids"]
    analysis["metadata"]["sources_consulted"] = review["sources_consulted"]
    analysis["metadata"]["reviewed_by"] = review["reviewed_by"]
    analysis["metadata"]["model"] = review.get("model", "")
    analysis["metadata"]["mode"] = "agent-reviewed"
    analysis["metadata"]["reviewed_at"] = utc_now()


def finalize(
    work_dir: str | Path, output_dir: str | Path, review_path: str | Path | None = None
) -> dict[str, Any]:
    work = Path(work_dir).expanduser().resolve()
    analysis = read_json(work / "analysis.json")
    if review_path:
        apply_review(analysis, read_json(Path(review_path).expanduser().resolve()))
    _validate_schema(analysis, "analysis.schema.json")
    analysis["quality_gate"] = run_quality_gate(analysis)
    if analysis["quality_gate"]["status"] != "passed":
        write_json(work / "analysis.failed.json", analysis)
        messages = "; ".join(item["message"] for item in analysis["quality_gate"]["errors"])
        raise QualityGateError(f"Quality gate falhou: {messages}")
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    csv_path = destination / "bugs-normalized.csv"
    html_path = destination / "rca-report.html"
    write_normalized_csv(csv_path, analysis)
    write_html(html_path, analysis)
    write_json(work / "analysis.final.json", analysis)
    return {
        "csv": str(csv_path),
        "html": str(html_path),
        "quality_gate": analysis["quality_gate"],
    }


def analyze(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    prepared = prepare(input_path, output_dir)
    return finalize(prepared["work_dir"], output_dir)


def report_bug(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    source = Path(input_path).expanduser().resolve()
    raw = ingest(source)
    bugs, _ = normalize(raw, source)
    if len(bugs) != 1:
        raise ValueError("report-bug exige exatamente um bug na entrada.")
    classify_rules(bugs)
    bug = bugs[0]
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / "bug-report.json"
    markdown_path = destination / "bug-report.md"
    write_json(json_path, bug)
    markdown_path.write_text(render_bug_markdown(bug), encoding="utf-8")
    return {"json": str(json_path), "markdown": str(markdown_path)}


def validate_report(report_path: str | Path) -> dict[str, Any]:
    path = Path(report_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    content = path.read_text(encoding="utf-8")
    match = re.search(
        r'<script id="rca-analysis" type="application/json">(.*?)</script>',
        content,
        flags=re.DOTALL,
    )
    if not match:
        raise QualityGateError("HTML não contém o objeto canônico de análise.")
    analysis = json.loads(match.group(1))
    gate = run_quality_gate(analysis)
    csv_path = path.with_name("bugs-normalized.csv")
    if not csv_path.exists():
        gate["errors"].append(
            {"code": "missing_normalized_csv", "message": "CSV normalizado não encontrado."}
        )
    else:
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            count = sum(1 for _ in csv.DictReader(handle))
        if count != len(analysis["bugs"]):
            gate["errors"].append(
                {
                    "code": "csv_html_count_mismatch",
                    "message": f"CSV tem {count}; HTML tem {len(analysis['bugs'])}.",
                }
            )
    gate["status"] = "passed" if not gate["errors"] else "failed"
    if gate["status"] != "passed":
        raise QualityGateError("; ".join(item["message"] for item in gate["errors"]))
    return gate
