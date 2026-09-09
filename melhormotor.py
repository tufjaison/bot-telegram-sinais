#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor de Presunções Esportivas v4.3 + Bot Telegram
Rodando no Render como Web Service (gratuito)
"""

import os, time, logging, math, csv, json, requests, joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import PoissonRegressor
from dotenv import load_dotenv

# ---- Telegram ----
import threading
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

# ==================== CHAVES ====================
BZZ_URL = os.getenv("BZZ_BASE_URL", "https://sports.bzzoiro.com/api/v2")
BZZ_API_KEY = os.getenv("BZZ_API_KEY")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

if not BZZ_API_KEY or not ODDS_API_KEY or not TELEGRAM_TOKEN:
    raise ValueError("Faltam chaves no .env (BZZ_API_KEY, ODDS_API_KEY, TELEGRAM_TOKEN)")

BANKROLL = 1000.0

# ==================== CONFIGURAÇÕES ====================
RIGOR = {
    'ev_minimo': 0.03,
    'prob_minima': 0.18,
    'odd_minima': 1.25,
    'edge_minimo': 0.02,
    'volatilidade_maxima': 0.25,
    'kelly_fraction': 0.25,
    'score_minimo': 0.40,
}

LIGA_CONFIG = {
    'default': {'rho': 0.12},
    'Premier League': {'rho': 0.10},
    'Serie A': {'rho': 0.18},
    'La Liga': {'rho': 0.16},
    'Bundesliga': {'rho': 0.08},
    'Ligue 1': {'rho': 0.14},
    'Eredivisie': {'rho': 0.08},
}

SPORT_MAP = {
    'Premier League': 'soccer_epl',
    'Serie A': 'soccer_italy_serie_a',
    'La Liga': 'soccer_spain_la_liga',
    'Bundesliga': 'soccer_germany_bundesliga',
    'Ligue 1': 'soccer_france_ligue_1',
    'Eredivisie': 'soccer_netherlands_eredivisie',
    'default': 'soccer'
}

FEATURES = [
    'gf_casa', 'gs_casa', 'gf_fora', 'gs_fora',
    'media_gf_home', 'media_gs_home', 'media_gf_away', 'media_gs_away',
    'confronto', 'forma_casa', 'forma_fora',
    'forca_ataque_casa', 'forca_defesa_casa',
    'forca_ataque_fora', 'forca_defesa_fora'
]

PARAMS = {
    'n_estimators': 50,
    'max_depth': 4,
    'learning_rate': 0.1,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'tree_method': 'hist',
    'objective': 'reg:squarederror'
}

AVANCED = {
    'ensemble_weights': {'xgboost': 0.5, 'poisson_reg': 0.3, 'moving_avg': 0.2},
    'backtest_size': 0.2,
    'export_json': True,
    'save_metrics': True,
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== CACHE ====================
CACHE = {}
def get_c(key, ttl=21600):
    if key in CACHE:
        ts, val = CACHE[key]
        if time.time() - ts < ttl:
            return val
        del CACHE[key]
    return None
def set_c(key, value):
    CACHE[key] = (time.time(), value)

# ==================== FUNÇÕES ORIGINAIS (TODAS) ====================

def fetch_historico(limit=300):
    data = get_c('hist')
    if data is not None:
        return data
    all_m = []
    for off in range(0, limit, 100):
        try:
            r = requests.get(
                f"{BZZ_URL}/events",
                headers={"Authorization": f"Token {BZZ_API_KEY}"},
                params={"status": "FINISHED", "limit": 100, "offset": off},
                timeout=15
            )
            if r.status_code == 200:
                all_m.extend(r.json().get('results', []))
            else:
                break
            time.sleep(0.5)
        except Exception:
            break
    all_m.sort(key=lambda x: x.get('utcDate', x.get('date', '')))
    set_c('hist', all_m)
    return all_m

def fetch_eventos_futuros(limit=10):
    try:
        r = requests.get(
            f"{BZZ_URL}/events",
            headers={"Authorization": f"Token {BZZ_API_KEY}"},
            params={"status": "SCHEDULED", "limit": limit},
            timeout=15
        )
        return r.json().get('results', [])
    except Exception:
        return []

def forma_pontos(team, df, n=5):
    jogos = df[(df['home'] == team) | (df['away'] == team)].tail(n)
    pts = 0
    for _, r in jogos.iterrows():
        if r['home'] == team:
            pts += 3 if r['hg'] > r['ag'] else 1 if r['hg'] == r['ag'] else 0
        else:
            pts += 3 if r['ag'] > r['hg'] else 1 if r['ag'] == r['hg'] else 0
    return pts / (n * 3) if n > 0 else 0.5

def preparar_df_avancado(matches):
    rows = []
    for m in matches:
        rows.append({
            'home': m.get('home_team', ''),
            'away': m.get('away_team', ''),
            'hg': int(m.get('home_score', 0) or 0),
            'ag': int(m.get('away_score', 0) or 0),
            'date': m.get('utcDate', m.get('date', ''))
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values('date').reset_index(drop=True)

    home_games = df[['home', 'hg', 'ag']].rename(columns={'home': 'team', 'hg': 'gf', 'ag': 'gs'})
    away_games = df[['away', 'ag', 'hg']].rename(columns={'away': 'team', 'ag': 'gf', 'hg': 'gs'})
    all_games = pd.concat([home_games, away_games], ignore_index=True)

    media_gf = all_games.groupby('team')['gf'].rolling(5, min_periods=1).mean().groupby(level=0).last()
    media_gs = all_games.groupby('team')['gs'].rolling(5, min_periods=1).mean().groupby(level=0).last()

    home_only = df.groupby('home').agg(
        gf_casa=('hg', lambda x: x.rolling(5, min_periods=1).mean().iloc[-1] if len(x) > 0 else 1.2),
        gs_casa=('ag', lambda x: x.rolling(5, min_periods=1).mean().iloc[-1] if len(x) > 0 else 1.2)
    ).fillna(1.2)
    away_only = df.groupby('away').agg(
        gf_fora=('ag', lambda x: x.rolling(5, min_periods=1).mean().iloc[-1] if len(x) > 0 else 1.2),
        gs_fora=('hg', lambda x: x.rolling(5, min_periods=1).mean().iloc[-1] if len(x) > 0 else 1.2)
    ).fillna(1.2)
    confronto = df.groupby(['home', 'away'])['hg'].agg(
        lambda x: x.rolling(3, min_periods=1).mean().iloc[-1] if len(x) > 0 else 1.2
    ).fillna(1.2).reset_index(name='confronto')

    df = df.merge(home_only, left_on='home', right_index=True, how='left')
    df = df.merge(away_only, left_on='away', right_index=True, how='left')
    df = df.merge(confronto, on=['home', 'away'], how='left')

    df['media_gf_home'] = df['home'].map(media_gf).fillna(1.2)
    df['media_gs_home'] = df['home'].map(media_gs).fillna(1.2)
    df['media_gf_away'] = df['away'].map(media_gf).fillna(1.2)
    df['media_gs_away'] = df['away'].map(media_gs).fillna(1.2)
    df['forma_casa'] = df['home'].apply(lambda t: forma_pontos(t, df, 5))
    df['forma_fora'] = df['away'].apply(lambda t: forma_pontos(t, df, 5))
    df['forca_ataque_casa'] = df['gf_casa'] / (df['gs_fora'] + 1e-5)
    df['forca_defesa_casa'] = df['gs_casa'] / (df['gf_fora'] + 1e-5)
    df['forca_ataque_fora'] = df['gf_fora'] / (df['gs_casa'] + 1e-5)
    df['forca_defesa_fora'] = df['gs_fora'] / (df['gf_casa'] + 1e-5)
    return df.fillna(1.2)

def treinar_modelos_separados(df):
    df = df.sort_values('date').reset_index(drop=True)
    split = int(len(df) * 0.8)
    train, test = df.iloc[:split], df.iloc[split:]
    X_train = train[FEATURES].values
    yh_train, ya_train = train['hg'].values, train['ag'].values
    X_test = test[FEATURES].values
    yh_test, ya_test = test['hg'].values, test['ag'].values

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model_h = xgb.XGBRegressor(**PARAMS)
    model_h.fit(X_train_scaled, yh_train, eval_set=[(X_test_scaled, yh_test)], verbose=False, early_stopping_rounds=10)
    model_a = xgb.XGBRegressor(**PARAMS)
    model_a.fit(X_train_scaled, ya_train, eval_set=[(X_test_scaled, ya_test)], verbose=False, early_stopping_rounds=10)

    X_all = scaler.transform(df[FEATURES].values)
    model_h.fit(X_all, df['hg'].values)
    model_a.fit(X_all, df['ag'].values)
    return model_h, model_a, scaler

def treinar_poisson_regressor(df):
    X_h = df[['forca_ataque_casa', 'forca_defesa_fora', 'forma_casa']].values
    y_h = df['hg'].values
    X_a = df[['forca_ataque_fora', 'forca_defesa_casa', 'forma_fora']].values
    y_a = df['ag'].values
    return (PoissonRegressor(alpha=0.1, max_iter=200).fit(X_h, y_h),
            PoissonRegressor(alpha=0.1, max_iter=200).fit(X_a, y_a))

def presuncao_gols_xgb(casa, fora, model_h, model_a, scaler, df):
    jogos_casa = df[df['home'] == casa].tail(5)
    gf_casa = jogos_casa['hg'].mean() if len(jogos_casa) else 1.2
    gs_casa = jogos_casa['ag'].mean() if len(jogos_casa) else 1.2
    jogos_fora = df[df['away'] == fora].tail(5)
    gf_fora = jogos_fora['ag'].mean() if len(jogos_fora) else 1.2
    gs_fora = jogos_fora['hg'].mean() if len(jogos_fora) else 1.2

    jogos_casa_global = df[(df['home'] == casa) | (df['away'] == casa)].tail(5)
    media_gf_home = jogos_casa_global['hg'].mean() if len(jogos_casa_global) else 1.2
    media_gs_home = jogos_casa_global['ag'].mean() if len(jogos_casa_global) else 1.2
    jogos_fora_global = df[(df['home'] == fora) | (df['away'] == fora)].tail(5)
    media_gf_away = jogos_fora_global['ag'].mean() if len(jogos_fora_global) else 1.2
    media_gs_away = jogos_fora_global['hg'].mean() if len(jogos_fora_global) else 1.2

    confrontos = df[(df['home'] == casa) & (df['away'] == fora)].tail(3)
    confronto = confrontos['hg'].mean() if len(confrontos) else 1.2
    forma_casa = forma_pontos(casa, df, 5)
    forma_fora = forma_pontos(fora, df, 5)
    forca_ataque_casa = gf_casa / (gs_fora + 1e-5)
    forca_defesa_casa = gs_casa / (gf_fora + 1e-5)
    forca_ataque_fora = gf_fora / (gs_casa + 1e-5)
    forca_defesa_fora = gs_fora / (gf_casa + 1e-5)

    X = np.array([[
        gf_casa, gs_casa, gf_fora, gs_fora,
        media_gf_home, media_gs_home, media_gf_away, media_gs_away,
        confronto, forma_casa, forma_fora,
        forca_ataque_casa, forca_defesa_casa,
        forca_ataque_fora, forca_defesa_fora
    ]])
    X_scaled = scaler.transform(X)
    return max(0, model_h.predict(X_scaled)[0]), max(0, model_a.predict(X_scaled)[0])

def presuncao_poisson_reg(casa, fora, model_h, model_a, df):
    ult_casa = df[df['home'] == casa].tail(5)
    ult_fora = df[df['away'] == fora].tail(5)
    f_ac = ult_casa['gf_casa'].mean() if not ult_casa.empty else 1.2
    f_df = ult_fora['gs_fora'].mean() if not ult_fora.empty else 1.2
    f_casa = forma_pontos(casa, df, 5)
    f_af = ult_fora['gf_fora'].mean() if not ult_fora.empty else 1.2
    f_dc = ult_casa['gs_casa'].mean() if not ult_casa.empty else 1.2
    f_fora = forma_pontos(fora, df, 5)
    Xh = np.array([[f_ac, f_df, f_casa]])
    Xa = np.array([[f_af, f_dc, f_fora]])
    return max(0, model_h.predict(Xh)[0]), max(0, model_a.predict(Xa)[0])

def presuncao_media(casa, fora, df):
    jc = df[df['home'] == casa].tail(5)
    gf_c = jc['hg'].mean() if len(jc) else 1.2
    gs_c = jc['ag'].mean() if len(jc) else 1.2
    jf = df[df['away'] == fora].tail(5)
    gf_f = jf['ag'].mean() if len(jf) else 1.2
    gs_f = jf['hg'].mean() if len(jf) else 1.2
    mg_c = df['hg'].mean() if not df.empty else 1.2
    mg_f = df['ag'].mean() if not df.empty else 1.2
    return (0.6*gf_c + 0.2*(1 - gs_f/(gs_f+1)) + 0.2*mg_c,
            0.6*gf_f + 0.2*(1 - gs_c/(gs_c+1)) + 0.2*mg_f)

def presuncao_ensemble(casa, fora, model_h, model_a, scaler, poiss_h, poiss_a, df, erro_h=0.4, erro_a=0.4):
    gx_h, gx_a = presuncao_gols_xgb(casa, fora, model_h, model_a, scaler, df)
    gp_h, gp_a = presuncao_poisson_reg(casa, fora, poiss_h, poiss_a, df)
    gm_h, gm_a = presuncao_media(casa, fora, df)
    w = AVANCED['ensemble_weights']
    gh = w['xgboost']*gx_h + w['poisson_reg']*gp_h + w['moving_avg']*gm_h
    ga = w['xgboost']*gx_a + w['poisson_reg']*gp_a + w['moving_avg']*gm_a
    z = 1.28
    return gh, ga, max(0, gh - z*erro_h), gh + z*erro_h, max(0, ga - z*erro_a), ga + z*erro_a

def backtest(df, model_h, model_a, scaler, poiss_h, poiss_a):
    split = int(len(df) * (1 - AVANCED['backtest_size']))
    test = df.iloc[split:].copy()
    erros = {'xgb': [], 'poisson': [], 'media': [], 'ensemble': []}
    for _, row in test.iterrows():
        train = df[df['date'] < row['date']].copy()
        if len(train) < 10:
            continue
        gx_h, gx_a = presuncao_gols_xgb(row['home'], row['away'], model_h, model_a, scaler, train)
        gp_h, gp_a = presuncao_poisson_reg(row['home'], row['away'], poiss_h, poiss_a, train)
        gm_h, gm_a = presuncao_media(row['home'], row['away'], train)
        ge_h = 0.5*gx_h + 0.3*gp_h + 0.2*gm_h
        ge_a = 0.5*gx_a + 0.3*gp_a + 0.2*gm_a
        erros['xgb'].append((gx_h - row['hg'], gx_a - row['ag']))
        erros['poisson'].append((gp_h - row['hg'], gp_a - row['ag']))
        erros['media'].append((gm_h - row['hg'], gm_a - row['ag']))
        erros['ensemble'].append((ge_h - row['hg'], ge_a - row['ag']))
    metrics = {}
    for nome, e in erros.items():
        eh = [x[0] for x in e]
        ea = [x[1] for x in e]
        metrics[nome] = {'rmse_h': np.sqrt(np.mean(np.square(eh))), 'rmse_a': np.sqrt(np.mean(np.square(ea)))}
    eh_ens = [x[0] for x in erros['ensemble']]
    ea_ens = [x[1] for x in erros['ensemble']]
    return metrics, np.std(eh_ens) if eh_ens else 0.4, np.std(ea_ens) if ea_ens else 0.4

def parse_date_flexible(date_str):
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        try:
            from dateutil import parser
            return parser.isoparse(date_str)
        except:
            for fmt in ('%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S.%fZ', '%Y-%m-%d'):
                try:
                    return datetime.strptime(date_str, fmt)
                except:
                    continue
            raise ValueError(f"Formato de data não reconhecido: {date_str}")

def get_odds(match):
    league = match.get('league', 'default')
    sport = SPORT_MAP.get(league, SPORT_MAP['default'])
    try:
        match_date = parse_date_flexible(match['date'])
    except Exception:
        return None
    date_from = (match_date - timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    date_to = (match_date + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'eu',
        'markets': 'h2h,totals',
        'dateFormat': 'iso',
        'oddsFormat': 'decimal',
        'commenceTimeFrom': date_from,
        'commenceTimeTo': date_to
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        if resp.status_code != 200:
            return None
        data = resp.json()
        for event in data:
            if event.get('home_team', '').lower() == match['home_team'].lower() and \
               event.get('away_team', '').lower() == match['away_team'].lower():
                return extrair_odds_median(event)
    except Exception:
        return None
    return None

def extrair_odds_median(event):
    odds = {}
    h2h = {'home': [], 'draw': [], 'away': []}
    totals = {'over': [], 'under': []}
    for bm in event.get('bookmakers', []):
        for market in bm.get('markets', []):
            if market.get('key') == 'h2h':
                for out in market.get('outcomes', []):
                    name = out.get('name', '').lower()
                    if name in h2h:
                        h2h[name].append(float(out.get('price', 1)))
            elif market.get('key') == 'totals':
                for out in market.get('outcomes', []):
                    if out.get('point') == 2.5:
                        name = out.get('name', '').lower()
                        if 'over' in name:
                            totals['over'].append(float(out.get('price', 1)))
                        elif 'under' in name:
                            totals['under'].append(float(out.get('price', 1)))
    for k, v in h2h.items():
        if v:
            odds[k] = np.median(v)
    for k, v in totals.items():
        if v:
            odds[k] = np.median(v)
    return odds if odds else None

def probs_dixon_coles(h_l, a_l, rho=0.15):
    max_gols = 10
    ph = [math.exp(-h_l)*(h_l**i)/math.factorial(i) for i in range(max_gols+1)]
    pa = [math.exp(-a_l)*(a_l**i)/math.factorial(i) for i in range(max_gols+1)]
    prob_h = prob_d = prob_a = 0.0
    for i in range(max_gols+1):
        for j in range(max_gols+1):
            p = ph[i]*pa[j]
            if i > j:
                prob_h += p
            elif i < j:
                prob_a += p
            else:
                prob_d += p
    if rho > 0:
        prob_d *= (1 + rho)
        soma = prob_h + prob_d + prob_a
        return {'home': prob_h/soma, 'draw': prob_d/soma, 'away': prob_a/soma}
    return {'home': prob_h, 'draw': prob_d, 'away': prob_a}

def prob_over_25(h_l, a_l):
    total = 0.0
    for i in range(11):
        for j in range(11):
            if i+j > 2:
                total += math.exp(-h_l)*(h_l**i)/math.factorial(i) * math.exp(-a_l)*(a_l**j)/math.factorial(j)
    return total

def prob_under_25(h_l, a_l):
    return 1.0 - prob_over_25(h_l, a_l)

def prob_btts(h_l, a_l):
    total = 0.0
    for i in range(1, 11):
        for j in range(1, 11):
            total += math.exp(-h_l)*(h_l**i)/math.factorial(i) * math.exp(-a_l)*(a_l**j)/math.factorial(j)
    return total

def amarrar(outcome, prob_modelo, odd, prob_mercado, volatilidade):
    if odd <= 1:
        return None
    ev = prob_modelo * odd - 1
    if ev < RIGOR['ev_minimo'] or prob_modelo < RIGOR['prob_minima'] or odd < RIGOR['odd_minima']:
        return None
    edge = prob_modelo - prob_mercado
    if edge < RIGOR['edge_minimo'] or volatilidade > RIGOR['volatilidade_maxima']:
        return None
    kelly = (prob_modelo * odd - 1) / (odd - 1) if odd > 1 else 0
    if kelly <= 0:
        return None
    fracao = min(kelly * RIGOR['kelly_fraction'], 0.05)
    score = 0.5 * edge/0.10 + 0.5 * ev/0.20
    score = min(1.0, max(0.0, score))
    if score < RIGOR['score_minimo']:
        return None
    return {
        'outcome': outcome,
        'prob': prob_modelo,
        'odd': odd,
        'ev': ev,
        'stake_estimado': fracao * BANKROLL,
        'score_percent': score * 100
    }

def selecionar_aprovada(probs, odds, volatilidade=0.0):
    inv_sum = sum(1/o for o in odds.values() if o > 1)
    if inv_sum == 0:
        return None
    fair_odds = {k: (1/o)/inv_sum for k, o in odds.items() if o > 1}
    market_probs = {k: 1/o for k, o in fair_odds.items()}
    best = None
    best_score = -999
    for outcome in ['home', 'draw', 'away']:
        if outcome not in odds or outcome not in probs:
            continue
        p = probs[outcome]
        o = odds[outcome]
        mp = market_probs.get(outcome, 1/o)
        aprov = amarrar(outcome, p, o, mp, volatilidade)
        if aprov and aprov['score_percent'] > best_score:
            best_score = aprov['score_percent']
            best = aprov
    return best

def aprov_over_under(prob_over, odd_over, odd_under, volatilidade=0.0):
    prob_under = 1.0 - prob_over
    ev_over = prob_over * odd_over - 1
    ev_under = prob_under * odd_under - 1
    for (tipo, prob, odd, ev) in [('Over', prob_over, odd_over, ev_over), ('Under', prob_under, odd_under, ev_under)]:
        if ev > RIGOR['ev_minimo'] and prob > RIGOR['prob_minima'] and odd > RIGOR['odd_minima']:
            edge = prob - 0.5
            if edge > RIGOR['edge_minimo'] and volatilidade <= RIGOR['volatilidade_maxima']:
                kelly = (prob * odd - 1) / (odd - 1) if odd > 1 else 0
                if kelly > 0:
                    fracao = min(kelly * RIGOR['kelly_fraction'], 0.05)
                    score = 0.5 * edge/0.10 + 0.5 * ev/0.20
                    score = min(1.0, max(0.0, score))
                    if score >= RIGOR['score_minimo']:
                        return {
                            'mercado': f'{tipo} 2.5',
                            'outcome': tipo,
                            'prob': prob,
                            'odd': odd,
                            'ev': ev,
                            'stake_estimado': fracao * BANKROLL,
                            'score_percent': score * 100
                        }
    return None

def registrar(casa, fora, liga, mercado, outcome, odd, stake, ev, score, data_jogo):
    arquivo = 'apostas.csv'
    existe = os.path.isfile(arquivo) and os.stat(arquivo).st_size > 0
    with open(arquivo, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(['data_registro','data_jogo','casa','fora','liga','mercado','outcome','odd','stake','ev','score','resultado','lucro'])
        w.writerow([datetime.now().strftime('%Y-%m-%d %H:%M'), data_jogo, casa, fora, liga, mercado, outcome,
                    round(odd,2), round(stake,2), round(ev,4), round(score,1), 'pendente', 0.0])

def exportar_json(dados, arquivo='presuncoes.json'):
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=2, default=str)
    logger.info(f"📄 JSON exportado: {arquivo}")

# ==================== FUNÇÃO DE ANÁLISE PARA O TELEGRAM ====================

def executar_analise(chat_id=None):
    """Executa o motor e retorna uma string com o resumo das apostas aprovadas."""
    logs = []
    def log_para_telegram(msg):
        logger.info(msg)
        if chat_id:
            logs.append(msg)

    log_para_telegram("🚀 Iniciando análise...")

    # Carregar/treinar XGB
    try:
        model_h = joblib.load('model_home.pkl')
        model_a = joblib.load('model_away.pkl')
        scaler = joblib.load('scaler.pkl')
    except:
        log_para_telegram("Treinando XGB...")
        hist = fetch_historico(500)
        if not hist:
            return "Erro: sem dados históricos."
        df = preparar_df_avancado(hist)
        if df.empty:
            return "Erro: DataFrame vazio."
        model_h, model_a, scaler = treinar_modelos_separados(df)
        joblib.dump(model_h, 'model_home.pkl')
        joblib.dump(model_a, 'model_away.pkl')
        joblib.dump(scaler, 'scaler.pkl')

    # Poisson
    log_para_telegram("Treinando Poisson...")
    hist_pois = fetch_historico(400)
    if not hist_pois:
        return "Erro: sem dados para Poisson."
    df_pois = preparar_df_avancado(hist_pois)
    if df_pois.empty:
        return "Erro: DataFrame Poisson vazio."
    poiss_h, poiss_a = treinar_poisson_regressor(df_pois)

    # Histórico completo
    hist_raw = fetch_historico(300)
    if not hist_raw:
        return "Erro: sem histórico."
    df_hist = preparar_df_avancado(hist_raw)
    if df_hist.empty:
        return "Erro: histórico vazio."

    # Backtest
    if len(df_hist) > 50:
        metrics, erro_h, erro_a = backtest(df_hist, model_h, model_a, scaler, poiss_h, poiss_a)
        log_para_telegram(f"Backtest: RMSE casa={metrics['ensemble']['rmse_h']:.3f}, fora={metrics['ensemble']['rmse_a']:.3f}")
    else:
        erro_h, erro_a = 0.5, 0.5

    # Eventos futuros
    eventos = fetch_eventos_futuros(15)
    if not eventos:
        return "Nenhum evento futuro encontrado."

    resultados = []
    total_aprovadas = 0
    linhas_resumo = []

    for evt in eventos:
        casa = evt.get('home_team', '')
        fora = evt.get('away_team', '')
        data = evt.get('utcDate') or evt.get('date')
        liga = evt.get('league', {}).get('name', 'default') if isinstance(evt.get('league'), dict) else 'default'
        if not casa or not fora or not data:
            continue

        df_filtrado = df_hist[df_hist['date'] < data].copy()
        if df_filtrado.empty:
            continue

        gh, ga, ic_h_inf, ic_h_sup, ic_a_inf, ic_a_sup = presuncao_ensemble(
            casa, fora, model_h, model_a, scaler, poiss_h, poiss_a, df_filtrado, erro_h, erro_a
        )

        match_info = {'home_team': casa, 'away_team': fora, 'league': liga, 'date': data}
        odds = get_odds(match_info)
        if not odds:
            continue

        volatilidade = np.std(list(odds.values())) / np.mean(list(odds.values())) if len(odds) > 1 else 0.0
        rho = LIGA_CONFIG.get(liga, LIGA_CONFIG['default'])['rho']
        probs_1x2 = probs_dixon_coles(gh, ga, rho)
        p_over = prob_over_25(gh, ga)
        p_under = prob_under_25(gh, ga)

        aprov = selecionar_aprovada(probs_1x2, odds, volatilidade)
        if aprov:
            mapa = {'home': 'Casa', 'draw': 'Empate', 'away': 'Fora'}
            linha = (f"✅ {casa} x {fora} ({liga})\n"
                     f"  Mercado: 1X2 -> {mapa[aprov['outcome']]} | Odd {aprov['odd']:.2f} | EV {aprov['ev']:.2%} | Stake R$ {aprov['stake_estimado']:.2f}")
            linhas_resumo.append(linha)
            registrar(casa, fora, liga, '1X2', aprov['outcome'], aprov['odd'], aprov['stake_estimado'], aprov['ev'], aprov['score_percent'], data)
            total_aprovadas += 1

        # Over/Under
        if 'over' in odds and 'under' in odds:
            aprov_ou_obj = aprov_over_under(p_over, odds['over'], odds['under'], volatilidade)
            if aprov_ou_obj:
                linha = (f"✅ {casa} x {fora} ({liga})\n"
                         f"  Mercado: {aprov_ou_obj['mercado']} | Odd {aprov_ou_obj['odd']:.2f} | EV {aprov_ou_obj['ev']:.2%} | Stake R$ {aprov_ou_obj['stake_estimado']:.2f}")
                linhas_resumo.append(linha)
                registrar(casa, fora, liga, aprov_ou_obj['mercado'], aprov_ou_obj['outcome'],
                          aprov_ou_obj['odd'], aprov_ou_obj['stake_estimado'], aprov_ou_obj['ev'], aprov_ou_obj['score_percent'], data)
                total_aprovadas += 1

    if total_aprovadas == 0:
        return "⚠️ Nenhuma aposta aprovada nesta rodada."

    resumo = f"📊 *RESUMO DA ANÁLISE*\nTotal de apostas aprovadas: {total_aprovadas}\n\n" + "\n".join(linhas_resumo)
    return resumo

# ==================== HANDLERS DO TELEGRAM ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Responde ao comando /start e executa a análise."""
    chat_id = update.effective_chat.id
    await update.message.reply_text("🔄 Iniciando análise... Isso pode levar alguns minutos. Aguarde.")

    def rodar():
        resultado = executar_analise(chat_id)
        # Envia a mensagem de volta
        context.bot.send_message(chat_id=chat_id, text=resultado, parse_mode='Markdown')

    thread = threading.Thread(target=rodar)
    thread.start()

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /status para verificar se o bot está online."""
    await update.message.reply_text("🤖 Bot está online e aguardando comandos. Envie /start para iniciar a análise.")

# ==================== MAIN ====================

def main():
    """Inicia o bot do Telegram."""
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("analisar", start))  # alias

    logger.info("🤖 Bot do Telegram iniciado. Aguardando comandos...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()