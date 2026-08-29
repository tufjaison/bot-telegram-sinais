import os
import re
import pytesseract
from PIL import Image
from io import BytesIO
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from config import TELEGRAM_TOKEN
from analisador import buscar_com_fallback, extrair_jogos, ajustar, analisar_confronto

# ----------------------
# Comando /start
# ----------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚽ Analisador de Chutes Ativo!\n\n"
        "📸 Basta enviar a foto do bilhete que eu faço a análise completa:\n"
        "• Médias reais de chutes e chutes ao gol\n"
        "• Tendência: MAIS ou MENOS para cada confronto\n"
        "• Análise de TODOS os jogos encontrados\n\n"
        "Envie a imagem e pronto! 📤"
    )

# ----------------------
# Processar imagem
# ----------------------
async def processar_imagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text(
        "📸 Imagem recebida! Processando...\n"
        "🔍 Lendo o bilhete..."
    )
    
    # Baixar imagem
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
        texto = pytesseract.image_to_string(imagem)
    
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
            "❌ Não encontrei confrontos no formato reconhecido.\n"
            "Esperado: 'Time A x Time B'\n\n"
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
    await msg.edit_text("📊 Analisando tendências dos confrontos...")
    
    relatorio = "═════════════════════════════\n"
    relatorio += "📊 ANÁLISE COMPLETA DOS CONFRONTOS\n"
    relatorio += "═════════════════════════════\n\n"
    relatorio += f"📡 Fontes: {qtd_api} da API · {qtd_local} Local\n"
    relatorio += f"⚽ {len(jogos)} jogos encontrados\n\n"
    
    for idx, jogo in enumerate(jogos, 1):
        casa = dados_times[jogo["casa"]]
        fora = dados_times[jogo["fora"]]
        
        # Análise completa do confronto
        analise = analisar_confronto(casa, fora)
        
        relatorio += f"🎮 Jogo {idx}: {jogo['casa']} × {jogo['fora']}\n"
        relatorio += f"🏠 {jogo['casa']}: média {casa['chutes']} chutes → ajustado {ajustar(casa['chutes'], True)} [{casa['origem']}]\n"
        relatorio += f"👤 {jogo['fora']}: média {fora['chutes']} chutes → ajustado {ajustar(fora['chutes'], False)} [{fora['origem']}]\n"
        relatorio += f"\n📈 MÉDIA ESPERADA DO JOGO:\n"
        relatorio += f"   • Total de chutes: {analise['chutes_esperado']}\n"
        relatorio += f"   • Chutes ao gol:   {analise['gol_esperado']}\n"
        relatorio += f"\n🎯 TENDÊNCIA:\n"
        relatorio += f"   • Chutes: → {analise['tendencia_chutes']['icone']} {analise['tendencia_chutes']['texto']}\n"
        relatorio += f"     (Referência: {analise['ref_chutes']} chutes)\n"
        relatorio += f"   • Ao Gol: → {analise['tendencia_gol']['icone']} {analise['tendencia_gol']['texto']}\n"
        relatorio += f"     (Referência: {analise['ref_gol']} chutes ao gol)\n"
        relatorio += f"\n📊 NÍVEL DE CONFIANÇA:\n"
        relatorio += f"   • Chutes: {analise['confianca_chutes']}\n"
        relatorio += f"   • Ao Gol: {analise['confianca_gol']}\n"
        relatorio += f"\n💡 CONCLUSÃO:\n"
        relatorio += f"   {analise['conclusao']}\n"
        relatorio += "─────────────────────────────\n\n"
    
    # Resumo final
    relatorio += "═════════════════════════════\n"
    relatorio += "📋 RESUMO DAS TENDÊNCIAS\n"
    relatorio += "═════════════════════════════\n\n"
    
    for idx, jogo in enumerate(jogos, 1):
        casa = dados_times[jogo["casa"]]
        fora = dados_times[jogo["fora"]]
        analise = analisar_confronto(casa, fora)
        relatorio += f"{idx}. {jogo['casa']} × {jogo['fora']}\n"
        relatorio += f"   Chutes: {analise['tendencia_chutes']['icone']} {analise['tendencia_chutes']['resumo']} | Ao Gol: {analise['tendencia_gol']['icone']} {analise['tendencia_gol']['resumo']}\n\n"
    
    relatorio += "⚠️ Análise baseada em médias estatísticas históricas\n"
    relatorio += "⚠️ Odds não são consideradas nesta análise\n"
    relatorio += f"📅 Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    
    # Enviar resultado
    await msg.edit_text("✅ Análise concluída!")
    for i in range(0, len(relatorio), 3500):
        await update.message.reply_text(relatorio[i:i+3500])

# ----------------------
# Inicialização do Bot
# ----------------------
def main():
    print("🔄 Iniciando bot...")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, processar_imagem))
    
    print("✅ Bot Online — Aguardando fotos...")
    app.run_polling()

if __name__ == "__main__":
    main()
