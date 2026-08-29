# ==============================================
# CONFIGURAÇÕES — PREENCHA SUAS CHAVES AQUI
# ==============================================

# 1. Token do Bot do Telegram — peça em @BotFather
TELEGRAM_TOKEN = "8819192214:AAEmA-EY2f-iKqW4xWbbzhusQXneyA3Yx1I"

# 2. Chave da API-Football — em dashboard.api-football.com
API_FOOTBALL_KEY = "ea675f5ba4e2600e7cc3207192f5f1c6"
API_FOOTBALL_HOST = "v3.football.api-sports.io"

# 3. Ajustes da análise
AJUSTE_CASA = 1.08    # +8% mandante
AJUSTE_FORA = 0.94    # -6% visitante

# 4. Temporada atual (detecta automaticamente)
from datetime import datetime
mes = datetime.now().month
ano = datetime.now().year
TEMPORADA = ano if mes >= 8 else ano - 1
