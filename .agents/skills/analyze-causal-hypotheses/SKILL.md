---
name: analyze-causal-hypotheses
description: Formular hipóteses de mecanismo causal para clusters prioritários. Usar depois de triagem, métricas e padrões identificados. Exige evidências, contraevidências e testes falsificáveis; estimativas só entram quando têm base reproduzível.
---

# Analisar hipóteses causais

Distinguir claramente:
- **Sintoma** — o que é observado
- **Fator** — condição associada
- **Mecanismo** — como o fator produz o sintoma

Para cada hipótese prioritária:

1. Explicar o mecanismo de forma causal (como ele geraria os comportamentos observados).
2. Registrar:
   - Evidências favoráveis
   - Contraevidências
   - Informação ausente / lacunas
   - Alegações reportadas separadamente de artefatos corroboradores
3. Preencher `estimated_rework_hours` somente se houver dado de esforço ou modelo reproduzível. Nesse caso, preencher também `estimate_basis.method`, `estimate_basis.supporting_evidence_ids` e `estimate_basis.assumptions`. Frequência e severidade, isoladamente, não sustentam horas; sem base, omitir o campo ou usar `null`.
4. Classificar o nível de confiança seguindo obrigatoriamente `config/confidence-rules.yml`. Se a configuração estiver ausente ou inválida, interromper a revisão causal e expor a limitação.
5. Formular perguntas concretas e um método de validação falsificável.
6. Manter sempre `status: requires_human_review`.

**Regra crítica:** nunca afirmar que a causa está confirmada. Tratar tudo como hipótese até teste empírico e decisão humana.

Nota QA/Dev é `reported_causal_signal` com `epistemic_status: unverified` por padrão. Ela pode sustentar o mecanismo de uma hipótese, especialmente quando o mesmo mecanismo específico recorre em bugs distintos, converge entre QA/Dev e é coerente com comportamento, bug type, severidade, módulo, ambiente, versão, time e sinal RCA.

Classificar como sinal fraco uma nota isolada, genérica, contraditória ou possivelmente copiada. Classificar como forte indicativo uma convergência independente e tecnicamente específica, seguindo `config/confidence-rules.yml`. Artefatos como teste reproduzível, log, trace, observabilidade, código ou histórico de mudança fortalecem e podem validar a hipótese, mas sua ausência não impede formular uma hipótese causal de confiança média. Não contar a mesma nota como fontes independentes nem promover forte indicativo a causa confirmada.
