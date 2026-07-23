from __future__ import annotations

from typing import Any

from .utils import UNKNOWN


def _line(label: str, value: Any) -> str:
    text = str(value) if value not in {None, "", UNKNOWN} else "Não informado"
    return f"- **{label}:** {text}"


def render_bug_markdown(bug: dict[str, Any]) -> str:
    severity = bug.get("agent_suggested_severity")
    severity_text = severity if severity != UNKNOWN else bug.get("severity", UNKNOWN)
    bug_type = bug.get("agent_suggested_bug_type")
    bug_type_text = bug_type if bug_type != UNKNOWN else bug.get("bug_type", UNKNOWN)
    return "\n".join(
        [
            f"# {bug.get('title', 'Bug sem título')}",
            "",
            _line("ID", bug.get("bug_id")),
            _line("Severidade sugerida", severity_text),
            _line("Tipo do defeito", bug_type_text),
            _line("Módulo", bug.get("affected_module")),
            _line("Ambiente", bug.get("environment")),
            _line("Versão", bug.get("version")),
            _line("Time", bug.get("team")),
            "",
            "## Descrição",
            str(bug.get("description", "Não informado")),
            "",
            "## Comportamento esperado",
            str(bug.get("expected_behavior", "Não informado")),
            "",
            "## Comportamento observado",
            str(bug.get("actual_behavior", "Não informado")),
            "",
            "## Pré-condições",
            str(bug.get("preconditions", "Não informado")),
            "",
            "## Evidências e contexto",
            _line("Notas de QA", bug.get("qa_analysis_notes")),
            _line("Notas de Dev", bug.get("dev_analysis_notes")),
            _line("Racional da sugestão", bug.get("agent_suggestion_rationale")),
            "",
            "## Observações",
            "- Este artefato é um bug report padronizado para triagem. Não trata a categoria RCA como causa confirmada.",
        ]
    )