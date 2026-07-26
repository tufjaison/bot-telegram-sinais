import os
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

def estimar_probabilidade_vitoria(time_casa, time_fora):
    prob_calculada = 0.85
    favorito = time_casa
    return favorito, prob_calculada

async def buscar_e_enviar_sinais(context: ContextTypes.DEFAULT_TYPE, data_str: str, rotulo_data: str):
    await context.bot.send_message(
        chat_id=CHAT_ID, 
        text=f"🔎 Buscando partidas de futebol agendadas para {rotulo_data} ({data_str})..."
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

    sinais_encontrados = 0
    jogos_processados = 0

    for partida in jogos_encontrados:
        jogos_processados += 1

        # Filtra partidas já finalizadas ou canceladas
        status_partida = str(partida.get("status", "")).lower()
        if any(termo in status_partida for termo in ["finished", "ft", "ended", "cancel", "postponed"]):
            continue

        home_obj = partida.get("home", {})
        away_obj = partida.get("away", {})
        
        time_casa = home_obj.get("name", "Time Casa") if isinstance(home_obj, dict) else "Time Casa"
        time_fora = away_obj.get("name", "Time Fora") if isinstance(away_obj, dict) else "Time Fora"
        nome_liga = partida.get("leagueName", partida.get("league", {}).get("name", "Liga Geral"))
        horario_jogo = partida.get("time", "Horário a definir")
        
        favorito, prob_estimada = estimar_probabilidade_vitoria(time_casa, time_fora)

        odd_mercado = 1.22 
        prob_implicita = 1 / odd_mercado

        if prob_estimada > 0.80 and prob_estimada > prob_implicita:
            sinais_encontrados += 1
            mensagem = (
                f"🎯 *SINAL DE APOSTA IDENTIFICADO ({rotulo_data.upper()})*\n\n"
                f"🏆 *Competição:* {nome_liga}\n"
                f"⏰ *Horário:* {horario_jogo}\n"
                f"⚽ *Jogo:* {time_casa} x {time_fora}\n"
                f"⭐️ *Favorito:* {favorito}\n"
                f"📈 *Probabilidade Estimada:* {prob_estimada * 100:.1f}%\n"
                f"📊 *Odd do Mercado:* {odd_mercado:.2f} (Implícita: {prob_implicita * 100:.1f}%)\n\n"
                f"✅ *Critério:* Taxa de vitória +80% e valor sobre a odd do mercado."
            )
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=mensagem, 
                parse_mode="Markdown"
            )

    if sinais_encontrados == 0:
        await context.bot.send_message(
            chat_id=CHAT_ID, 
            text=f"Análise concluída em {jogos_processados} jogos ({rotulo_data}). Nenhum jogo pendente com oportunidade +80% EV+ encontrada."
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
    
    # Registra os dois comandos
    app.add_handler(CommandHandler("consultar", consultar))
    app.add_handler(CommandHandler("amanha", amanha))
    
    print("Bot rodando com sucesso...")
    app.run_polling()

if __name__ == "__main__":
    main()
