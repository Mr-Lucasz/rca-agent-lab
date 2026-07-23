---
name: analyze-rca
description: Orquestrar uma análise de causa raiz completa e auditável a partir de CSV, XLSX, JSON ou bug individual. Usar quando o usuário fornecer um caminho e pedir RCA, análise de bugs, clusters, hipóteses, ações ou dashboard HTML.
---

# Analisar RCA

1. Ler `AGENTS.md` e executar `prepare`.
2. Usar as skills de normalização, triagem, métricas, padrões, hipóteses e ações nessa ordem.
3. Ler `analysis.json`; nunca recalcular números no texto.
4. Copiar o template para `agent-review.json` e editar apenas o novo arquivo.
5. Adicionar somente evidências reais com referência reproduzível.
6. Executar `finalize` e depois `validate`.
7. Se o review não puder ser sustentado, usar o baseline `rules` e declarar a limitação.
8. Entregar somente `bugs-normalized.csv`, `rca-report.html` e limitações relevantes.

Não alterar a entrada, não sobrescrever valores reportados e não afirmar causalidade sem confirmação humana.

