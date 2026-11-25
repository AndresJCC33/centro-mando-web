"""Motor NFL: fuerza de cada equipo por EPA (puntos esperados añadidos por jugada) y por puntos, y simulación
con la distribución real de márgenes (los números clave 3, 7, 10 salen solos).

Ratings (con jugadas y juegos ANTERIORES; las recientes pesan más; ancla a la temporada anterior):
  EPA por jugada de ataque y de defensa ajustado por rival (pases y carreras, sin minutos de basura),
  y puntos a favor y en contra ajustados por rival.
Margen esperado = coeficientes x (diferencias de EPA y de puntos) + ventaja de local, con coeficientes estimados
solo con temporadas anteriores. Simulación: margen y total se sacan de juegos reales con margen esperado parecido
(desplazados al margen esperado de este juego), así respeta la forma real de los resultados de la NFL.
"""
import glob
import os

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, vstack, identity
from scipy.sparse.linalg import lsqr

DIR = os.environ.get("EEUU_DATOS", os.path.join(os.path.dirname(__file__), "datos"))
VIDA_MEDIA = 140.0   # días
ANCLA = 8.0
REGRESO = 0.6


def jugadas():
    """EPA por equipo y juego (ataque) desde el play-by-play de nflverse."""
    out = []
    for f in sorted(glob.glob(os.path.join(DIR, "nfl_pbp_*.parquet"))):
        p = pd.read_parquet(f, columns=["game_id", "season", "season_type", "week", "game_date", "home_team", "away_team",
                                        "posteam", "defteam", "epa", "play_type", "wp", "success"])
        p = p[p.play_type.isin(["pass", "run"]) & p.epa.notna() & p.wp.between(0.05, 0.95)]
        a = p.groupby(["game_id", "posteam"]).agg(epa=("epa", "mean"), n=("epa", "size"), exito=("success", "mean")).reset_index()
        out.append(a)
    return pd.concat(out, ignore_index=True)


def juegos():
    g = pd.read_csv(os.path.join(DIR, "nfl_games.csv"))
    g = g[g.season >= 2012].copy()
    g["fecha"] = pd.to_datetime(g.gameday)
    g["neutral"] = g.location.eq("Neutral")
    e = jugadas()
    eh = e.rename(columns={"posteam": "home_team", "epa": "epa_l", "n": "n_l", "exito": "ex_l"})
    ea = e.rename(columns={"posteam": "away_team", "epa": "epa_v", "n": "n_v", "exito": "ex_v"})
    g = g.merge(eh, on=["game_id", "home_team"], how="left").merge(ea, on=["game_id", "away_team"], how="left")
    return g.sort_values(["fecha", "game_id"]).reset_index(drop=True)


def _ridge(eq, il, iv, yl, yv, w, loc, prev0, ancla):
    """y_l = media + h*loc + A[l] - D[v];  y_v = media - h*loc + A[v] - D[l]. Devuelve media, h, A, D."""
    n, m = len(eq), len(il)
    filas = np.arange(2 * m)
    sw = np.sqrt(np.concatenate([w, w]))
    rr = np.concatenate([filas] * 4)
    cc = np.concatenate([np.zeros(2 * m, int), np.ones(2 * m, int), np.concatenate([il, iv]) + 2, np.concatenate([iv, il]) + 2 + n])
    data = np.concatenate([np.ones(2 * m), np.concatenate([loc, -loc]), np.ones(2 * m), -np.ones(2 * m)]) * sw[rr]
    X = csr_matrix((data, (rr, cc)), shape=(2 * m, 2 + 2 * n))
    A = identity(2 + 2 * n, format="csr")[2:] * np.sqrt(ancla)
    y = np.concatenate([np.concatenate([yl, yv]) * sw, np.sqrt(ancla) * prev0])
    s = lsqr(vstack([X, A]), y, atol=1e-10, btol=1e-10, iter_lim=10000)[0]
    return s[0], s[1], s[2:2 + n], s[2 + n:]


def ajustar(g, fecha, previo=None, vida=VIDA_MEDIA, ancla=ANCLA):
    g = g[(g.fecha < fecha) & g.result.notna() & g.epa_l.notna() & g.epa_v.notna()]
    if len(g) < 16:
        return None
    w = 0.5 ** ((fecha - g.fecha).dt.days.values / vida)
    eq = pd.Index(sorted(set(g.home_team) | set(g.away_team)))
    il, iv = eq.get_indexer(g.home_team), eq.get_indexer(g.away_team)
    loc = np.where(g.neutral.values, 0.0, 1.0)
    n = len(eq)
    p_epa = np.zeros(2 * n)
    p_pts = np.zeros(2 * n)
    if previo:
        for k, e in enumerate(eq):
            if e in previo["r"]:
                ae, de, ap, dp = previo["r"][e]
                p_epa[k], p_epa[n + k], p_pts[k], p_pts[n + k] = (REGRESO * v for v in (ae, de, ap, dp))
    me, he, Ae, De = _ridge(eq, il, iv, g.epa_l.values, g.epa_v.values, w, loc, p_epa, ancla)
    mp, hp, Ap, Dp = _ridge(eq, il, iv, g.home_score.values.astype(float), g.away_score.values.astype(float), w, loc, p_pts, ancla)
    return {"epa": (me, he), "pts": (mp, hp), "r": {e: (Ae[k], De[k], Ap[k], Dp[k]) for k, e in enumerate(eq)}}


def rasgos(R, local, visita, neutral=False):
    z = (0.0, 0.0, 0.0, 0.0)
    ael, del_, apl, dpl = R["r"].get(local, z)
    aev, dev, apv, dpv = R["r"].get(visita, z)
    mp, hp = R["pts"]
    h = 0.0 if neutral else hp
    pts_l = mp + h + apl - dpv
    pts_v = mp - h + apv - dpl
    return {"epa_dif": (ael - dev) - (aev - del_), "pts_dif": pts_l - pts_v, "pts_tot": pts_l + pts_v,
            "loc": 0.0 if neutral else 1.0}


class Simulador:
    """Margen y total con la forma real: residuos de juegos con margen esperado parecido."""

    def __init__(self, hist):
        # hist: DataFrame con 'pred' (margen esperado del mercado o del motor), 'result' y 'total'
        self.h = hist.dropna(subset=["pred", "result", "total"])

    def muestras(self, mu, total_mu, ventana=2.0):
        h = self.h
        s = h[np.abs(h.pred - mu) <= ventana]
        if len(s) < 200:
            s = h.iloc[np.argsort(np.abs(h.pred.values - mu))[:400]]
        m = s.result.values - s.pred.values + mu
        m = np.rint(m)
        t = s.total.values - s.total_pred.values + total_mu if "total_pred" in s else np.full(len(m), total_mu)
        return m, t

    def probabilidades(self, mu, total_mu, linea_local=None, linea_total=None):
        m, t = self.muestras(mu, total_mu)
        m = m[m != 0] if (m == 0).any() else m  # NFL: los empates casi no existen (prórroga)
        r = {"p_local": float((m > 0).mean()), "margen": float(mu), "total": float(total_mu)}
        if linea_local is not None:
            d = m + linea_local
            r["p_cubre_local"] = float((d > 0).sum() / max(1, (d != 0).sum()))
        if linea_total is not None:
            r["p_over"] = float((t > linea_total).sum() / max(1, (t != linea_total).sum()))
        return r
