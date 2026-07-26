---
name: review-bug-triage
description: Revisar severidade, bug type, módulo e categoria RCA de bugs normalizados. Usar após normalização quando um bug ou conjunto precisar de triagem sem sobrescrever valores reportados.
---

# Revisar triagem

Cruzar título, descrição, esperado, obtido, ambiente e notas. Comparar severidade, `bug_type` e `root_cause_category` reportados. Registrar sugestões somente em `triage` de `agent-review.json`, com confiança, racional e um status: `consistent`, `questionable`, `unsupported`, `conflicting` ou `insufficient_evidence`.

Categoria RCA reportada é sinal, não causalidade confirmada.

Notas QA/Dev são sinais causais reportados. Separar trecho observacional de interpretação e hipótese causal, registrar como `reported_causal_signal` e manter confiabilidade `unassessed` e status `unverified` até avaliação. Preservar o conteúdo para síntese com notas de outros bugs e com os demais indicadores.

Quando `clarification-questions.json` contiver perguntas abertas, agrupá-las para o usuário e pausar o RCA. Para mapeamentos de schema, mostrar coluna original, campo proposto, método, score e alternativas. Para sugestões semânticas, explicar proposta, confiança e racional. Aceitação alimenta somente `effective_*` e `agent_suggested_*`; nunca sobrescrever o valor reportado. Categoria RCA aprovada continua sendo sinal de triagem. Ambiente, módulo e outros fatos ausentes devem ser perguntados, não inferidos. Continuar apenas após resposta, autorização ou recusa explícita registrada.

