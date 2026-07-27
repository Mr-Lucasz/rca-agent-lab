import json
from pathlib import Path

from rca_agent.analysis.classification import classify_rules
from rca_agent.analysis.normalization import normalize
from rca_agent.ingestion import ingest
from rca_agent.metrics import calculate_metrics

ROOT = Path(__file__).resolve().parents[1]


def test_demo_metrics_keep_expected_values_after_decomposition():
    source = ROOT / "data" / "input" / "bugs-demo.csv"
    bugs, _ = normalize(ingest(source), source)
    classify_rules(bugs)

    metrics = calculate_metrics(bugs)
    values = {
        kpi["id"]: (kpi["value"], kpi["numerator"], kpi["denominator"])
        for kpi in metrics["kpis"]
    }

    assert values == {
        "defect_count": (12, 12, 12),
        "production_escape_rate": (66.7, 8, 12),
        "reopen_rate": (25.0, 3, 12),
        "detection_lead_time_hours": (None, None, 0),
        "ticket_resolution_time_hours": (14.5, 174.0, 12),
        "high_severity_share": (58.3, 7, 12),
        "critical_bug_count": (2, 2, 12),
        "causal_signal_coverage_rate": (100.0, 12, 12),
        "top_module_share": (25.0, 3, 12),
        "top_bug_type_share": (25.0, 3, 12),
        "top_root_cause_share": (33.3, 4, 12),
    }
    assert metrics["highlights"]["top_module"] == {
        "label": "pagamentos",
        "count": 3,
    }


def test_metric_copy_has_no_corrupted_encoding_tokens():
    source = ROOT / "data" / "input" / "bugs-demo.csv"
    bugs, _ = normalize(ingest(source), source)
    classify_rules(bugs)

    metrics = calculate_metrics(bugs)
    serialized = json.dumps(metrics, ensure_ascii=False)
    kpis = {kpi["id"]: kpi for kpi in metrics["kpis"]}

    assert "?" not in serialized
    assert kpis["production_escape_rate"]["label"] == "Escape para produção"
    assert kpis["top_module_share"]["label"] == "Concentração no módulo líder"
    assert kpis["production_escape_rate"]["formula"].endswith("× 100")
    assert metrics["cross_tab_meta"]["severity_by_module"]["row_label"] == "Módulo"


def test_health_export_aliases_preserve_reported_operational_fields():
    source = ROOT / "data" / "input" / "health-export.csv"
    raw = [
        {
            "ID_Bug": "MED-2024",
            "Título": "Botão oculto",
            "Severidade": "Alta",
            "Ambiente_Encontrado": "PRD",
            "Qtd_Reaberturas": "1",
            "Notas_Dev_QA": "QA: reproduzido. Dev: corrigido.",
        }
    ]

    bugs, quality = normalize(raw, source)

    assert bugs[0]["bug_id"] == "MED-2024"
    assert bugs[0]["environment"] == "production"
    assert bugs[0]["reopened"] == "true"
    assert bugs[0]["dev_analysis_notes"] == "QA: reproduzido. Dev: corrigido."
    assert quality["causal_signal_coverage_percent"] == 100.0
    assert quality["records_with_causal_signals"] == 1
    assert not any(issue["code"] == "missing_id" for issue in quality["issues"])


def test_causal_signal_patterns_cross_all_configured_dimensions():
    source = ROOT / "data" / "input" / "bugs-demo.csv"
    bugs, _ = normalize(ingest(source), source)
    classify_rules(bugs)

    patterns = calculate_metrics(bugs)["causal_signal_patterns"]

    assert patterns["records_with_signals"] == 12
    assert patterns["coverage_percent"] == 100.0
    assert patterns["source_coverage"] == {"qa": 12, "dev": 12}
    assert patterns["multi_source_records"] == 12
    assert set(patterns["contextual_distributions"]) == {
        "severity",
        "bug_type",
        "root_cause_category",
        "affected_module",
        "environment",
        "team",
        "version",
    }
    assert patterns["bug_ids"] == [bug["bug_id"] for bug in bugs]


def test_reported_durations_feed_honest_duration_metrics_without_timestamps():
    source = ROOT / "data" / "input" / "duration-export.csv"
    raw = [
        {
            "ID_Bug": "OPS-1",
            "Título": "Falha operacional",
            "Descrição": "Fluxo interrompido.",
            "Tempo_Deteccao_Horas": "2,5",
            "Tempo_Resolucao_Horas": "7",
        }
    ]

    bugs, _ = normalize(raw, source)
    metrics = calculate_metrics(bugs)
    kpis = {item["id"]: item for item in metrics["kpis"]}

    assert bugs[0]["detection_time_hours"] == 2.5
    assert bugs[0]["resolution_time_hours"] == 7.0
    assert kpis["detection_lead_time_hours"]["value"] == 2.5
    assert kpis["ticket_resolution_time_hours"]["value"] == 7.0
    assert (
        kpis["detection_lead_time_hours"]["methodology"]["source_counts"]
        == {"reported:detection_time_hours": 1}
    )


def test_detection_lead_time_requires_occurrence_start_not_ticket_creation():
    source = ROOT / "data" / "input" / "duration-export.csv"
    raw = [
        {
            "ID_Bug": "OPS-2",
            "Título": "Falha operacional",
            "created_at": "2026-01-01T08:00:00Z",
            "detected_at": "2026-01-01T10:00:00Z",
        }
    ]

    bugs, _ = normalize(raw, source)
    kpis = {
        item["id"]: item
        for item in calculate_metrics(bugs)["kpis"]
    }

    assert kpis["detection_lead_time_hours"]["value"] is None


def test_detection_lead_time_uses_observable_occurrence_start():
    source = ROOT / "data" / "input" / "duration-export.csv"
    raw = [
        {
            "ID_Bug": "OPS-3",
            "Título": "Falha operacional",
            "occurrence_started_at": "2026-01-01T08:00:00Z",
            "detected_at": "2026-01-01T10:30:00Z",
        }
    ]

    bugs, _ = normalize(raw, source)
    kpis = {
        item["id"]: item
        for item in calculate_metrics(bugs)["kpis"]
    }

    assert kpis["detection_lead_time_hours"]["value"] == 2.5
