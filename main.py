import requests
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# Configurações de Token e Chaves
TELEGRAM_BOT_TOKEN = "8841800451:AAE_4-wSQ8LDY-uJH9s09uulW8S9_DDvSlo"
CHAT_ID = "--1004348164311"  # <--- COLE AQUI O ID QUE VOCÊ PEGOU NO NAVEGADOR (COM O SINAL -)

RAPIDAPI_KEY = "da8f4c8adamsh028fa7a3a2166f7p1e958ejsnff73e59f7c30"

# IDs das 12 principais ligas do futebol
LIGAS_ALVO = [71, 39, 140, 135, 78, 61, 2, 3, 848, 128, 253, 94] 

# Headers configurados para a Free API Live Football Data
headers_api = {
    "X-RapidAPI-Key": RAPIDAPI_KEY,
    "X-RapidAPI-Host": "free-api-live-football-data.p.rapidapi.com"
}

def estimar_probabilidade_vitoria(time_casa, time_fora):
    """
    Função para calcular a chance estimada do favorito.
    Deve avaliar forma recente, confrontos indiretos/diretos e momentos das equipes.
    Retorna (favorito_nome, probabilidade_float)
    """
    # Exemplo de cálculo do algoritmo (substitua pela sua regra estatística):
    prob_calculada = 0.85  # Exemplo: 85% de chance estimada
    favorito = time_casa
    return favorito, prob_calculada

async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Envia aviso no canal/grupo informado
    await context.bot.send_message(
        chat_id=CHAT_ID, 
        text="🔎 Buscando partidas das 12 ligas e analisando oportunidades..."
    )

    hoje = datetime.now().strftime("%Y-%m-%d")
    
    # Busca os jogos da data atual na Free API Live Football Data
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

    for partida in jogos_encontrados:
        liga_id = partida.get("league", {}).get("id")
        
        # Filtra apenas se o jogo pertencer a uma das 12 ligas alvo
        if liga_id in LIGAS_ALVO:
            jogos_processados += 1
            if jogos_processados > 90:
                break  # Limita a 90 jogos

            time_casa = partida.get("teams", {}).get("home", {}).get("name", "Time Casa")
            time_fora = partida.get("teams", {}).get("away", {}).get("name", "Time Fora")
            
            # Executa o cálculo da taxa estimada de vitória
            favorito, prob_estimada = estimar_probabilidade_vitoria(time_casa, time_fora)

            # Exemplo de odd vinda do mercado (ex: 1.22 = 81.9% de probabilidade implícita)
            odd_mercado = 1.22 
            prob_implicita = 1 / odd_mercado

            # CRITÉRIOS DE FILTRO:
            # 1. Taxa estimada de vitória superior a 80% (0.80)
            # 2. Probabilidade estimada maior que a oferecida pela odd (EV+)
            if prob_estimada > 0.80 and prob_estimada > prob_implicita:
                sinais_encontrados += 1
                mensagem = (
                    f"🎯 *SINAL DE APOSTA IDENTIFICADO*\n\n"
                    f"⚽ *Jogo:* {time_casa} x {time_fora}\n"
                    f"🏆 *Favorito:* {favorito}\n"
                    f"📈 *Probabilidade Estimada:* {prob_estimada * 100:.1f}%\n"
                    f"📊 *Odd do Mercado:* {odd_mercado:.2f} (Implícita: {prob_implicita * 100:.1f}%)\n\n"
                    f"✅ *Critério:* Taxa de vitória superior a 80% e valor sobre a odd do mercado."
                )
                # Envia o sinal diretamente para o canal/grupo do CHAT_ID
                await context.bot.send_message(
                    chat_id=CHAT_ID, 
                    text=mensagem, 
                    parse_mode="Markdown"
                )

    if sinais_encontrados == 0:
        await context.bot.send_message(
            chat_id=CHAT_ID, 
            text=f"Análise concluída em {jogos_processados} jogos. Nenhuma oportunidade com +80% de chance e EV+ encontrada para hoje."
        )

def main():
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("consultar", consultar))
    print("Bot rodando...")
    app.run_polling()

if __name__ == "__main__":
    main()

