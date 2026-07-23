---
name: validate-rca-report
description: Aplicar o quality gate ao CSV normalizado e dashboard HTML RCA. Usar obrigatoriamente antes de entregar relatório ou ao revisar um existente.
---

# Validar relatório

Executar `npm run rca -- validate "<relatório.html>"`. Bloquear erro de contagem, denominador, referência, hipótese sem evidência, ação genérica ou causalidade indevida. Confirmar a cadeia bug-cluster-hipótese-ação e a mesma quantidade no CSV e HTML. Exibir limitações. Executar `npm run check` ao concluir alterações no repositório.
