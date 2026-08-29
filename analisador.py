import requests
import re
from config import *

# ----------------------
# Buscar dados da API
# ----------------------
headers = {
    "x-rapidapi-key": API_FOOTBALL_KEY,
    "x-rapidapi-host": API_FOOTBALL_HOST
}

def buscar_time(nome_time):
    """Busca estatísticas do time na API-Football"""
    try:
        url_busca = f"https://{API_FOOTBALL_HOST}/teams?search={nome_time}&season={TEMPORADA}"
        resp = requests.get(url_busca, headers=headers, timeout=10).json()
        
        if not resp["response"]:
            return None
        
        time = resp["response"][0]
        time_id = time["team"]["id"]
        liga_id = time["league"]["id"]
        
        url_stats = f"https://{API_FOOTBALL_HOST}/teams/statistics?league={liga_id}&season={TEMPORADA}&team={time_id}"
        stats = requests.get(url_stats, headers=headers, timeout=10).json()["response"]
        
        jogos = stats["fixtures"]["played"]["total"]
        if jogos < 3:
            return None
        
        chutes_total = stats["shots"]["total"]
        chutes_gol_total = stats["shots"]["onTarget"]
        
        return {
            "nome": time["team"]["name"],
            "chutes": round(chutes_total / jogos, 1),
            "chutes_gol": round(chutes_gol_total / jogos, 1),
            "liga": stats["league"]["name"],
            "pais": stats["league"]["country"]
        }
    except Exception as e:
        print(f"Erro em {nome_time}: {e}")
        return None

# ----------------------
# Banco de dados fallback
# ----------------------
BANCO_LOCAL = {
    "Tottenham": {"chutes":13.8, "chutes_gol":5.2, "liga":"Premier League"},
    "Newcastle": {"chutes":12.1, "chutes_gol":4.7, "liga":"Premier League"},
    "Fiorentina": {"chutes":14.2, "chutes_gol":5.4, "liga":"Serie A"},
    "Frosinone": {"chutes":11.0, "chutes_gol":4.1, "liga":"Serie A"},
    "Monza": {"chutes":11.3, "chutes_gol":4.3, "liga":"Serie A"},
    "Udinese": {"chutes":11.8, "chutes_gol":4.6, "liga":"Serie A"},
    "Borussia Dortmund": {"chutes":15.2, "chutes_gol":5.8, "liga":"Bundesliga"},
    "Hamburgo": {"chutes":10.4, "chutes_gol":3.9, "liga":"Bundesliga"},
    "Real Sociedad": {"chutes":14.7, "chutes_gol":5.5, "liga":"La Liga"},
    "Espanhol": {"chutes":11.2, "chutes_gol":4.0, "liga":"La Liga"},
    "Espanyol": {"chutes":11.2, "chutes_gol":4.0, "liga":"La Liga"},
    "Dortmund": {"chutes":15.2, "chutes_gol":5.8, "liga":"Bundesliga"}
}

def buscar_com_fallback(nome_time):
    """Tenta API, senão usa banco local"""
    dados = buscar_time(nome_time)
    if dados:
        dados["origem"] = "API"
        return dados
    
    if nome_time in BANCO_LOCAL:
        return {**BANCO_LOCAL[nome_time], "origem": "Local"}
    for chave in BANCO_LOCAL:
        if nome_time.lower() in chave.lower() or chave.lower() in nome_time.lower():
            return {**BANCO_LOCAL[chave], "origem": "Local"}
    
    return {"chutes":12.0, "chutes_gol":4.5, "liga":"Média", "origem":"Padrão"}

# ----------------------
# Extrair jogos do texto
# ----------------------
def extrair_jogos(texto):
    """Extrai TODOS os confrontos no formato 'Time A x Time B'"""
    jogos = []
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    re_jogo = re.compile(r"^(.+?)\s+x\s+(.+)$", re.I)
    
    for linha in linhas:
        m_jogo = re_jogo.match(linha)
        if m_jogo and not re.search(r"Chutes|Menos|Mais|Odd|Odds|Casa|Empate|Visita", linha, re.I):
            casa = m_jogo.group(1).strip()
            fora = m_jogo.group(2).strip()
            # Limpar possíveis números ou símbolos no final dos nomes
            casa = re.sub(r"[\d@#$%&*]+$", "", casa).strip()
            fora = re.sub(r"[\d@#$%&*]+$", "", fora).strip()
            if casa and fora:
                jogos.append({"casa": casa, "fora": fora})
    return jogos

