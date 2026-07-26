import os
import requests
from threading import Thread
from flask import Flask
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot de Teste Online"

def run_web_server():
    port = int(os.environ.get("PORT", 10000))
    web_app.run(host="0.0.0.0", port=port)

TELEGRAM_BOT_TOKEN = "8841800451:AAE_4-wSQ8LDY-uJH9s09uulW8S9_DDvSlo"
CHAT_ID = "-1004348164311"
RAPIDAPI_KEY = "da8f4c8adamsh028fa7a3a2166f7p1e958ejsnff73e59f7c30"

headers_api = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "free-api-live-football-data.p.rapidapi.com"
}

async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    agora = datetime.now()
    
    # Formatos de data para testar
    formatos = {
        "BR (DD/MM/YYYY)": agora.strftime("%d/%m/%Y"),
        "Compacto (YYYYMMDD)": agora.strftime("%Y%m%d"),
        "ISO (YYYY-MM-DD)": agora.strftime("%Y-%m-%d")
    }
    
    relatorio = ["🔍 **TESTE DE FORMATOS DE DATA**\n"]

    for nome, data_str in formatos.items():
        url = f"https://free-api-live-football-data.p.rapidapi.com/football-get-matches-by-date?date={data_str}"
        try:
            res = requests.get(url, headers=headers_api, timeout=10)
            relatorio.append(f"📌 **Format:** {nome} (`{data_str}`)\n• Status: {res.status_code}\n• Retorno: `{res.text[:120]}`\n")
        except Exception as e:
            relatorio.append(f"📌 **Format:** {nome}\n• Erro: {str(e)}\n")

    await context.bot.send_message(
        chat_id=CHAT_ID, 
        text="\n".join(relatorio), 
        parse_mode="Markdown"
    )

def main():
    server_thread = Thread(target=run_web_server)
    server_thread.daemon = True
    server_thread.start()

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("consultar", consultar))
    app.run_polling()

if __name__ == "__main__":
    main()
