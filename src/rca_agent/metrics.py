from __future__ import annotations

import re
from collections import Counter, defaultdict
from statistics import mean
from typing import Any

from .utils import UNKNOWN, parse_datetime, percent

STOPWORDS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "por",
    "que",
    "sem",
    "ser",
    "seu",
    "sua",
    "the",
    "uma",
    "um",
}


def _distribution(bugs: list[dict[str, Any]], field: str) -> dict[str, int]:
    return dict(sorted(Counter(str(bug.get(field, UNKNOWN)) for bug in bugs).items()))


def _date_distribution(bugs: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for bug in bugs:
        value = parse_datetime(bug.get(field))
        if value:
            counts[value.date().isoformat()] += 1
    return dict(sorted(counts.items()))


def _cross_tab(bugs: list[dict[str, Any]], row_field: str, column_field: str) -> dict[str, dict[str, int]]:
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    for bug in bugs:
        matrix[str(bug.get(row_field, UNKNOWN))][str(bug.get(column_field, UNKNOWN))] += 1
    return {row: dict(sorted(values.items())) for row, values in sorted(matrix.items())}


def _tokenize_notes(text: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[a-z0-9à-ÿ]{3,}", text.casefold())
        if token not in STOPWORDS and token != UNKNOWN
    ]


def _top_note_terms(bugs: list[dict[str, Any]], fields: tuple[str, ...]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for bug in bugs:
        parts = [str(bug.get(field, "")) for field in fields if bug.get(field, UNKNOWN) != UNKNOWN]
        for token in _tokenize_notes(" ".join(parts)):
            counts[token] += 1
    return dict(counts.most_common(18))


def _top_focus(values: dict[str, int]) -> tuple[str, int]:
    if not values:
        return (UNKNOWN, 0)
    label, count = max(values.items(), key=lambda item: (item[1], item[0]))
    return label, count


def _predominant(bugs: list[dict[str, Any]], field: str) -> str:
    values = Counter(str(bug.get(field, UNKNOWN)) for bug in bugs if bug.get(field, UNKNOWN) != UNKNOWN)
    return values.most_common(1)[0][0] if values else UNKNOWN


def _root_cause_profiles(bugs: list[dict[str, Any]], total: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for bug in bugs:
        grouped[str(bug.get("root_cause_category", UNKNOWN))].append(bug)
    profiles: list[dict[str, Any]] = []
    for cause, group in grouped.items():
        detected = _duration_hours(group, "created_at", "detected_at")
        modules = Counter(
            bug["affected_module"] for bug in group if bug.get("affected_module", UNKNOWN) != UNKNOWN
        )
        reopened_total = sum(1 for bug in group if bug.get("reopened") == "true")
        production_total = sum(1 for bug in group if bug.get("environment") == "production")
        profiles.append(
            {
                "root_cause_category": cause,
                "count": len(group),
                "share_percent": percent(len(group), total),
                "predominant_severity": _predominant(group, "severity"),
                "top_modules": [module for module, _ in modules.most_common(3)],
                "avg_detect_hours": round(mean(detected), 1) if detected else None,
                "reopened_total": reopened_total,
                "production_total": production_total,
                "sample_bug_ids": [bug["bug_id"] for bug in group[:4]],
            }
        )
    return sorted(
        profiles,
        key=lambda item: (-item["count"], -(item["share_percent"] or 0), item["root_cause_category"]),
    )


def _duration_hours(bugs: list[dict[str, Any]], start: str, end: str) -> list[float]:
    values: list[float] = []
    for bug in bugs:
        left = parse_datetime(bug.get(start))
        right = parse_datetime(bug.get(end))
        if left and right and right >= left:
            values.append((right - left).total_seconds() / 3600)
    return values


def _kpi(
    identifier: str,
    label: str,
    value: float | int | None,
    unit: str,
    numerator: float | int | None,
    denominator: float | int | None,
    formula: str,
    limitation: str,
) -> dict[str, Any]:
    return {
        "id": identifier,
        "label": label,
        "value": value,
        "unit": unit,
        "numerator": numerator,
        "denominator": denominator,
        "sample_size": denominator,
        "formula": formula,
        "limitations": [limitation] if limitation else [],
        "chart": "progress" if denominator else "value",
        "context_value": numerator,
        "context_total": denominator,
    }


def _bug_ids(
    bugs: list[dict[str, Any]], predicate: Any, limit: int = 10
) -> list[str]:
    return [str(bug["bug_id"]) for bug in bugs if predicate(bug)][:limit]


def _enrich_kpis(
    kpis: list[dict[str, Any]],
    bugs: list[dict[str, Any]],
    *,
    top_module: str,
    top_type: str,
    top_root_cause: str,
) -> list[dict[str, Any]]:
    total = len(bugs)
    definitions = {
        "defect_count": "Quantidade de registros de bug válidos incluídos nesta análise.",
        "production_escape_rate": "Percentual de bugs com ambiente conhecido que chegaram à produção.",
        "reopen_rate": "Percentual de bugs com status de reabertura conhecido que foram reabertos.",
        "mttd_hours": "Tempo médio entre a criação do bug e sua detecção.",
        "mttr_hours": "Tempo médio entre a criação do bug e sua resolução.",
        "causal_coverage_rate": "Percentual de bugs com ao menos uma nota de análise de QA ou Dev.",
        "high_severity_share": "Participação de bugs críticos ou altos no volume analisado.",
        "critical_bug_count": "Quantidade absoluta de bugs classificados como críticos.",
        "top_module_share": "Participação do módulo com maior volume de bugs na base.",
        "top_bug_type_share": "Participação do tipo de bug mais frequente na base.",
        "top_root_cause_share": "Participação do sinal de categoria RCA mais frequente na base.",
    }
    supporting = {
        "defect_count": _bug_ids(bugs, lambda _: True),
        "production_escape_rate": _bug_ids(
            bugs, lambda bug: bug.get("environment") == "production"
        ),
        "reopen_rate": _bug_ids(bugs, lambda bug: bug.get("reopened") == "true"),
        "mttd_hours": _bug_ids(
            bugs,
            lambda bug: parse_datetime(bug.get("created_at")) is not None
            and parse_datetime(bug.get("detected_at")) is not None,
        ),
        "mttr_hours": _bug_ids(
            bugs,
            lambda bug: parse_datetime(bug.get("created_at")) is not None
            and parse_datetime(bug.get("resolved_at")) is not None,
        ),
        "causal_coverage_rate": _bug_ids(
            bugs,
            lambda bug: bug.get("qa_analysis_notes") != UNKNOWN
            or bug.get("dev_analysis_notes") != UNKNOWN,
        ),
        "high_severity_share": _bug_ids(
            bugs, lambda bug: bug.get("severity") in {"critical", "high"}
        ),
        "critical_bug_count": _bug_ids(
            bugs, lambda bug: bug.get("severity") == "critical"
        ),
        "top_module_share": _bug_ids(
            bugs, lambda bug: bug.get("affected_module") == top_module
        ),
        "top_bug_type_share": _bug_ids(
            bugs, lambda bug: bug.get("bug_type") == top_type
        ),
        "top_root_cause_share": _bug_ids(
            bugs, lambda bug: bug.get("root_cause_category") == top_root_cause
        ),
    }
    focus = {
        "top_module_share": top_module,
        "top_bug_type_share": top_type,
        "top_root_cause_share": top_root_cause,
    }
    for kpi in kpis:
        identifier = kpi["id"]
        value = kpi.get("value")
        sample = kpi.get("denominator") or 0
        label = kpi["label"]
        if value is None:
            status = "insufficient"
            insight = f"{label} não pode ser calculado com os dados disponíveis."
            analysis = (
                "O indicador permanece sem valor porque não há pares ou campos válidos suficientes. "
                "A próxima ação é melhorar a captura do dado antes de interpretar desempenho."
            )
        elif identifier == "defect_count":
            status = "context"
            insight = f"A análise usa {int(value)} bugs como universo de referência."
            analysis = (
                f"Esse volume é o denominador dos demais indicadores. Ele descreve a base recebida, "
                f"mas não mede sozinho melhora ou piora da qualidade; compare períodos equivalentes "
                f"e a quantidade de entregas para interpretar tendência."
            )
        elif identifier == "production_escape_rate":
            status = "attention" if value >= 20 else "watch" if value > 0 else "stable"
            insight = (
                f"{kpi['numerator']} de {sample} bugs com ambiente conhecido chegaram à produção "
                f"({value}%)."
            )
            analysis = (
                "Escape indica falha das barreiras anteriores ao deploy. A leitura precisa ser cruzada "
                "com severidade, módulo e notas de QA/Dev para localizar qual mecanismo de prevenção "
                "não conteve o defeito."
            )
        elif identifier == "reopen_rate":
            status = "attention" if value >= 15 else "watch" if value > 0 else "stable"
            insight = f"{kpi['numerator']} de {sample} bugs conhecidos foram reabertos ({value}%)."
            analysis = (
                "Reabertura recorrente pode sinalizar correção parcial, critério de aceite incompleto "
                "ou validação insuficiente. Os tickets listados devem ser comparados pelo comportamento "
                "antes e depois da correção para separar reincidência real de mudança de escopo."
            )
        elif identifier in {"mttd_hours", "mttr_hours"}:
            status = "attention" if value >= 72 else "watch" if value >= 24 else "stable"
            kind = "detecção" if identifier == "mttd_hours" else "resolução"
            insight = f"O tempo médio de {kind} foi de {value} horas em {sample} registros válidos."
            analysis = (
                f"O valor resume apenas registros com datas coerentes. Analise a dispersão e os casos "
                f"mais demorados antes de atribuir o resultado ao processo; poucos outliers podem "
                f"dominar a média de {kind}."
            )
        elif identifier == "causal_coverage_rate":
            status = "stable" if value >= 80 else "watch" if value >= 50 else "attention"
            insight = f"{kpi['numerator']} de {sample} bugs têm notas de QA ou Dev ({value}%)."
            analysis = (
                "Cobertura alta aumenta a capacidade de formular hipóteses rastreáveis, mas nota "
                "preenchida não é causa confirmada. Cobertura baixa reduz confiança e deve gerar uma "
                "barreira de melhoria do report antes de conclusões causais."
            )
        elif identifier == "high_severity_share":
            status = "attention" if value >= 30 else "watch" if value > 0 else "stable"
            insight = f"{kpi['numerator']} de {sample} bugs são críticos ou altos ({value}%)."
            analysis = (
                "A concentração de criticidade orienta prioridade de investigação. Cruze com ambiente "
                "e recorrência: severidade alta em produção ou reabertura deve superar volume simples "
                "na fila de RCA."
            )
        elif identifier == "critical_bug_count":
            status = "attention" if value > 0 else "stable"
            insight = f"A base contém {int(value)} bug(s) crítico(s) em {sample} registros."
            analysis = (
                "Mesmo uma contagem pequena merece inspeção individual por impacto. O número é uma "
                "classificação de triagem e precisa ser validado contra efeito real, alcance e "
                "recuperabilidade."
            )
        else:
            focus_value = focus.get(identifier, UNKNOWN)
            status = "attention" if value >= 40 else "watch" if value >= 25 else "context"
            insight = (
                f"{focus_value} concentra {kpi['numerator']} de {sample} bugs ({value}%)."
            )
            if identifier == "top_root_cause_share":
                analysis = (
                    "A categoria RCA reportada é apenas um sinal de triagem. Use a concentração para "
                    "priorizar perguntas e evidências, nunca para declarar causa sem mecanismo, "
                    "sequência temporal e teste de confirmação."
                )
            else:
                analysis = (
                    "A concentração sugere um padrão prioritário, mas tickets repetidos podem pertencer "
                    "à mesma família de defeito. Deduplicação, notas e comportamento observado devem "
                    "confirmar se existe um mecanismo comum."
                )
        kpi.update(
            {
                "definition": definitions[identifier],
                "status": status,
                "insight": insight,
                "detailed_analysis": analysis,
                "supporting_bug_ids": supporting[identifier],
                "requires_human_review": True,
            }
        )
    return kpis


def calculate_metrics(bugs: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(bugs)
    known_environment = [bug for bug in bugs if bug["environment"] != UNKNOWN]
    production = sum(1 for bug in known_environment if bug["environment"] == "production")
    known_reopened = [bug for bug in bugs if bug["reopened"] != UNKNOWN]
    reopened = sum(1 for bug in known_reopened if bug["reopened"] == "true")
    causal = sum(
        1
        for bug in bugs
        if bug["dev_analysis_notes"] != UNKNOWN or bug["qa_analysis_notes"] != UNKNOWN
    )
    critical = sum(1 for bug in bugs if bug["severity"] == "critical")
    high_severity = sum(1 for bug in bugs if bug["severity"] in {"critical", "high"})
    mttd = _duration_hours(bugs, "created_at", "detected_at")
    mttr = _duration_hours(bugs, "created_at", "resolved_at")
    modules = _distribution(bugs, "affected_module")
    bug_types = _distribution(bugs, "bug_type")
    root_causes = _distribution(bugs, "root_cause_category")
    environments = _distribution(bugs, "environment")
    teams = _distribution(bugs, "team")
    versions = _distribution(bugs, "version")
    top_module, top_module_count = _top_focus(modules)
    top_type, top_type_count = _top_focus(bug_types)
    top_root_cause, top_root_cause_count = _top_focus(root_causes)
    kpis = [
        _kpi("defect_count", "Bugs analisados", total, "count", total, total, "count(rows)", ""),
        _kpi(
            "production_escape_rate",
            "Escape para produção",
            percent(production, len(known_environment)),
            "percent",
            production,
            len(known_environment),
            "production / known_environment × 100",
            "Ambiente desconhecido é excluído do denominador.",
        ),
        _kpi(
            "reopen_rate",
            "Taxa de reabertura",
            percent(reopened, len(known_reopened)),
            "percent",
            reopened,
            len(known_reopened),
            "reopened / known_reopened × 100",
            "Bugs sem indicador de reabertura são excluídos.",
        ),
        _kpi(
            "mttd_hours",
            "MTTD",
            round(mean(mttd), 1) if mttd else None,
            "hours",
            round(sum(mttd), 1) if mttd else None,
            len(mttd),
            "mean(detected_at - created_at)",
            "Somente pares de datas válidos e não negativos.",
        ),
        _kpi(
            "mttr_hours",
            "MTTR",
            round(mean(mttr), 1) if mttr else None,
            "hours",
            round(sum(mttr), 1) if mttr else None,
            len(mttr),
            "mean(resolved_at - created_at)",
            "Somente pares de datas válidos e não negativos.",
        ),
        _kpi(
            "causal_coverage_rate",
            "Cobertura causal",
            percent(causal, total),
            "percent",
            causal,
            total,
            "bugs_with_qa_or_dev_notes / total × 100",
            "Nota disponível não equivale a evidência causal confirmada.",
        ),
        _kpi(
            "high_severity_share",
            "Carga de alta criticidade",
            percent(high_severity, total),
            "percent",
            high_severity,
            total,
            "(critical + high) / total × 100",
            "Usa a severidade reportada ou normalizada; não reflete impacto financeiro.",
        ),
        _kpi(
            "critical_bug_count",
            "Bugs críticos",
            critical,
            "count",
            critical,
            total,
            "count(severity = critical)",
            "Contagem absoluta; deve ser lida junto da amostra total.",
        ),
        _kpi(
            "top_module_share",
            "Concentração no módulo líder",
            percent(top_module_count, total),
            "percent",
            top_module_count,
            total,
            "top_module_count / total × 100",
            "Não distingue incidentes correlatos de incidentes independentes no mesmo módulo.",
        ),
        _kpi(
            "top_bug_type_share",
            "Bug type dominante",
            percent(top_type_count, total),
            "percent",
            top_type_count,
            total,
            "top_bug_type_count / total × 100",
            "Concentração alta sugere padrão, mas não prova mecanismo comum.",
        ),
        _kpi(
            "top_root_cause_share",
            "Sinal RCA dominante",
            percent(top_root_cause_count, total),
            "percent",
            top_root_cause_count,
            total,
            "top_root_cause_count / total × 100",
            "Categoria reportada é sinal de triagem e pode conter viés de classificação.",
        ),
    ]
    _enrich_kpis(
        kpis,
        bugs,
        top_module=top_module,
        top_type=top_type,
        top_root_cause=top_root_cause,
    )
    cross = {
        "severity_by_bug_type": _cross_tab(bugs, "bug_type", "severity"),
        "root_cause_by_bug_type": _cross_tab(bugs, "bug_type", "root_cause_category"),
        "bug_type_by_root_cause": _cross_tab(bugs, "root_cause_category", "bug_type"),
        "severity_by_root_cause": _cross_tab(bugs, "root_cause_category", "severity"),
        "environment_by_module": _cross_tab(bugs, "affected_module", "environment"),
        "severity_by_module": _cross_tab(bugs, "affected_module", "severity"),
        "team_by_root_cause": _cross_tab(bugs, "root_cause_category", "team"),
    }
    return {
        "kpis": kpis,
        "distributions": {
            field: _distribution(bugs, field)
            for field in (
                "severity",
                "environment",
                "affected_module",
                "bug_type",
                "root_cause_category",
                "team",
                "version",
            )
        },
        "cross_tabs": cross,
        "timelines": {
            "created_by_day": _date_distribution(bugs, "created_at"),
            "detected_by_day": _date_distribution(bugs, "detected_at"),
            "resolved_by_day": _date_distribution(bugs, "resolved_at"),
        },
        "note_terms": {
            "qa_dev": _top_note_terms(bugs, ("qa_analysis_notes", "dev_analysis_notes")),
            "qa": _top_note_terms(bugs, ("qa_analysis_notes",)),
            "dev": _top_note_terms(bugs, ("dev_analysis_notes",)),
        },
        "highlights": {
            "top_module": {"label": top_module, "count": top_module_count},
            "top_bug_type": {"label": top_type, "count": top_type_count},
            "top_root_cause": {"label": top_root_cause, "count": top_root_cause_count},
            "production": {"count": production, "total": len(known_environment)},
            "reopened": {"count": reopened, "total": len(known_reopened)},
        },
        "root_cause_profiles": _root_cause_profiles(bugs, total),
        "cross_tab_meta": {
            "severity_by_bug_type": {
                "label": "Severidade por bug type",
                "row_label": "Bug type",
                "column_label": "Severidade",
            },
            "root_cause_by_bug_type": {
                "label": "Sinal RCA por bug type",
                "row_label": "Bug type",
                "column_label": "Categoria RCA",
            },
            "bug_type_by_root_cause": {
                "label": "Tipos de bug por sinal RCA",
                "row_label": "Categoria RCA",
                "column_label": "Bug type",
            },
            "severity_by_root_cause": {
                "label": "Criticidade por sinal RCA",
                "row_label": "Categoria RCA",
                "column_label": "Severidade",
            },
            "environment_by_module": {
                "label": "Ambiente por módulo",
                "row_label": "Módulo",
                "column_label": "Ambiente",
            },
            "severity_by_module": {
                "label": "Severidade por módulo",
                "row_label": "Módulo",
                "column_label": "Severidade",
            },
            "team_by_root_cause": {
                "label": "Time por sinal RCA",
                "row_label": "Categoria RCA",
                "column_label": "Time",
            },
        },
    }
