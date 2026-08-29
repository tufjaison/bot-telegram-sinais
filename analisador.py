import requests
from datetime import datetime
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
        # 1. Buscar ID do time
        url_busca = f"https://{API_FOOTBALL_HOST}/teams?search={nome_time}&season={TEMPORADA}"
        resp = requests.get(url_busca, headers=headers, timeout=10).json()
        
        if not resp["response"]:
            return None
        
        time = resp["response"][0]
        time_id = time["team"]["id"]
        liga_id = time["league"]["id"]
        
        # 2. Buscar estatísticas
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
    
    # Busca no banco local
    if nome_time in BANCO_LOCAL:
        return {**BANCO_LOCAL[nome_time], "origem": "Local"}
    for chave in BANCO_LOCAL:
        if nome_time.lower() in chave.lower() or chave.lower() in nome_time.lower():
            return {**BANCO_LOCAL[chave], "origem": "Local"}
    
    return {"chutes":12.0, "chutes_gol":4.5, "liga":"Média", "origem":"Padrão"}

# ----------------------
# Extrair jogos do texto
# ----------------------
import re
def extrair_jogos(texto):
    jogos = []
    linhas = [l.strip() for l in texto.split("\n") if l.strip()]
    re_jogo = re.compile(r"^(.+?)\s+x\s+(.+)$", re.I)
    re_linha = re.compile(r"(Menos|Mais)\s+de\s+([\d,.]+)\s+Chutes(?:\s+ao\s+Gol)?", re.I)
    
    jogo_atual = None
    for linha in linhas:
        m_jogo = re_jogo.match(linha)
        if m_jogo and not re.search(r"Chutes|Menos|Mais", linha, re.I):
            if jogo_atual: jogos.append(jogo_atual)
            jogo_atual = {
                "casa": m_jogo.group(1).strip(),
                "fora": m_jogo.group(2).strip(),
                "linha_chutes": None, "tipo_chutes": None,
                "linha_gol": None, "tipo_gol": None
            }
            continue
        m_linha = re_linha.match(linha)
        if m_linha and jogo_atual:
            tipo = m_linha.group(1).lower()
            valor = float(m_linha.group(2).replace(",", "."))
            if "ao Gol" in linha:
                jogo_atual["tipo_gol"] = tipo
                jogo_atual["linha_gol"] = valor
            else:
                jogo_atual["tipo_chutes"] = tipo
                jogo_atual["linha_chutes"] = valor
    if jogo_atual: jogos.append(jogo_atual)
    return jogos

# ----------------------
# Avaliar aposta
# ----------------------
def avaliar(valor_esperado, linha, tipo_oferecido):
    diferenca = valor_esperado - linha
    edge_pct = abs(diferenca / linha * 100) if linha > 0 else 0
    
    if tipo_oferecido == "menos":
        tem_valor = valor_esperado < linha
        recomendacao = "MENOS" if tem_valor else "MAIS"
    else:
        tem_valor = valor_esperado > linha
        recomendacao = "MAIS" if tem_valor else "MENOS"
    
    abs_dif = abs(diferenca)
    confianca = "Alta" if abs_dif > 4 else "Média" if abs_dif > 2 else "Baixa"
    
    return {
        "diferenca": diferenca,
        "edge_pct": round(edge_pct, 1),
        "tem_valor": tem_valor,
        "recomendacao": recomendacao,
        "confianca": confianca
    }

def ajustar(valor, eh_casa):
    return round(valor * (AJUSTE_CASA if eh_casa else AJUSTE_FORA), 1)
