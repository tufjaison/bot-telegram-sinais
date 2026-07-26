import os
import time
import requests
from threading import Thread
from flask import Flask
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# --- SERVIDOR WEB SECUNDÁRIO PARA O RENDER ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot de Sinais está Online!"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

# --- CONFIGURAÇÕES DO BOT E API ---
TELEGRAM_BOT_TOKEN = "8841800451:AAE_4-wSQ8LDY-uJH9s09uulW8S9_DDvSlo"
CHAT_ID = "-1004348164311"

RAPIDAPI_KEY = "da8f4c8adamsh028fa7a3a2166f7p1e958ejsnff73e59f7c30"

headers_api = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "free-api-live-football-data.p.rapidapi.com"
}

# CACHE SIMPLES PARA EVITAR REQUISITION LIMITS NA API
cache_times = {}

# --- FUNÇÃO DE ANÁLISE ESTATÍSTICA REAL ---
def calcular_desempenho_time(time_id):
    """
    Busca as últimas partidas do time na API para calcular a taxa real de vitórias recentes.
    Utiliza cache simples para evitar exceder o limite de requisições.
    """
    if not time_id:
        return 0.50

    if time_id in cache_times:
        return cache_times[time_id]

    url_historico = f"https://free-api-live-football-data.p.rapidapi.com/football-get-team-all-matches?teamid={time_id}"
    
    try:
        # Respeitar limite de requisições da API
        time.sleep(0.1) 
        response = requests.get(url_historico, headers=headers_api, timeout=6)
        if response.status_code != 200:
            return 0.50
            
        dados = response.json()
        response_obj = dados.get("response", {})
        jogos = response_obj.get("matches", []) if isinstance(response_obj, dict) else []
        
        jogos_recentes = jogos[:5]
        if not jogos_recentes:
            return 0.50

        vitorias = 0
        total_jogos = 0

        for jogo in jogos_recentes:
            status_info = jogo.get("status", {})
            if isinstance(status_info, dict):
                status_str = str(status_info.get("reason", {}).get("short", "")).lower() or str(status_info.get("type", "")).lower()
            else:
                status_str = str(status_info).lower()

            if any(termo in status_str for termo in ["finished", "ft", "ended"]):
                total_jogos += 1
                home_obj = jogo.get("home", {})
                away_obj = jogo.get("away", {})
                
                gols_casa = home_obj.get("score", 0) if isinstance(home_obj, dict) else 0
                gols_fora = away_obj.get("score", 0) if isinstance(away_obj, dict) else 0
                
                eh_mandante = (isinstance(home_obj, dict) and str(home_obj.get("id")) == str(time_id))
                
                if eh_mandante and gols_casa > gols_fora:
                    vitorias += 1
                elif not eh_mandante and gols_fora > gols_casa:
                    vitorias += 1

        taxa = (vitorias / total_jogos) if total_jogos > 0 else 0.50
        cache_times[time_id] = taxa
        return taxa

    except Exception:
        return 0.50

def estimar_probabilidade_vitoria(time_casa_id, time_fora_id, nome_casa, nome_fora):
    """
    Compara o aproveitamento dos dois times para determinar quem é o favorito e a % estimada.
    """
    taxa_casa = calcular_desempenho_time(time_casa_id)
    taxa_fora = calcular_desempenho_time(time_fora_id)

    # Bônus de mandante (+5%)
    taxa_casa_ajustada = taxa_casa + 0.05

    total = taxa_casa_ajustada + taxa_fora
    if total == 0:
        return nome_casa, 0.50

    prob_casa = taxa_casa_ajustada / total
    prob_fora = taxa_fora / total

    if prob_casa >= prob_fora:
        return nome_casa, prob_casa
    else:
        return nome_fora, prob_fora

