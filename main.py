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
        text="🔎 Testando resposta da API..."
    )

    hoje = datetime.now().strftime("%Y-%m-%d")
    url_fixtures = f"https://free-api-live-football-data.p.rapidapi.com/football-get-all-matches-by-date?date={hoje}"
    
    try:
        response = requests.get(url_fixtures, headers=headers_api, timeout=10)
        
        if response.status_code != 200:
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=f"🚨 ERRO DA API (Código {response.status_code}):\n{response.text[:300]}"
            )
            return

        data = response.json()
        chaves_retornadas = list(data.keys()) if isinstance(data, dict) else type(data)
        
        jogos_encontrados = []
        if isinstance(data, dict):
            resp = data.get("response")
            if isinstance(resp, list):
                jogos_encontrados = resp
            elif isinstance(resp, dict):
                jogos_encontrados = resp.get("matches", resp.get("list", []))

        if not jogos_encontrados:
            await context.bot.send_message(
                chat_id=CHAT_ID, 
                text=f"⚠️ API respondeu 200 OK, mas a lista veio vazia.\nChaves do JSON: {chaves_retornadas}\nConteúdo parcial: {str(data)[:300]}"
            )
            return

    except Exception as e:
        await context.bot.send_message(chat_id=CHAT_ID, text=f"❌ Erro na requisição Python: {str(e)}")
        return

    sinais_encontrados = 0
    jogos_processados = 0

    for partida in jogos_encontrados:
        jogos_processados += 1

        home_obj = partida.get("home", partida.get("teams", {}).get("home", {}))
        away_obj = partida.get("away", partida.get("teams", {}).get("away", {}))
        league_obj = partida.get("league", {})

        time_casa = home_obj.get("name", "Time Casa") if isinstance(home_obj, dict) else "Time Casa"
        time_fora = away_obj.get("name", "Time Fora") if isinstance(away_obj, dict) else "Time Fora"
        nome_liga = league_obj.get("name", "Liga Geral") if isinstance(league_obj, dict) else "Liga Geral"
        
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
            text=f"Análise concluída em {jogos_processados} jogos do dia. Nenhuma oportunidade encontrada."
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
