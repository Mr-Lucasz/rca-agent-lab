# Webhook falha no retry

- **ID:** BUG-777
- **Severidade sugerida:** high
- **Bug type:** security
- **Módulo:** autenticação
- **Ambiente:** production
- **Versão:** Não informado
- **Time:** Não informado

## Descrição
Retry do webhook devolve 401 após expiração da sessão.

## Comportamento esperado
O retry deve renovar a credencial.

## Comportamento observado
O segundo envio reutiliza token expirado.

## Pré-condições
unknown

## Evidências e contexto
- **Notas de QA:** Cenário reproduzido após o TTL.
- **Notas de Dev:** Token foi armazenado fora do ciclo de retry.
- **Racional da sugestão:** Regras encontraram 2 sinal(is) textual(is); classificação reportada avaliada como consistent. Requer revisão humana.

## Observações
- Este artefato é um bug report padronizado para triagem. Não trata a categoria RCA como causa confirmada.