# --- BUSCA E ENVIO DOS TOP 10 SINAIS ---
async def buscar_e_enviar_sinais(context: ContextTypes.DEFAULT_TYPE, data_str: str, rotulo_data: str):
    await context.bot.send_message(
        chat_id=CHAT_ID, 
        text=f"🔎 Analisando todas as partidas de {rotulo_data} ({data_str}) para mapear os 10 mais prováveis..."
    )

    url_fixtures = f"https://free-api-live-football-data.p.rapidapi.com/football-get-matches-by-date?date={data_str}"
    
    try:
        response = requests.get(url_fixtures, headers=headers_api, timeout=12)
        
        if response.status_code != 200:
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=f"🚨 ERRO DA API (Código {response.status_code}):\n{response.text[:300]}"
            )
            return

        data = response.json()
        if not isinstance(data, dict) or data.get("status") != "success":
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=f"⚠️ A API não retornou sucesso: {data.get('message', 'Erro desconhecido')}"
            )
            return

        response_obj = data.get("response", {})
        jogos_encontrados = response_obj.get("matches", []) if isinstance(response_obj, dict) else []

        if not jogos_encontrados:
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=f"⚠️ Nenhuma partida encontrada para a data de {rotulo_data}."
            )
            return

    except Exception as e:
        await context.bot.send_message(
            chat_id=CHAT_ID, 
            text=f"❌ Erro na requisição Python: {str(e)}"
        )
        return

    candidatos_sinais = []

    for partida in jogos_encontrados:
        status_info = partida.get("status", {})
        if isinstance(status_info, dict):
            status_str = str(status_info.get("reason", {}).get("short", "")).lower() or str(status_info.get("type", "")).lower()
        else:
            status_str = str(status_info).lower()

        # Descarta partidas encerradas ou canceladas
        if any(termo in status_str for termo in ["finished", "ft", "ended", "canceled", "postponed"]):
            continue

        home_obj = partida.get("home", {}) if isinstance(partida.get("home"), dict) else {}
        away_obj = partida.get("away", {}) if isinstance(partida.get("away"), dict) else {}
        
        time_casa_id = home_obj.get("id")
        time_fora_id = away_obj.get("id")
        
        time_casa = home_obj.get("name", "Time Casa")
        time_fora = away_obj.get("name", "Time Fora")
        
        nome_liga = partida.get("leagueName", partida.get("league", {}).get("name", "Liga Geral"))
        horario_jogo = partida.get("time", "Horário a definir")

        favorito, prob_estimada = estimar_probabilidade_vitoria(
            time_casa_id, time_fora_id, time_casa, time_fora
        )

        # Odd padrão/estimada do mercado se não houver odd em tempo real
        odd_mercado = 1.35 
        prob_implicita = 1 / odd_mercado

        # Considera apenas jogos onde a probabilidade calculada supera a odd do mercado
        diferenca_valor = prob_estimada - prob_implicita

        if diferenca_valor > 0:
            candidatos_sinais.append({
                'liga': nome_liga,
                'horario': horario_jogo,
                'jogo': f"{time_casa} x {time_fora}",
                'favorito': favorito,
                'prob_estimada': prob_estimada,
                'odd_mercado': odd_mercado,
                'prob_implicita': prob_implicita,
                'diferenca': diferenca_valor
            })

    if not candidatos_sinais:
        await context.bot.send_message(
            chat_id=CHAT_ID, 
            text=f"Nenhum jogo com valor estimado acima da odd de mercado foi encontrado para {rotulo_data}."
        )
        return

    # Ordena os jogos do maior para o menor valor estimado/probabilidade
    candidatos_sinais.sort(key=lambda x: x['prob_estimada'], reverse=True)

    # Seleciona os Top 10 mais prováveis
    top_10 = candidatos_sinais[:10]

    await context.bot.send_message(
        chat_id=CHAT_ID, 
        text=f"🔥 *TOP {len(top_10)} JOGOS MAIS PROVÁVEIS ({rotulo_data.upper()})*",
        parse_mode="Markdown"
    )

    for idx, jogo in enumerate(top_10, 1):
        mensagem = (
            f"🎯 *# {idx} MAIS PROVÁVEL*\n"
            f"🏆 *Competição:* {jogo['liga']}\n"
            f"⏰ *Horário:* {jogo['horario']}\n"
            f"⚽ *Jogo:* {jogo['jogo']}\n"
            f"⭐️ *Favorito:* {jogo['favorito']}\n"
            f"📈 *Probabilidade Estimada:* {jogo['prob_estimada'] * 100:.1f}%\n"
            f"📊 *Odd do Mercado:* {jogo['odd_mercado']:.2f} (Implícita: {jogo['prob_implicita'] * 100:.1f}%)\n"
        )
        await context.bot.send_message(
            chat_id=CHAT_ID, 
            text=mensagem, 
            parse_mode="Markdown"
        )

# --- COMANDOS DO TELEGRAM ---
async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    hoje_compacto = datetime.now().strftime("%Y%m%d")
    await buscar_e_enviar_sinais(context, hoje_compacto, "hoje")

async def amanha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    amanha_compacto = (datetime.now() + timedelta(days=1)).strftime("%Y%m%d")
    await buscar_e_enviar_sinais(context, amanha_compacto, "amanhã")

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("consultar", consultar))
    app.add_handler(CommandHandler("amanha", amanha))
    
    print("Bot rodando com sucesso...")
    app.run_polling()

if __name__ == "__main__":
    main()
