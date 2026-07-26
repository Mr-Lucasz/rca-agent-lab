---
name: recommend-rca-actions
description: Recomendar ações RCA específicas, rastreáveis e mensuráveis a partir de hipóteses sustentadas. Usar após análise causal para selecionar controles adequados ao mecanismo e à evidência.
---

# Recomendar ações

Ler `config/action-policy.yml`. Para cada hipótese prioritária, selecionar somente os controles necessários entre `containment`, `corrective`, `detective` e `preventive`. Não criar uma ação de cada tipo por obrigação.

Cada ação deve informar hipótese, evidências, dono por papel, horizonte, prioridade, impacto esperado, esforço, métrica, validação e risco residual. A prioridade e o impacto são julgamentos revisáveis, não saídas automáticas do score do cluster.

Rejeitar ações genéricas, ações sem vínculo com o mecanismo e ações sem critério verificável.

