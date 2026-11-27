"""Motor NCAAF (fútbol americano universitario).

Datos: calendario y marcadores de cfbfastR (sportsdataverse), con el Elo previo de CFBD de cada juego.
Modelo 1 (puntos): rating de ataque y defensa de cada equipo por mínimos cuadrados con ridge hacia el rating de la
temporada anterior (arrastrado), más ventaja de local; el mismo que en el estudio de ligas (2014-2023), donde las
apuestas en la APERTURA cuando el modelo difería 4+ puntos ganaron +0,59 puntos de CLV (el cierre no se le gana).
Modelo 2 (Elo de CFBD): probabilidad logística con la diferencia de Elo y la ventaja de local ajustada en el backtest.
"""
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, identity, vstack
from scipy.sparse.linalg import lsqr
from scipy.stats import norm

DIVISIONES = ("fbs", "fcs")


def juegos(rutas):
    """rutas: archivos parquet de cfbfastR (uno por temporada)."""
    xs = []
    for r in rutas:
        s = pd.read_parquet(r)
        xs.append(s)
    s = pd.concat(xs, ignore_index=True)
    for c in ("home_division", "away_division"):
        if c not in s:
            s[c] = "fbs"
    ok = s.home_division.fillna("fbs").isin(DIVISIONES) & s.away_division.fillna("fbs").isin(DIVISIONES)
    s = s[ok].copy()
    g = pd.DataFrame({
        "id": s.game_id.astype(str), "temporada": s.season.astype(int), "semana": s.week,
        "tipo": s.season_type, "fecha": pd.to_datetime(s.start_date, utc=True),
        "local": s.home_team.astype(str), "visita": s.away_team.astype(str),
        "pl": pd.to_numeric(s.home_points, errors="coerce"), "pv": pd.to_numeric(s.away_points, errors="coerce"),
        "neutral": s.neutral_site.fillna(False).astype(bool),
        "elo_l": pd.to_numeric(s.home_pregame_elo, errors="coerce"), "elo_v": pd.to_numeric(s.away_pregame_elo, errors="coerce"),
        "div_l": s.home_division.fillna("fbs"), "div_v": s.away_division.fillna("fbs"),
    })
    g["jugado"] = g.pl.notna() & g.pv.notna()
    return g.sort_values("fecha").reset_index(drop=True)


def ajustar(G, hasta, previo=None, lam=3.0, arrastre=0.6):
    """Ratings con los juegos jugados antes de «hasta». previo: {equipo: (ataque, defensa)} de la temporada anterior.
    Devuelve {"r": {equipo: (ataque, defensa)}, "mu", "hca", "pj": {equipo: juegos}} o None."""
    hasta = pd.Timestamp(hasta)
    hasta = hasta.tz_localize("UTC") if hasta.tzinfo is None else hasta
    ant = G[G.jugado & (G.fecha < hasta)]
    previo = previo or {}
    equipos = sorted(set(ant.local) | set(ant.visita) | set(previo))
    if len(ant) < 20 and not previo:
        return None
    idx = {t: k for k, t in enumerate(equipos)}
    T = len(equipos)
    prior = np.array([[previo.get(t, (0.0, 0.0))[0] * arrastre, previo.get(t, (0.0, 0.0))[1] * arrastre] for t in equipos])
    n = len(ant)
    rows, cols, vals, y = [], [], [], []
    for r_, (l_, v_, neu, pl_, pv_) in enumerate(zip(ant.local.map(idx), ant.visita.map(idx), ant.neutral, ant.pl, ant.pv)):
        h_ = 0.0 if neu else 1.0
        for kk, (o, de, hh, pts) in enumerate(((l_, v_, h_, pl_), (v_, l_, 0.0, pv_))):
            rr = 2 * r_ + kk
            rows += [rr, rr, rr, rr]
            cols += [o, T + de, 2 * T, 2 * T + 1]
            vals += [1.0, -1.0, 1.0, hh]
            y.append(pts)
    A = csr_matrix((vals, (rows, cols)), shape=(2 * n, 2 * T + 2))
    R = identity(2 * T + 2, format="csr")[: 2 * T] * np.sqrt(lam)
    yp = np.concatenate([prior[:, 0], prior[:, 1]]) * np.sqrt(lam)
    if n:
        AA, yy = vstack([A, R]), np.concatenate([np.array(y, float), yp])
    else:
        AA, yy = R, yp
    sol = lsqr(AA, yy, atol=1e-9, btol=1e-9, iter_lim=5000)[0]
    of, de = sol[:T], sol[T:2 * T]
    mu, hca = (sol[2 * T], sol[2 * T + 1]) if n else (27.0, 2.5)
    pj = pd.concat([ant.local, ant.visita]).value_counts().to_dict()
    return {"r": {t: (float(of[idx[t]]), float(de[idx[t]])) for t in equipos}, "mu": float(mu), "hca": float(hca),
            "pj": pj}


def predecir(R, local, visita, neutral=False):
    of_l, de_l = R["r"].get(local, (0.0, 0.0))
    of_v, de_v = R["r"].get(visita, (0.0, 0.0))
    pl = R["mu"] + of_l - de_v + (0.0 if neutral else R["hca"])
    pv = R["mu"] + of_v - de_l
    return pl, pv


def p_gana(margen, sd):
    """Probabilidad de que gane el local (sin empates: la prórroga reparte el 0 según el margen)."""
    return float(norm.cdf(margen / sd))


def p_elo(elo_l, elo_v, neutral, hfa):
    if elo_l is None or elo_v is None or np.isnan(elo_l) or np.isnan(elo_v):
        return None
    d = elo_l - elo_v + (0.0 if neutral else hfa)
    return float(1 / (1 + 10 ** (-d / 400)))
