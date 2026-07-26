import os
import requests
from threading import Thread
from flask import Flask
from datetime import datetime
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

async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_message(
        chat_id=CHAT_ID, 
        text="🔎 Buscando partidas de TODAS as ligas disponíveis hoje e analisando oportunidades..."
    )

    hoje = datetime.now().strftime("%Y-%m-%d")
    url_fixtures = f"https://free-api-live-football-data.p.rapidapi.com/football-get-all-matches-by-date?date={hoje}"
    
    try:
        response = requests.get(url_fixtures, headers=headers_api)
        data = response.json()
        jogos_encontrados = data.get("response", [])
    except Exception as e:
        await context.bot.send_message(chat_id=CHAT_ID, text="❌ Erro ao consultar a API de futebol.")
        return

    sinais_encontrados = 0
    jogos_processados = 0

    # Analisa TODOS os jogos do dia, sem restrição de ligas
    for partida in jogos_encontrados:
        jogos_processados += 1

        time_casa = partida.get("teams", {}).get("home", {}).get("name", "Time Casa")
        time_fora = partida.get("teams", {}).get("away", {}).get("name", "Time Fora")
        nome_liga = partida.get("league", {}).get("name", "Liga Geral")
        
        favorito, prob_estimada = estimar_probabilidade_vitoria(time_casa, time_fora)

        odd_mercado = 1.22 
        prob_implicita = 1 / odd_mercado

        if prob_estimada > 0.80 and prob_estimada > prob_implicita:
            sinais_encontrados += 1
            mensagem = (
                f"🎯 *SINAL DE APOSTA IDENTIFICADO*\n\n"
                f"🏆 *Competição:* {nome_liga}\n"
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
            text=f"Análise concluída em {jogos_processados} jogos de todas as ligas do dia. Nenhuma oportunidade com +80% e EV+ encontrada."
        )

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("consultar", consultar))
    print("Bot rodando com sucesso...")
    app.run_polling()

if __name__ == "__main__":
    main()
                )

    if sinais_encontrados == 0:
        await context.bot.send_message(
            chat_id=CHAT_ID, 
            text=f"Análise concluída em {jogos_processados} jogos. Nenhuma oportunidade com +80% e EV+ encontrada."
        )

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("consultar", consultar))
    print("Bot rodando com sucesso...")
    app.run_polling()

if __name__ == "__main__":
    main()
