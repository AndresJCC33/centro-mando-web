"""Motor NHL v2: tiros a puerta + portero titular + calidad de tiro, sobre el motor de goles.

Goles esperados del local = tiros esperados del local x (1 - % de atajadas del portero rival) x factor de tiro del local
  - tiros esperados: Poisson log-lineal (generar / permitir tiros) con ajuste por rival y local, como el de goles.
  - portero: % de atajadas con encogimiento hacia la media de la liga (K_PORTERO tiros de "prior"), con decaimiento.
  - tiro: % de gol del equipo con encogimiento fuerte (K_TIRO).
Después se mezcla con los goles esperados del motor de goles (ALFA = peso de tiros+portero).
"""
import glob
import os

import numpy as np
import pandas as pd

from . import nhl_motor as G

DIR = os.environ.get("EEUU_DATOS", os.path.join(os.path.dirname(__file__), "datos"))
K_PORTERO = 2500.0
K_TIRO = 3000.0
VIDA_PORTERO = 400.0
ALFA = 0.6


def cargar(temporadas=None):
    tb, gb = [], []
    for f in sorted(glob.glob(os.path.join(DIR, "nhl_tbox_*.parquet"))):
        y = int(f[-12:-8])
        if temporadas and y not in temporadas:
            continue
        tb.append(pd.read_parquet(f).assign(temporada=y))
        gf = os.path.join(DIR, f"nhl_gbox_{y}.parquet")
        if os.path.exists(gf):
            gb.append(pd.read_parquet(gf).assign(temporada=y))
    t = pd.concat(tb)
    t = t[t.game_id.astype(str).str[4:6] == "02"]
    h = t[t.home_away == "home"].set_index("game_id")
    a = t[t.home_away == "away"].set_index("game_id")
    c = h.index.intersection(a.index)
    h, a = h.loc[c], a.loc[c]
    j = pd.DataFrame({"game_id": c, "temporada": h.temporada.values, "fecha": pd.to_datetime(h.game_date.values),
                      "local": h.team_abbrev.values, "visita": a.team_abbrev.values,
                      "gl": h.goals.values, "gv": a.goals.values, "sl": h.shots_on_goal.values, "sv": a.shots_on_goal.values})
    j = j.dropna().astype({"gl": int, "gv": int, "sl": int, "sv": int}).sort_values(["fecha", "game_id"]).reset_index(drop=True)
    g = pd.concat(gb)
    g = g[g.game_id.astype(str).str[4:6] == "02"]
    g["fecha"] = pd.to_datetime(g.game_date)
    tit = g[g.starter == True]  # noqa: E712
    tit = tit[["game_id", "team_abbrev", "player_id", "player_name"]]
    j = j.merge(tit.rename(columns={"team_abbrev": "local", "player_id": "port_l", "player_name": "port_l_n"}), on=["game_id", "local"], how="left")
    j = j.merge(tit.rename(columns={"team_abbrev": "visita", "player_id": "port_v", "player_name": "port_v_n"}), on=["game_id", "visita"], how="left")
    j = j.drop_duplicates("game_id")
    return j, g


class Porteros:
    """% de atajadas de cada portero antes de una fecha (con decaimiento y encogimiento)."""

    def __init__(self, g):
        g = g[(g.shots_against > 0)]
        self.g = g[["fecha", "player_id", "shots_against", "saves"]].copy()

    def tabla(self, fecha):
        s = self.g[self.g.fecha < fecha]
        if s.empty:
            return {}, 0.905
        w = 0.5 ** ((fecha - s.fecha).dt.days.values / VIDA_PORTERO)
        sh = pd.Series(w * s.shots_against.values).groupby(s.player_id.values).sum()
        sv = pd.Series(w * s.saves.values).groupby(s.player_id.values).sum()
        lg = sv.sum() / sh.sum()
        est = (sv + K_PORTERO * lg) / (sh + K_PORTERO)
        return est.to_dict(), lg


def tiro_equipos(j, fecha):
    s = j[j.fecha < fecha]
    w = 0.5 ** ((fecha - s.fecha).dt.days.values / VIDA_PORTERO)
    gol = pd.Series(np.concatenate([w * s.gl.values, w * s.gv.values])).groupby(np.concatenate([s.local.values, s.visita.values])).sum()
    tir = pd.Series(np.concatenate([w * s.sl.values, w * s.sv.values])).groupby(np.concatenate([s.local.values, s.visita.values])).sum()
    lg = gol.sum() / tir.sum()
    return ((gol + K_TIRO * lg) / (tir + K_TIRO) / lg).to_dict()


def correr(j, g, temporadas):
    P = Porteros(g)
    out = []
    prev_g = prev_s = None
    for t in temporadas:
        J = j[j.temporada == t]
        for d in sorted(J.fecha.unique()):
            d = pd.Timestamp(d)
            Rg = G.ajustar(J, d, prev_g)
            Js = J.rename(columns={"gl": "x1", "gv": "x2"}).rename(columns={"sl": "gl", "sv": "gv"})
            Rs = G.ajustar(Js, d, prev_s)
            if Rg is None or Rs is None:
                continue
            port, sv_lg = P.tabla(d)
            fin = tiro_equipos(j[j.temporada.isin([t - 1, t])], d)
            for r in J[J.fecha == d].itertuples():
                lg_, vg_ = G.esperados(Rg, r.local, r.visita)
                ls_, vs_ = G.esperados(Rs, r.local, r.visita)
                svv = port.get(r.port_v, sv_lg)  # portero rival del local
                svl = port.get(r.port_l, sv_lg)
                lx = ls_ * (1 - svv) * fin.get(r.local, 1.0)
                vx = vs_ * (1 - svl) * fin.get(r.visita, 1.0)
                out.append(dict(game_id=r.game_id, temporada=t, fecha=d, local=r.local, visita=r.visita, gl=r.gl, gv=r.gv,
                                lg_g=lg_, vg_g=vg_, lg_x=lx, vg_x=vx, sv_l=svl, sv_v=svv,
                                pj_l=Rg["pj"].get(r.local, 0), pj_v=Rg["pj"].get(r.visita, 0)))
        prev_g = G.ajustar(J, J.fecha.max() + pd.Timedelta(days=1), prev_g)
        Js = J.rename(columns={"gl": "x1", "gv": "x2"}).rename(columns={"sl": "gl", "sv": "gv"})
        prev_s = G.ajustar(Js, J.fecha.max() + pd.Timedelta(days=1), prev_s)
        print("temporada", t, flush=True)
    return pd.DataFrame(out)
