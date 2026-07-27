# Fundamentos metodológicos

Este projeto separa algoritmo de decisão metodológica. O Python executa contratos; fórmulas, campos, limiares, pesos, limites de apresentação e políticas ficam em `config/`, com versão e validação. Isso não elimina constantes estruturais de software — nomes de campos, tipos e enums continuam no schema —, mas evita esconder julgamentos analíticos no código.

## Decisões aplicadas

| Tema | Contrato adotado | Limitação explícita |
|---|---|---|
| Duração de detecção | Duração reportada ou `detected_at - occurrence_started_at` | Criação do ticket não representa início da ocorrência |
| Resolução | `resolved_at - created_at` é tempo de ciclo do ticket | Não é chamado de MTTR de serviço |
| Notas QA/Dev | Sinais causais reportados; cobertura, recorrência, convergência e contexto são analisados | Presença ou repetição textual isolada não confirma mecanismo |
| Duplicidade | Família é sempre `candidate` | Similaridade não confirma duplicidade |
| Clustering | Jaccard configurado com ligação completa e casos limítrofes | Sem base rotulada, confiança é `unvalidated` |
| Hipótese causal | Evidência, contraevidência, lacunas e teste falsificável | Permanece `requires_human_review` |
| Retrabalho | Estimativa opcional com método, evidências e suposições | Severidade e frequência não são convertidas em horas |
| Ações | Tipos e quantidade dependem do mecanismo | Não existe obrigação automática de três ações |

## Relação com a literatura

- Validação de clusters deve distinguir validação interna, externa, estabilidade e replicação em dados separados. Por isso o sistema não converte tamanho de cluster em confiança e registra o estado como não calibrado: [Ullmann, Hennig e Boulesteix, 2022](https://arxiv.org/abs/2103.01281).
- A literatura clássica descreve clustering como uma família de métodos dependentes de representação, medida de similaridade e critério de ligação; esses elementos precisam estar explícitos e avaliados no domínio: [Jain, Murty e Flynn, 1999](https://doi.org/10.1145/331499.331504).
- Identificar mecanismo causal exige desenho e suposições adicionais; associação textual ou coocorrência não identifica o processo causal. Isso sustenta contraevidência, teste falsificável e revisão humana: [Imai, Tingley e Yamamoto, 2013](https://doi.org/10.1111/j.1467-985X.2012.01032.x).
- Estudos empíricos de bug reports destacam passos de reprodução, stack traces e casos de teste como informações úteis. A skill de bug report agora solicita esses artefatos sem inventá-los: [Bettenburg et al., 2008](https://doi.org/10.1145/1453101.1453146).
- Texto de bug reports contém informação útil para levantar categorias de causa, mas não entrega classificação perfeita: Hirsch e Hofer obtiveram precisão média de 0,74 e recall de 0,72 em um benchmark rotulado a partir de 103 projetos. Isso sustenta usar notas como sinal causal, mantendo validação humana e técnica: [Hirsch e Hofer, 2021](https://arxiv.org/abs/2103.02372).
- Um estudo misto com entrevistas, survey e mineração de 250 repositórios mostrou que diferentes elementos do bug report têm utilidade e efeitos distintos no processo de debugging. Portanto, cobertura mede disponibilidade; a força precisa considerar conteúdo e contexto: [Soltani, Hermans e Bäck, 2020](https://doi.org/10.1007/s10664-020-09882-z).
- A integração de evidências qualitativas e quantitativas deve registrar convergência, complementaridade e divergência. Convergência entre resultados independentes aumenta credibilidade, mas continua sendo uma avaliação de grau que precisa de justificativa explícita: [Morgan, 2019](https://doi.org/10.1177/1558689818780596) e [Farmer et al., 2006](https://doi.org/10.1177/1049732305285708).
- A literatura de Defect Causal Analysis recomenda analisar tipos recorrentes de defeito para identificar causas associadas e oportunidades preventivas, mantendo o processo auditável e apoiado em evidências: [Kalinowski, Travassos e Card, 2008](https://www-di.inf.puc-rio.br/~kalinowski/publications/KalinowskiTC08b.pdf).
- Na prática de SRE, recuperação se refere à restauração operacional, e métricas médias de incidente podem ser inadequadas para decisão quando distribuições e amostras não são tratadas. Isso sustenta a separação entre ciclo do ticket e recuperação de serviço: [Google SRE — Incident Metrics](https://sre.google/resources/practices-and-processes/incident-metrics-in-sre/) e [Google SRE — Managing Incidents](https://sre.google/sre-book/managing-incidents/).

## O que ainda precisa de validação local

Os valores atuais de `config/clustering.yml` e `config/schema-mapping.yml` são hipóteses operacionais não calibradas. Antes de promover confiança, a organização deve criar amostra rotulada, medir precisão/recall, estabilidade e erros por segmento, e versionar os parâmetros resultantes. Até lá, o sistema gera candidatos para revisão, não decisões automáticas.

Notas QA/Dev e categorias RCA reportadas não participam da similaridade textual que gera candidatos a duplicidade. Em uma camada semântica separada, todas as notas são analisadas como sinais causais: mecanismos recorrentes, convergência ou divergência entre QA e Dev, especificidade técnica, contraexemplos e coerência com bug type, severidade, módulo, ambiente, versão, time e sinal RCA. Essa separação evita o raciocínio circular de usar uma causa reportada para formar o grupo e depois tratar o próprio grupo como confirmação.

Convergência entre bugs e fontes independentes pode elevar uma hipótese a forte indicativo mesmo antes de existir log, teste ou trace disponível. O estado continua `unverified` e `requires_human_review`; confiança causal alta e causa confirmada continuam exigindo validação reproduzível.
