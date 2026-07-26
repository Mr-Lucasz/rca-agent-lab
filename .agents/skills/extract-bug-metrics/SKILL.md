---
name: extract-bug-metrics
description: Extrair e conferir KPIs de bugs com fórmula, numerador, denominador, amostra e limitações. Usar antes de interpretar tendências ou clusters.
---

# Extrair métricas

Usar `analysis.json` como fonte numérica e `config/kpis.yml` como contrato de definição. Conferir valor, fórmula, numerador, denominador, amostra, fontes efetivamente usadas e limitações.

- Chamar de `detection_lead_time_hours` apenas a duração reportada pela fonte ou `detected_at - occurrence_started_at`. Nunca usar criação do ticket como início da ocorrência.
- Chamar `resolved_at - created_at` de tempo de resolução do ticket, nunca de MTTR de serviço.
- Calcular `causal_signal_coverage_rate` conforme `config/kpis.yml`. Esse KPI mede disponibilidade de material causal reportado, não a qualidade ou confirmação da causa.
- Ler `metrics.causal_signal_patterns` para conferir recorrência, cobertura por fonte e distribuição dos bugs com notas nas dimensões configuradas. Frequência de palavras isolada não mede força causal.
- Se os campos exigidos não existirem, preservar `value: null`; não estimar nem substituir por proxy silencioso.
- Usar cruzamentos relevantes; não usar word cloud como evidência nem concluir tendência sem período e volume suficientes.

