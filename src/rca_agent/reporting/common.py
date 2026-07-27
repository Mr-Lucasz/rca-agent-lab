from __future__ import annotations

import html
import re
from typing import Any

from ..core.config import load_yaml
from ..core.root_causes import resolve_root_cause

FIELD_LABELS = {
    "severity": "Severidade",
    "environment": "Ambiente",
    "affected_module": "Módulo",
    "bug_type": "Tipo do defeito",
    "root_cause_category": "Categoria RCA reportada",
    "team": "Time",
    "version": "Versão",
}

VALUE_LABELS = {
    "critical": "Crítica",
    "high": "Alta",
    "medium": "Média",
    "low": "Baixa",
    "production": "Produção",
    "staging": "Staging",
    "qa": "QA",
    "unknown": "Não informado",
    "true": "Sim",
    "false": "Não",
}

# Defensive fixes for corrupted text fragments that can appear when review text
# was authored with a mismatched terminal/code-page encoding.
_TEXT_FIXUPS = {
    "Ap?s": "Após",
    "Identifica??o": "Identificação",
    "identifica??o": "identificação",
    "Oscila??o": "Oscilação",
    "Predom?nio": "Predomínio",
    "Recorr?ncia": "Recorrência",
    "a??es": "ações",
    "an?lise": "análise",
    "ass?ncrono": "assíncrono",
    "can?nica": "canônica",
    "cen?rios": "cenários",
    "confian?a": "confiança",
    "corre??es": "correções",
    "cr?tico": "crítico",
    "degrada??o": "degradação",
    "espec?ficos": "específicos",
    "evid?ncia": "evidência",
    "evid?ncias": "evidências",
    "execu??o": "execução",
    "experi?ncia": "experiência",
    "fam?lia": "família",
    "hip?teses": "hipóteses",
    "implementa??o": "implementação",
    "integra??o": "integração",
    "interrup??o": "interrupção",
    "investiga??o": "investigação",
    "m?dulos": "módulos",
    "n?o": "não",
    "normaliza??o": "normalização",
    "padr?o": "padrão",
    "pol?tica": "política",
    "por?m": "porém",
    "priorit?rios": "prioritários",
    "prioriza??o": "priorização",
    "prov?vel": "provável",
    "re?ne": "reúne",
    "recorr?ncia": "recorrência",
    "reincid?ncia": "reincidência",
    "relat?rio": "relatório",
    "renderiza??o": "renderização",
    "repeti??o": "repetição",
    "revis?o": "revisão",
    "s?o": "são",
    "seguran?a": "segurança",
    "sem?ntica": "semântica",
    "sincroniza??o": "sincronização",
    "t?cnicas": "técnicas",
    "transi??o": "transição",
    "valida??es": "validações",
    "valida??o": "validação",
}


def _repair_text(value: Any) -> str:
    text = str(value)
    # Common mojibake path: UTF-8 bytes interpreted as Latin-1.
    if any(marker in text for marker in ("Ã", "â", "€", "™")):
        try:
            text = text.encode("latin-1").decode("utf-8")
        except UnicodeError:
            pass
    if "?" in text:
        for broken, fixed in _TEXT_FIXUPS.items():
            text = text.replace(broken, fixed)
        # Preserve intentional question marks and only flag suspicious leftovers.
        if "??" in text:
            text = re.sub(r"\?{2,}", "?", text)
    return text


def _repair_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _repair_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_repair_structure(item) for item in value]
    if isinstance(value, str):
        return _repair_text(value)
    return value


def _root_cause_catalog() -> dict[str, Any]:
    return load_yaml("root-causes.yml").get("canonical", {})


def _escape(value: Any) -> str:
    return html.escape(_repair_text(value), quote=True)


def _display(value: Any, unit: str = "") -> str:
    if value is None:
        return "N/D"
    if unit == "percent":
        return f"{value}%"
    if unit == "hours":
        return f"{value} h"
    return _repair_text(value)


def _pretty(value: Any) -> str:
    text = str(value)
    return VALUE_LABELS.get(text, text.replace("_", " ").replace("-", " ").title())


def _cause_display_name(cause: str) -> str:
    return str(resolve_root_cause(cause, _root_cause_catalog())["display_name"])


def _summary_sentence(analysis: dict[str, Any]) -> str:
    narrative = analysis.get("narrative", {})
    if narrative.get("executive_summary"):
        return str(narrative["executive_summary"])
    profiles = analysis["metrics"].get("root_cause_profiles", [])
    total = len(analysis["bugs"])
    if not profiles:
        return (
            f"A amostra tem {total} bugs e não possui contagem disponível "
            "de categorias RCA reportadas."
        )
    first = profiles[0]
    second = profiles[1] if len(profiles) > 1 else None
    sentence = (
        f"A leitura geral mostra {total} bugs com concentração em {_cause_display_name(first['root_cause_category'])} "
        f"({first['count']} casos; {first['share_percent']}%)."
    )
    if second and second.get("share_percent"):
        sentence += f" O segundo bloco de peso está em {_cause_display_name(second['root_cause_category'])} ({second['count']} casos; {second['share_percent']}%)."
    return sentence


def _systemic_patterns(analysis: dict[str, Any]) -> list[str]:
    narrative = analysis.get("narrative", {})
    if narrative.get("systemic_patterns"):
        return list(narrative["systemic_patterns"])
    return []


def _causal_signal_audit(data_quality: dict[str, Any]) -> str:
    count = data_quality.get("records_with_causal_signals", 0)
    coverage = data_quality.get("causal_signal_coverage_percent", 0)
    return (
        f'{data_quality["usable_for_metrics"]} de '
        f'{data_quality["total_records"]} registros são utilizáveis para '
        f"métricas. {count} ({coverage}%) contêm sinais causais documentados "
        "em notas QA/Dev. Esses sinais são analisados em conjunto com "
        "recorrência, convergência entre fontes e coerência com os demais "
        "indicadores; sustentam hipóteses, mas não confirmam automaticamente "
        "a causa."
    )
