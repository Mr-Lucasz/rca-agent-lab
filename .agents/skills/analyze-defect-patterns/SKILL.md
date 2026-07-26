---
name: analyze-defect-patterns
description: Analisar deduplicação, famílias de defeitos e clusters priorizados usando sinais textuais e operacionais. Usar depois das métricas para encontrar padrões sistêmicos.
---

# Analisar padrões

Começar pelos candidatos a família e clusters de `analysis.json` e conferir a metodologia registrada em `config/clustering.yml`.

- Verificar descrição, comportamento, módulo, ambiente e notas; não agrupar só por categoria RCA.
- Tratar notas QA/Dev como sinais causais reportados de primeira classe. Ler todas as notas expostas em `narrative_inputs.causal_signal_context`, preservando `bug_id`, `evidence_id`, fonte e status epistêmico.
- Sintetizar mecanismos recorrentes entre bugs, convergência e divergência entre QA/Dev, especificidade técnica, contradições e coocorrência com bug type, severidade, módulo, ambiente, versão, time e sinal RCA, conforme `config/descriptive-analysis.yml`.
- Um padrão convergente pode sustentar forte indicativo e priorizar hipótese causal. Não o apresentar como causa confirmada sem o teste exigido por `config/confidence-rules.yml`.
- Manter separadas a similaridade de sintomas usada para gerar famílias candidatas e a síntese semântica dos sinais causais. Uma nota isolada não confirma que dois tickets são duplicados; todas as notas ainda participam da análise sistêmica.
- Tratar `duplicate_candidate_family_id` como candidato a duplicidade, nunca como duplicidade confirmada.
- Não elevar confiança pelo tamanho do grupo. Sem avaliação rotulada, manter `cluster_confidence: unvalidated`.
- Examinar `boundary_cases`, conflitos e possível fragmentação antes de interpretar um cluster.
- Usar `priority_rank` somente para ordenar investigação. O score não mede probabilidade causal nem impacto financeiro.
- Registrar insights com evidências e limitações; não afirmar mecanismo compartilhado só pela similaridade.

