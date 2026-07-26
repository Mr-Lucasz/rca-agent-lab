# RCA Agent Lab

Um agente orquestrador e um conjunto de skills para transformar bugs em um RCA por cluster, rastreável da linha de origem até o controle recomendado. O usuário fornece um arquivo; o agente devolve um CSV normalizado e um dashboard HTML autocontido.

```mermaid
flowchart TD
    A["Entrada: CSV, XLSX, JSON ou bug"] --> B["Validação e normalização"]
    B --> C["Revisão e classificação"]
    C --> D["Métricas com denominadores"]
    D --> E["Candidatos a duplicidade e clusters"]
    E --> F["Hipóteses causais auditáveis"]
    F --> G["Controles adequados ao mecanismo"]
    G --> H["Quality gate"]
    H --> I["CSV normalizado + HTML autocontido"]
```

## Por que um agente e várias skills

Métricas, parsing e HTML são determinísticos e testáveis; não ganham qualidade por virarem “agentes”. O orquestrador usa skills onde contexto e julgamento importam: revisar classificação, relacionar evidências, testar hipóteses e criar ações específicas.

## Uso direto, sem LLM

```bash
    G --> H["Quality gate"]
    H --> I["CSV normalizado + HTML autocontido"]
```

## Por que um agente e várias skills

Métricas, parsing e HTML são determinísticos e testáveis; não ganham qualidade por virarem “agentes”. O orquestrador usa skills onde contexto e julgamento importam: revisar classificação, relacionar evidências, testar hipóteses e criar ações específicas.

## Uso direto, sem LLM

```bash
python -m pip install -e ".[dev]"
npm run rca -- analyze data/input/bugs-demo.csv --output reports/demo
```

Saída: `reports/demo/bugs-normalized.csv` e `reports/demo/rca-report.html`.

## Para a Comunidade de QA 🚀

Este projeto foi desenhado pensando na comunidade de Qualidade de Software (QA). A triagem de bugs não precisa ser um processo manual doloroso. O RCA Agent Lab permite que equipes de QA escalem a análise de causa raiz, transformando planilhas de bugs em relatórios acionáveis para a engenharia, identificando rapidamente gargalos de arquitetura e dívidas técnicas, como falta de *shift-left* em testes.

### Compatibilidade Multi-Agente

O fluxo de orquestração do RCA Agent Lab, baseado em *skills* e diretrizes (`AGENTS.md`), é **100% compatível** com os principais assistentes de IA do mercado. Você pode rodar a análise semântica e conduzir o fluxo usando o seu agente favorito:

- **Antigravity (Google)**
- **GitHub Copilot**
- **Cursor**
- **Claude (Anthropic)**
- **Codex (OpenAI)**

Basta apontar o seu agente para a pasta do projeto e pedir: *"Analise `dados.csv` e gere o RCA HTML"*. O agente lerá as instruções do `AGENTS.md` e as *skills* em `.agents/skills` para orquestrar o processo completo.

## Uso com Codex ou Antigravity

```text
Use a skill analyze-rca para analisar C:\dados\bugs.xlsx e gerar o RCA HTML.
```

O `AGENTS.md` conduz `prepare → revisão semântica → finalize → validate`.

## Uso com GitHub Copilot / Cursor / Claude

No Copilot, selecione o agente `rca-orchestrator` em `.github/agents/rca-orchestrator.agent.md`. No Cursor ou Claude, basta abrir o diretório. Envie o prompt:

```text
Analise ./data/input/bugs-demo.csv e gere o relatório RCA.
```

As skills ficam em `.agents/skills`, localização padronizada para os ambientes.

## Modos

```bash
npm run rca -- report-bug --input evidence.json --output reports/bug
npm run rca -- prepare data/bugs.xlsx --output reports/run
npm run rca -- review-questions --work .rca-work/<run> --review agent-review.json
npm run rca -- finalize --work .rca-work/<run> --review agent-review.json --output reports/run
npm run rca -- analyze data/bugs.xlsx --output reports/run --mode rules
npm run rca -- validate reports/run/rca-report.html
```

`rules` produz somente uma linha de base factual, offline e reproduzível: dados normalizados, métricas, distribuições, clusters e evidências extraídas. Esse modo não escreve insights, hipóteses, mecanismos nem ações. No fluxo agentic, o modelo escreve essas interpretações somente em `agent-review.json`; números, renderização e quality gate continuam no núcleo Python.

As decisões metodológicas não ficam escondidas no código. Definições de KPI, fontes de duração, limiares e pesos de clustering, regras de confiança, confiabilidade inicial de evidências, mapeamento de schema e política de ações ficam em arquivos versionados de `config/`. Configuração ausente ou inválida bloqueia o cálculo correspondente; não há fallback analítico improvisado.

Depois que o agente preencher as sugestões de triagem, `review-questions` converte essas sugestões em perguntas auditáveis. O dashboard final continua bloqueado até o humano aceitar, responder ou recusar cada pergunta.

## Rastreabilidade

O HTML contém cards de KPI e uma seção detalhada para **cada indicador** com definição, fórmula, denominador, bugs de apoio e limitações. Insights e análises aparecem somente quando foram fornecidos pela revisão semântica. Também inclui gráficos Plotly autocontidos para evolução, severidade, tipo, ambiente, módulo, sinais RCA, cruzamentos, palavras-chave e clusters.

`detection_lead_time_hours` exige duração reportada ou início observável da ocorrência. `resolved_at - created_at` é apresentado como tempo de resolução do ticket, não como MTTR de serviço. Notas QA/Dev geram o KPI configurado de cobertura de sinais causais e alimentam uma síntese sistêmica rastreável por bug, fonte e `evidence_id`. Recorrência, convergência entre fontes e coerência com os demais indicadores podem sustentar uma hipótese forte; a causa só é confirmada após validação reproduzível.

O agente pode escrever os textos de cada KPI por `narrative.kpi_reviews`; o núcleo determinístico nunca fornece uma interpretação de fallback. Métricas externas de codebase, CI, DORA ou observabilidade exigem evidências identificadas e não recebem valores fictícios.

Valores reportados são preservados. Sugestões do agente ficam em colunas próprias com confiança, racional e status de revisão.

A fundamentação e as limitações das escolhas estão em [docs/methodology.md](docs/methodology.md).

## Desenvolvimento

```bash
npm run demo
npm run check
```

Hipótese nunca é causa confirmada.
