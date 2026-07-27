import json
import sys

def main():
    analysis_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\analysis.json"
    output_path = r"C:\Users\Acer\Documents\lab-lucas\rca-agent-lab\.rca-work\bugs-app-delivery-kpi-351d5db0b672\agent-review.json"

    with open(analysis_path, 'r', encoding='utf-8') as f:
        analysis = json.load(f)
        
    with open(output_path, 'r', encoding='utf-8') as f:
        review = json.load(f)

    # 1. Insights
    review['insights'] = [
        {
            "insight_id": "IN-001",
            "statement": "Gestão de Pagamentos concentra bugs críticos de concorrência e timeout.",
            "evidence_ids": ["DELIV-1008", "DELIV-1013"],
            "limitations": ["Amostra limitada, requer análise de logs de rede do gateway."]
        },
        {
            "insight_id": "IN-002",
            "statement": "Falta de testes unitários de fronteira resulta em quebras visuais constantes.",
            "evidence_ids": ["DELIV-1003", "DELIV-1010"],
            "limitations": ["Apenas bugs reportados considerados, cobertura real de testes desconhecida."]
        }
    ]

    # 2. Hypotheses
    review['hypotheses'] = [
        {
            "hypothesis_id": "HY-001",
            "cluster_id": "CL-002",
            "statement": "Falta de idempotência no Redis e ausência de debounce causam múltiplas cobranças.",
            "mechanism": "O usuário clica repetidamente no botão e as requisições não são bloqueadas, sobrecarregando o gateway.",
            "confidence": "high",
            "confidence_rationale": "Notas do QA confirmam a reprodução do erro usando a ferramenta k6.",
            "supporting_evidence_ids": ["DELIV-1008", "DELIV-1013"],
            "counter_evidence_ids": [],
            "missing_information": ["Volume exato de requisições por segundo durante os incidentes"],
            "confirmation_questions": ["Podemos priorizar a implementação de idempotência?"],
            "validation_method": "Validar com k6 e verificar bloqueio após a primeira submissão.",
            "status": "requires_human_review"
        },
        {
            "hypothesis_id": "HY-002",
            "cluster_id": "CL-001",
            "statement": "Testes exploratórios manuais são insuficientes para prevenir quebras de layout em CSS Flexbox.",
            "mechanism": "Alterações no Tailwind afetam múltiplos componentes não cobertos por testes visuais automatizados.",
            "confidence": "medium",
            "confidence_rationale": "Notas indicam ajustes simples no Tailwind, sugerindo fragilidade no design system.",
            "supporting_evidence_ids": ["DELIV-1003", "DELIV-1010"],
            "counter_evidence_ids": [],
            "missing_information": ["Se existe algum pipeline de teste de regressão visual configurado"],
            "confirmation_questions": ["Existe budget para implementar Storybook ou Percy?"],
            "validation_method": "Executar testes visuais comparativos antes e depois das correções.",
            "status": "requires_human_review"
        }
    ]

    # 3. Actions
    review['actions'] = [
        {
            "action_id": "AC-001",
            "hypothesis_id": "HY-001",
            "cluster_id": "CL-002",
            "barrier_type": "preventive",
            "statement": "Implementar chave de idempotência com Redis no endpoint de pagamento.",
            "owner_role": "Backend",
            "horizon": "Curto Prazo",
            "priority": "high",
            "expected_impact": "high",
            "effort": "medium",
            "success_metric": "0% de falhas nos testes de estresse de pagamento",
            "validation_method": "Passar suite de testes K6 sem duplicidades",
            "residual_risk": "Pequeno, restrito a indisponibilidade total do Redis.",
            "evidence_ids": ["DELIV-1008", "DELIV-1013"],
            "status": "requires_human_review"
        },
        {
            "action_id": "AC-002",
            "hypothesis_id": "HY-002",
            "cluster_id": "CL-001",
            "barrier_type": "detective",
            "statement": "Integrar testes de regressão visual no CI/CD para o frontend.",
            "owner_role": "QA / Frontend",
            "horizon": "Médio Prazo",
            "priority": "medium",
            "expected_impact": "medium",
            "effort": "high",
            "success_metric": "Bloqueio automático de PRs com quebras visuais detectadas",
            "validation_method": "Forçar um erro visual e confirmar bloqueio no CI",
            "residual_risk": "Falsos positivos em testes visuais de pequenas mudanças autorizadas.",
            "evidence_ids": ["DELIV-1003", "DELIV-1010"],
            "status": "requires_human_review"
        }
    ]

    # 4. Narrative
    review['narrative'] = {
        "headline": "RCA: Problemas Críticos de Concorrência e Quebras de Layout em Produção",
        "executive_summary": "A análise revela que o sistema enfrenta problemas de race conditions no módulo de pagamentos, gerando duplicidade sob alta carga. Adicionalmente, há fragilidades na validação de layout, apontando ausência de testes unitários de fronteira automatizados.",
        "key_findings": [
            "Gestão de Pagamentos é o módulo de maior criticidade e reincidência.",
            "O uso de Flexbox sem cobertura de testes automatizados tem causado bugs de regressão visual."
        ],
        "systemic_patterns": [
            "Falta de idempotência no processamento de requisições críticas.",
            "Dependência excessiva de testes exploratórios manuais pelo QA."
        ],
        "root_cause_signal_reviews": [
            {
                "root_cause_category": "Condição de Corrida (Race Condition)",
                "signal_axis": "Processamento",
                "title": "Duplicidade de Cobranças",
                "summary": "O sistema não trava requisições repetidas via frontend ou backend durante picos.",
                "symptom_pattern": "Múltiplas cobranças no cartão do cliente no mesmo segundo.",
                "hypothesized_mechanism": "Falta de idempotência e debounce.",
                "business_impact": "Reclamações de clientes e estornos (chargebacks).",
                "persistence_hypothesis": "A arquitetura atual não implementa lock distribuído ou chaves de idempotência eficientes.",
                "evidence_ids": ["DELIV-1008", "DELIV-1013"]
            }
        ]
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(review, f, indent=2, ensure_ascii=False)
        
    print(f"agent-review.json populated with semantic RCA content.")

if __name__ == "__main__":
    main()
