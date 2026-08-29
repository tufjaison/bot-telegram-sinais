import os
import re
import pytesseract
from PIL import Image
from io import BytesIO
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_TOKEN
from analisador import buscar_com_fallback, extrair_jogos, avaliar, ajustar

# ----------------------
# Comando /start — opcional, mas mantido
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Analisador de Chutes Ativo!\n\n"
        "📸 Basta enviar a foto do bilhete que eu faço a análise completa:\n"
        "• Dados em tempo real\n"
        "• Melhores opções de aposta\n"
        "• Valor esperado e confiança\n\n"
        "Envie a imagem e pronto! 📤"
    )

# ----------------------
# FUNÇÃO PRINCIPAL — Aciona ao receber a IMAGEM
# NÃO PRECISA DE /start ANTES
# ----------------------
async def processar_imagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Mensagem imediata assim que a foto chega
    msg = await update.message.reply_text(
        "📸 Imagem recebida! Processando...\n"
        "🔍 Lendo o bilhete..."
    )
    
    # Baixar imagem enviada
    foto = await update.message.photo[-1].get_file()
    arquivo = BytesIO()
    await foto.download_to_memory(arquivo)
    arquivo.seek(0)
    imagem = Image.open(arquivo)
    
    # Extrair texto via OCR
    await msg.edit_text("📝 Extraindo texto...")
    try:
        texto = pytesseract.image_to_string(imagem, lang='por')
    except:
        texto = pytesseract.image_to_string(imagem)  # Fallback
    
    if not texto.strip():
        await msg.edit_text(
            "❌ Não consegui ler o texto da imagem.\n"
            "Dicas:\n"
            "• Tire uma foto mais nítida e bem iluminada\n"
            "• Alinhe o bilhete\n"
            "• Ou cole o texto aqui digitado"
        )
        return
    
    # Identificar os jogos
    await msg.edit_text("⚽ Identificando jogos e times...")
    jogos = extrair_jogos(texto)
    
    if not jogos:
        await msg.edit_text(
            "❌ Não encontrei jogos no formato reconhecido.\n"
            "Esperado: 'Time A x Time B'\n"
            "Linhas: 'Mais de X Chutes' ou 'Menos de X Chutes ao Gol'\n\n"
            f"Texto lido:\n{texto[:300]}"
        )
        return
    
    # Coletar todos os times únicos
    todos_times = list({t for j in jogos for t in [j["casa"], j["fora"]]})
    await msg.edit_text(f"🌐 Buscando dados de {len(todos_times)} times...")
    
    # Buscar estatísticas
    dados_times = {}
    qtd_api = 0
    qtd_local = 0
    
    for time in todos_times:
        dados = buscar_com_fallback(time)
        dados_times[time] = dados
        if dados["origem"] == "API":
            qtd_api += 1
        else:
            qtd_local += 1
    
    # Montar relatório
    await msg.edit_text("📊 Calculando melhores apostas...")
    
    relatorio = "═════════════════════════════\n"
    relatorio += "📊 ANÁLISE COMPLETA DO BILHETE\n"
    relatorio += "═════════════════════════════\n\n"
    relatorio += f"📡 Fontes: {qtd_api} da API · {qtd_local} Local\n"
    relatorio += f"⚽ {len(jogos)} jogos encontrados\n\n"
    
    total_com_valor = 0
    total_mercados = 0
    
    for idx, jogo in enumerate(jogos, 1):
        casa = dados_times[jogo["casa"]]
        fora = dados_times[jogo["fora"]]
        
        # Cálculos com ajuste casa/fora
        chutes_esperado = round(ajustar(casa["chutes"], True) + ajustar(fora["chutes"], False), 1)
        gol_esperado = round(ajustar(casa["chutes_gol"], True) + ajustar(fora["chutes_gol"], False), 1)
        
        relatorio += f"🎮 Jogo {idx}: {jogo['casa']} × {jogo['fora']}\n"
        relatorio += f"🏠 {jogo['casa']}: {casa['chutes']} → {ajustar(casa['chutes'], True)} (+8%) [{casa['origem']}]\n"
        relatorio += f"👤 {jogo['fora']}: {fora['chutes']} → {ajustar(fora['chutes'], False)} (-6%) [{fora['origem']}]\n"
        relatorio += f"📈 Total esperado: {chutes_esperado} chutes · {gol_esperado} ao gol\n"
        
        # Avaliar mercado de Chutes
        if jogo["linha_chutes"]:
            total_mercados += 1
            aval = avaliar(chutes_esperado, jogo["linha_chutes"], jogo["tipo_chutes"])
            icone = "✅" if aval["tem_valor"] else "❌"
            relatorio += f"   ├─ {icone} {jogo['tipo_chutes'].upper()} de {jogo['linha_chutes']} → {aval['recomendacao']}\n"
            relatorio += f"   │   Confiança: {aval['confianca']} · Edge: {aval['edge_pct']}% · Dif: {aval['diferenca']:+}\n"
            if aval["tem_valor"]: total_com_valor += 1
        
        # Avaliar mercado de Chutes ao Gol
        if jogo["linha_gol"]:
            total_mercados += 1
            aval = avaliar(gol_esperado, jogo["linha_gol"], jogo["tipo_gol"])
            icone = "✅" if aval["tem_valor"] else "❌"
            relatorio += f"   └─ {icone} {jogo['tipo_gol'].upper()} de {jogo['linha_gol']} → {aval['recomendacao']}\n"
            relatorio += f"       Confiança: {aval['confianca']} · Edge: {aval['edge_pct']}% · Dif: {aval['diferenca']:+}\n"
            if aval["tem_valor"]: total_com_valor += 1
        
        relatorio += "\n"
    
    # Resumo final
    relatorio += "═════════════════════════════\n"
    relatorio += f"🏆 MELHORES APOSTAS: {total_com_valor} de {total_mercados} mercados com valor ✅\n"
    if total_com_valor > 0:
        relatorio += "💡 Recomendado apostar nos mercados marcados ✅\n"
    else:
        relatorio += "⚠️ Nenhum mercado mostrou vantagem estatística clara\n"
    relatorio += "═════════════════════════════\n"
    relatorio += "⚠️ Aposte com responsabilidade · Dados sujeitos a variação\n"
    relatorio += f"📅 Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    
    # Enviar resultado — divide se for muito longo
    await msg.edit_text("✅ Análise concluída!")
    for i in range(0, len(relatorio), 3500):
        await update.message.reply_text(relatorio[i:i+3500])

# ----------------------
# Inicialização do Bot
# ----------------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Comandos
    app.add_handler(CommandHandler("start", start))
    
    # ⚡ A FUNÇÃO PRINCIPAL — ACIONA QUANDO ENVIAR FOTO
    # NÃO PRECISA DE /start ANTES
    app.add_handler(MessageHandler(filters.PHOTO, processar_imagem))
    
    print("✅ Bot Online — Aguardando fotos...")
    app.run_polling()

if __name__ == "__main__":
    main()