# ----------------------
# Ajuste casa/fora
# ----------------------
def ajustar(valor, eh_casa):
    return round(valor * (AJUSTE_CASA if eh_casa else AJUSTE_FORA), 1)

# ----------------------
# Analisar confronto completo
# ----------------------
def analisar_confronto(casa, fora):
    """
    Analisa um confronto baseado APENAS nas médias estatísticas,
    ignorando completamente odds.
    """
    # Médias ajustadas
    chutes_casa = ajustar(casa["chutes"], True)
    chutes_fora = ajustar(fora["chutes"], False)
    gol_casa = ajustar(casa["chutes_gol"], True)
    gol_fora = ajustar(fora["chutes_gol"], False)
    
    # Totais esperados
    chutes_esperado = round(chutes_casa + chutes_fora, 1)
    gol_esperado = round(gol_casa + gol_fora, 1)
    
    # Valores de referência (médias globais do futebol)
    REF_CHUTES = 22.0    # Média global de chutes totais por jogo
    REF_GOL = 8.5        # Média global de chutes ao gol por jogo
    
    # Análise de tendência para CHUTES
    dif_chutes = chutes_esperado - REF_CHUTES
    if dif_chutes > 3:
        tend_chutes = {"icone": "📈", "texto": "FORTE TENDÊNCIA PARA MAIS", "resumo": "MAIS (forte)"}
        conf_chutes = "Alta"
    elif dif_chutes > 1:
        tend_chutes = {"icone": "⬆️", "texto": "Tendência para MAIS", "resumo": "MAIS"}
        conf_chutes = "Média"
    elif dif_chutes < -3:
        tend_chutes = {"icone": "📉", "texto": "FORTE TENDÊNCIA PARA MENOS", "resumo": "MENOS (forte)"}
        conf_chutes = "Alta"
    elif dif_chutes < -1:
        tend_chutes = {"icone": "⬇️", "texto": "Tendência para MENOS", "resumo": "MENOS"}
        conf_chutes = "Média"
    else:
        tend_chutes = {"icone": "➖", "texto": "Média equilibrada — sem tendência clara", "resumo": "Neutro"}
        conf_chutes = "Baixa"
    
    # Análise de tendência para CHUTES AO GOL
    dif_gol = gol_esperado - REF_GOL
    if dif_gol > 1.5:
        tend_gol = {"icone": "🎯", "texto": "FORTE TENDÊNCIA PARA MAIS", "resumo": "MAIS (forte)"}
        conf_gol = "Alta"
    elif dif_gol > 0.5:
        tend_gol = {"icone": "⬆️", "texto": "Tendência para MAIS", "resumo": "MAIS"}
        conf_gol = "Média"
    elif dif_gol < -1.5:
        tend_gol = {"icone": "🛡️", "texto": "FORTE TENDÊNCIA PARA MENOS", "resumo": "MENOS (forte)"}
        conf_gol = "Alta"
    elif dif_gol < -0.5:
        tend_gol = {"icone": "⬇️", "texto": "Tendência para MENOS", "resumo": "MENOS"}
        conf_gol = "Média"
    else:
        tend_gol = {"icone": "➖", "texto": "Média equilibrada — sem tendência clara", "resumo": "Neutro"}
        conf_gol = "Baixa"
    
    # Conclusão geral
    conclusao = f"Este confronto tem média projetada de {chutes_esperado} chutes ({tend_chutes['resumo']}) e {gol_esperado} chutes ao gol ({tend_gol['resumo']})."
    
    return {
        "chutes_esperado": chutes_esperado,
        "gol_esperado": gol_esperado,
        "ref_chutes": REF_CHUTES,
        "ref_gol": REF_GOL,
        "tendencia_chutes": tend_chutes,
        "tendencia_gol": tend_gol,
        "confianca_chutes": conf_chutes,
        "confianca_gol": conf_gol,
        "conclusao": conclusao
    }
