from rca_agent.core.root_causes import resolve_root_cause
from rca_agent.reporting.common import _cause_display_name


def test_company_specific_root_cause_is_preserved_without_unknown_fallback():
    cause = "Erro/Falta de Requisito"

    resolved = resolve_root_cause(cause)

    assert resolved["matched_catalog"] is False
    assert resolved["display_name"] == cause
    assert _cause_display_name(cause) == cause


def test_configured_root_cause_still_uses_canonical_display_name():
    resolved = resolve_root_cause("implementation")

    assert resolved["matched_catalog"] is True
    assert resolved["canonical_key"] == "implementation"
    assert resolved["display_name"] == "Falha de implementação"
