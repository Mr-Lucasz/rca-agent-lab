from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..analysis.classification import classify_rules
from ..analysis.clustering import build_clusters
from ..analysis.normalization import normalize
from ..analysis.reasoning import build_evidence
from ..core.exceptions import ClarificationRequiredError, QualityGateError
from ..core.schema_validation import validate_schema
from ..core.utils import project_root, read_json, slug, stable_hash, utc_now, write_json
from ..ingestion import ingest
from ..metrics import calculate_metrics
from ..quality import run_quality_gate
from ..reporting import write_html, write_normalized_csv
from ..reporting.bug_report import render_bug_markdown
from ..reporting.validation import validate_report as validate_published_report
from .clarifications import (
    build_clarification_questions,
    synchronize_clarification_review,
)
from .questions import prepare_review_question_artifacts
from .review import (
    apply_review as merge_review,
)
from .review import (
    build_narrative_inputs,
    build_review_template,
    stage_review_clarifications,
)

Analysis = dict[str, Any]
IngestRecords = Callable[[str | Path], list[dict[str, Any]]]
SchemaValidation = Callable[[Any, str], None]
QualityGate = Callable[[Analysis], dict[str, Any]]


class RcaPipeline:
    """Coordinates deterministic RCA stages through replaceable boundaries."""

    def __init__(
        self,
        input_ingestor: IngestRecords = ingest,
        schema_validation: SchemaValidation = validate_schema,
        quality_gate: QualityGate = run_quality_gate,
    ) -> None:
        self._ingest = input_ingestor
        self._validate_schema = schema_validation
        self._run_quality_gate = quality_gate

    def prepare(
        self,
        input_path: str | Path,
        output_hint: str | Path,
    ) -> dict[str, str]:
        source = Path(input_path).expanduser().resolve()
        raw_records = self._ingest(source)
        analysis = self._build_analysis(source, output_hint, raw_records)
        work_dir = self._work_dir(analysis["metadata"]["run_id"])
        return self._write_preparation_artifacts(
            work_dir,
            source,
            output_hint,
            analysis,
        )

    def finalize(
        self,
        work_dir: str | Path,
        output_dir: str | Path,
        review_path: str | Path | None = None,
    ) -> dict[str, Any]:
        work = Path(work_dir).expanduser().resolve()
        analysis = read_json(work / "analysis.json")
        if review_path is not None:
            review = read_json(Path(review_path).expanduser().resolve())
            self._validate_schema(review, "agent-review.schema.json")
            stage_review_clarifications(analysis, review)
            merge_review(analysis, review, self._validate_schema)

        self._validate_schema(analysis, "analysis.schema.json")
        self._ensure_clarifications_resolved(work, analysis)
        analysis["quality_gate"] = self._run_quality_gate(analysis)
        self._ensure_quality_gate_passed(work, analysis)
        return self._publish(work, output_dir, analysis)

    def prepare_review_questions(
        self,
        work_dir: str | Path,
        review_path: str | Path,
    ) -> dict[str, Any]:
        return prepare_review_question_artifacts(
            work_dir,
            review_path,
            self._validate_schema,
        )

    def analyze(
        self,
        input_path: str | Path,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        prepared = self.prepare(input_path, output_dir)
        return self.finalize(prepared["work_dir"], output_dir)

    def record_clarification(
        self,
        work_dir: str | Path,
        question_id: str,
        status: str,
        answer: str | None = None,
    ) -> dict[str, Any]:
        work = Path(work_dir).expanduser().resolve()
        analysis = read_json(work / "analysis.json")
        questions = analysis.get("clarification_questions", [])
        question = next(
            (item for item in questions if item.get("question_id") == question_id),
            None,
        )
        if question is None:
            raise ValueError(f"Pergunta de esclarecimento inexistente: {question_id}.")
        if status not in {"accepted", "answered", "declined"}:
            raise ValueError(
                "Status deve ser accepted, answered ou declined."
            )
        if status == "accepted" and question["question_type"] not in {
            "confirm_suggestions",
            "confirm_field_mapping",
        }:
            raise ValueError(
                f"{question_id} solicita informação factual; use answered ou declined."
            )
        if status == "answered" and not str(answer or "").strip():
            raise ValueError(f"{question_id} exige --answer não vazio.")

        review_path = work / "agent-review.json"
        if review_path.exists():
            review = read_json(review_path)
        else:
            review = build_review_template(analysis)
        if "clarification_questions" not in review:
            review["clarification_questions"] = deepcopy(questions)
        else:
            synchronize_clarification_review(review, questions)

        review_question = next(
            (
                item
                for item in review["clarification_questions"]
                if item.get("question_id") == question_id
            ),
            None,
        )
        if review_question is None:
            raise ValueError(
                f"O review não contém a pergunta original {question_id}."
            )
        review_question["status"] = status
        if status == "answered":
            review_question["answer"] = str(answer).strip()
        else:
            review_question.pop("answer", None)

        self._validate_schema(review, "agent-review.schema.json")
        write_json(review_path, review)
        open_ids = [
            item["question_id"]
            for item in review["clarification_questions"]
            if item.get("status") == "open"
        ]
        return {
            "review": str(review_path),
            "recorded": question_id,
            "status": status,
            "open_questions": open_ids,
        }

    def report_bug(
        self,
        input_path: str | Path,
        output_dir: str | Path,
    ) -> dict[str, Any]:
        source = Path(input_path).expanduser().resolve()
        raw_records = self._ingest(source)
        bugs, _ = normalize(raw_records, source)
        if len(bugs) != 1:
            raise ValueError("report-bug exige exatamente um bug na entrada.")

        classify_rules(bugs)
        destination = Path(output_dir).expanduser().resolve()
        destination.mkdir(parents=True, exist_ok=True)
        json_path = destination / "bug-report.json"
        markdown_path = destination / "bug-report.md"
        write_json(json_path, bugs[0])
        markdown_path.write_text(render_bug_markdown(bugs[0]), encoding="utf-8")
        return {"json": str(json_path), "markdown": str(markdown_path)}

    def validate_report(self, report_path: str | Path) -> dict[str, Any]:
        return validate_published_report(report_path, self._run_quality_gate)

    def _build_analysis(
        self,
        source: Path,
        output_hint: str | Path,
        raw_records: list[dict[str, Any]],
    ) -> Analysis:
        bugs, data_quality = normalize(raw_records, source)
        classify_rules(bugs)
        clarification_questions = build_clarification_questions(
            bugs,
            data_quality,
        )
        clusters = build_clusters(bugs)
        metrics = calculate_metrics(bugs)
        evidence = build_evidence(bugs)
        run_id = f"{slug(source.stem)}-{stable_hash([str(source), len(raw_records)])}"
        analysis = {
            "metadata": {
                "run_id": run_id,
                "input_path": str(source),
                "prepared_at": utc_now(),
                "mode": "rules-baseline",
                "output_hint": str(Path(output_hint)),
                "sources_consulted": _default_sources(source),
            },
            "data_quality": data_quality,
            "clarification_questions": clarification_questions,
            "bugs": bugs,
            "metrics": metrics,
            "clusters": clusters,
            "evidence": evidence,
            "insights": [],
            "hypotheses": [],
            "actions": [],
            "narrative": {},
            "narrative_inputs": build_narrative_inputs(bugs, evidence, metrics),
            "quality_gate": {},
        }
        analysis["quality_gate"] = self._run_quality_gate(analysis)
        return analysis

    @staticmethod
    def _work_dir(run_id: str) -> Path:
        return project_root() / ".rca-work" / run_id

    @staticmethod
    def _write_preparation_artifacts(
        work_dir: Path,
        source: Path,
        output_hint: str | Path,
        analysis: Analysis,
    ) -> dict[str, str]:
        work_dir.mkdir(parents=True, exist_ok=True)
        analysis_path = work_dir / "analysis.json"
        template_path = work_dir / "agent-review.template.json"
        write_json(analysis_path, analysis)
        write_json(template_path, build_review_template(analysis))
        clarification_path = work_dir / "clarification-questions.json"
        write_json(clarification_path, analysis.get("clarification_questions", []))
        write_json(
            work_dir / "run.json",
            {
                "input": str(source),
                "output": str(Path(output_hint)),
                "analysis": str(analysis_path),
            },
        )
        return {
            "work_dir": str(work_dir),
            "analysis": str(analysis_path),
            "review_template": str(template_path),
            "clarification_questions": str(clarification_path),
        }

    @staticmethod
    def _ensure_quality_gate_passed(work: Path, analysis: Analysis) -> None:
        if analysis["quality_gate"]["status"] == "passed":
            return
        write_json(work / "analysis.failed.json", analysis)
        messages = "; ".join(
            item["message"] for item in analysis["quality_gate"]["errors"]
        )
        raise QualityGateError(f"Quality gate falhou: {messages}")

    @staticmethod
    def _ensure_clarifications_resolved(work: Path, analysis: Analysis) -> None:
        open_questions = [
            item
            for item in analysis.get("clarification_questions", [])
            if item.get("status") == "open"
        ]
        if not open_questions:
            return

        awaiting_path = work / "analysis.awaiting-clarification.json"
        questions_path = work / "clarification-questions.json"
        write_json(awaiting_path, analysis)
        write_json(questions_path, open_questions)
        question_ids = ", ".join(
            str(item.get("question_id", "sem-id")) for item in open_questions
        )
        raise ClarificationRequiredError(
            "Finalização bloqueada pelo gate humano. "
            f"Responda ou recuse as perguntas {question_ids} em "
            f"{work / 'agent-review.json'} usando o template "
            f"{work / 'agent-review.template.json'}; depois execute finalize novamente. "
            f"Perguntas abertas: {questions_path}"
        )

    @staticmethod
    def _publish(
        work: Path,
        output_dir: str | Path,
        analysis: Analysis,
    ) -> dict[str, Any]:
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


def _default_sources(source: Path) -> list[dict[str, str]]:
    return [
        {"source": "input_file", "status": "consulted", "details": str(source)},
        {"source": "codebase", "status": "not_requested", "details": ""},
        {"source": "git", "status": "not_requested", "details": ""},
        {"source": "observability", "status": "not_requested", "details": ""},
    ]


_DEFAULT_PIPELINE = RcaPipeline()


def prepare(input_path: str | Path, output_hint: str | Path) -> dict[str, str]:
    return _DEFAULT_PIPELINE.prepare(input_path, output_hint)


def apply_review(analysis: Analysis, review: dict[str, Any]) -> None:
    """Backward-compatible facade for semantic review merging."""

    merge_review(analysis, review)


def prepare_review_questions(
    work_dir: str | Path,
    review_path: str | Path,
) -> dict[str, Any]:
    return _DEFAULT_PIPELINE.prepare_review_questions(work_dir, review_path)


def finalize(
    work_dir: str | Path,
    output_dir: str | Path,
    review_path: str | Path | None = None,
) -> dict[str, Any]:
    return _DEFAULT_PIPELINE.finalize(work_dir, output_dir, review_path)


def analyze(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    return _DEFAULT_PIPELINE.analyze(input_path, output_dir)


def record_clarification(
    work_dir: str | Path,
    question_id: str,
    status: str,
    answer: str | None = None,
) -> dict[str, Any]:
    return _DEFAULT_PIPELINE.record_clarification(
        work_dir,
        question_id,
        status,
        answer,
    )


def report_bug(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    return _DEFAULT_PIPELINE.report_bug(input_path, output_dir)


def validate_report(report_path: str | Path) -> dict[str, Any]:
    return _DEFAULT_PIPELINE.validate_report(report_path)
