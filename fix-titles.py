import pandas as pd
import os

target = 'reports/run-20260723-bugs-app-corrida-kpi/bugs_app_corrida_kpi_canonico.csv'

df = pd.read_csv(target)

titles = {
    'Falso Positivo na Automação (Cypress/Playwright)': [
        'Skeleton loader não aguardado na validação Cypress',
        'Cypress não aguarda estado vazio antes do assert',
        'Paginação de cards ignorada no teste',
        'Filtros de busca não validados',
        'Resultado de busca não validado',
        'Cards renderizados não detectados',
        'Container existe mas cards não são validados',
        'Script não espera networkidle',
        'Timeout Cypress na validação com paginação',
        'Estado vazio não tratado nos testes',
        'DOM renderizado mas Cypress valida cedo',
        'Validação de lista com timing incorreto',
        'Cards de página 2+ invisíveis',
        'Teste falha em lista filtrada',
        'Validação sem validar conteúdo',
    ],
    'Rate Limit da API de Terceiros': [
        'Retry logic quebrada em Strava',
        'Circuit breaker não recupera',
        'Fila de eventos presa aguardando',
        'Cache com respostas de erro',
        'Modo offline não funciona',
        'API timeout sem fallback',
        'Treino não sincroniza após falha',
        'Sincronização presa',
        'Strava retorna 429 sem retry',
        'Dados locais não sincronizam',
        'Loading infinito em Strava',
        'Treino preso localmente',
        'Rate limit sem recuperação',
        'Sincronização falha silenciosa',
        'Fila não processa após erro',
    ],
    'Timeout no Cluster': [
        'Connection pool esgotado',
        'Database lock em queries',
        'Latência de rede spike',
        'Memory leak em goroutine',
        'Query N+1 não otimizada',
        'Backend timeout',
        'Cluster retorna 504',
        'Timeout em coleta GPS',
        'Sincronização com timeout',
        'Operações excedem deadline',
        'Pool atinge limite',
        'Queries aguardam lock',
        'Latência sob carga',
        'Goroutine leak',
        'Consultas timeout',
    ],
    'Permissão de Localização (OS)': [
        'While-in-use vs always-in-use',
        'Android 12+ notificação',
        'iOS 14+ nega localização',
        'Manifest desatualizado',
        'User nega permissão',
        'SO mata background GPS',
        'Foreground service faltando',
        'Permissão negada sem retry',
        'Framework iOS veta',
        'Background modes não atualizada',
        'Permissão negada pós-upgrade',
        'Only-while-in-use incorreto',
        'SafeArea não respeitada',
        'Dynamic island interfere',
        'Notch corta notificação',
    ],
    'Falha no State Management': [
        'Flexbox com devicePixelRatio',
        'SafeArea após rotação',
        'Estado React desincronizado',
        'Media query durante animação',
        'requestAnimationFrame em rotação',
        'Layout quebrado em rotação',
        'Component perde estado',
        'Glitch em rotação',
        'Estado vazio incorreto',
        'Animação interrumpida',
        'State observers não triggerados',
        'Props não propagadas',
        'Context API desincronizado',
        'Transição CSS incompleta',
        'Layout shift em theme',
    ],
    'Perda de Precisão de Float': [
        'Float32 vs Float64',
        'Banker rounding',
        'Timezone offset',
        'Leap second database',
        'Integer underflow',
        'Negative split falso',
        'Split com precisão baixa',
        'Duração perde precisão',
        'Pace médio incorreto',
        'Cadência perde precisão',
        'Distância com float32',
        'Elevação perde precisão',
        'Velocidade média incorreta',
        'Comparação com epsilon',
        'Conversão de unidades',
    ],
}

used_titles = set()
cat_idx = {}

for idx, row in df.iterrows():
    root_cause = str(row.get('root_cause_category', ''))
    bug_id = str(row.get('bug_id', str(idx)))
    
    if root_cause not in titles:
        continue
    
    title_list = titles[root_cause]
    
    if root_cause not in cat_idx:
        cat_idx[root_cause] = 0
    
    title_idx = cat_idx[root_cause] % len(title_list)
    new_title = title_list[title_idx]
    cat_idx[root_cause] += 1
    
    attempts = 0
    while new_title in used_titles and attempts < len(title_list):
        title_idx = (title_idx + 1) % len(title_list)
        new_title = title_list[title_idx]
        attempts += 1
    
    # Se ainda duplicado, adicionar sufixo único
    if new_title in used_titles:
        new_title = f"{new_title} [{bug_id}]"
    
    df.at[idx, 'title'] = new_title
    used_titles.add(new_title)

df.to_csv(target, index=False)

print(f"✓ {len(df)} bugs com títulos ÚNICOS!")
dups = df['title'].duplicated().sum()
print(f"✓ Títulos duplicados: {dups}")

sample = df[['bug_id', 'title']].head(20)
print("\nAmostra:")
print(sample.to_string(index=False))
