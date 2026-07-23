import csv
import json
from pathlib import Path
from uuid import uuid4

from rca_agent.pipeline import analyze, prepare, report_bug, validate_report
from rca_agent.reporting import write_html


ROOT = Path(__file__).resolve().parents[1]


def test_rules_pipeline_generates_two_auditable_outputs():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    result = analyze(ROOT / "data" / "input" / "bugs-demo.csv", output)

    assert Path(result["csv"]).exists()
    assert Path(result["html"]).exists()
    assert result["quality_gate"]["status"] == "passed"

    with Path(result["csv"]).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 12
    assert all(row["source_row"] for row in rows)
    assert all(row["requires_human_review"] == "true" for row in rows)

    html = Path(result["html"]).read_text(encoding="utf-8")
    for section in (
        "Resumo executivo",
        "KPIs principais",
        "Análise detalhada dos KPIs",
        "Distribuição geral de bugs",
        "Análise de causa raiz",
        "Palavras-chave nas análises de causa raiz",
        "Clusters, hipóteses e barreiras",
        "Auditoria e rastreabilidade",
    ):
        assert section in html
    assert "plotly.js" in html
    assert '<script id="rca-analysis" type="application/json">' in html
    assert validate_report(result["html"])["status"] == "passed"


def test_prepare_creates_agent_review_surface():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    prepared = prepare(ROOT / "data" / "input" / "bugs-demo.csv", output)
    template = json.loads(Path(prepared["review_template"]).read_text(encoding="utf-8"))
    analysis = json.loads(Path(prepared["analysis"]).read_text(encoding="utf-8"))

    assert template["hypotheses"]
    assert "narrative" in template
    assert "kpi_reviews" in template["narrative"]
    assert analysis["narrative_inputs"]["kpi_briefs"]
    assert analysis["narrative_inputs"]["root_cause_briefs"]
    assert analysis["metadata"]["mode"] == "rules-baseline"
    assert all(
        {
            "definition",
            "insight",
            "detailed_analysis",
            "supporting_bug_ids",
            "requires_human_review",
        }
        <= set(item)
        for item in analysis["metrics"]["kpis"]
    )
    assert all(item["status"] == "requires_human_review" for item in template["hypotheses"])


def test_report_bug_generates_structured_outputs():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    source = output / "single-bug.json"
    output.mkdir(parents=True)
    source.write_text(
        json.dumps(
            {
                "id": "BUG-777",
                "titulo": "Webhook falha no retry",
                "severidade": "alta",
                "descricao": "Retry do webhook devolve 401 após expiração da sessão.",
                "comportamento_esperado": "O retry deve renovar a credencial.",
                "comportamento_obtido": "O segundo envio reutiliza token expirado.",
                "bug_type": "security",
                "causa_raiz": "implementation",
                "modulo": "autenticação",
                "ambiente": "produção",
                "notas_dev": "Token foi armazenado fora do ciclo de retry.",
                "notas_qa": "Cenário reproduzido após o TTL.",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = report_bug(source, output)

    assert Path(result["json"]).exists()
    assert Path(result["markdown"]).exists()
    markdown = Path(result["markdown"]).read_text(encoding="utf-8")
    assert "Webhook falha no retry" in markdown
    assert "Comportamento observado" in markdown


def test_write_html_repairs_common_corrupted_accent_tokens():
    output = ROOT / "reports" / "test-artifacts" / uuid4().hex
    prepared = prepare(ROOT / "data" / "input" / "bugs-demo.csv", output)
    analysis = json.loads(Path(prepared["analysis"]).read_text(encoding="utf-8"))
    analysis["narrative"] = {
        "headline": "Teste de valida??o",
        "executive_summary": "A an?lise n?o deve manter texto corrompido no relat?rio.",
        "key_findings": ["Identifica??o corrigida automaticamente."],
        "systemic_patterns": ["Recorr?ncia descrita com acentua??o corrigida."],
        "root_cause_reviews": [],
    }

    html_path = output / "accent-fix-report.html"
    write_html(html_path, analysis)
    html = html_path.read_text(encoding="utf-8")

    assert "análise" in html
    assert "não" in html
    assert "relatório" in html
    assert "validação" in html
    assert "an?lise" not in html
    assert "A an?lise n?o deve manter texto corrompido no relat?rio." not in html
    assert "valida??o" not in html
