"""Ajuste por mariscal (QB) para el motor NFL.

Rating del QB = EPA por jugada de pase (dropback) con decaimiento y encogimiento hacia un nivel de suplente.
Base del equipo = rating promedio de los QB que jugaron sus pases recientes (lo que ya está metido en sus ratings).
Ajuste del juego = (rating del titular - base del equipo) x jugadas de pase por juego.
"""
import glob
import os

import numpy as np
import pandas as pd

DIR = os.environ.get("EEUU_DATOS", os.path.join(os.path.dirname(__file__), "datos"))
K_QB = 250.0       # dropbacks de "prior"
M0 = -0.06         # nivel de un QB sin historial (suplente típico, EPA/dropback relativo a la liga)
VIDA_QB = 400.0
VIDA_EQ = 60.0     # la base del equipo mira sus juegos recientes
PASES = 36.0       # dropbacks por juego


def dropbacks():
    out = []
    for f in sorted(glob.glob(os.path.join(DIR, "nfl_pbp_*.parquet"))):
        p = pd.read_parquet(f, columns=["game_id", "game_date", "posteam", "passer_player_id", "passer_player_name",
                                        "qb_dropback", "epa", "wp"])
        p = p[(p.qb_dropback == 1) & p.epa.notna() & p.passer_player_id.notna()]
        out.append(p.groupby(["game_id", "game_date", "posteam", "passer_player_id"]).agg(
            n=("epa", "size"), epa=("epa", "sum"), nombre=("passer_player_name", "first")).reset_index())
    d = pd.concat(out, ignore_index=True)
    d["fecha"] = pd.to_datetime(d.game_date)
    # EPA relativa a la liga de esa temporada (los años cambian de nivel)
    temp = d.game_id.str[:4]
    media = (d.groupby(temp).epa.sum() / d.groupby(temp).n.sum())
    d["epa_rel"] = d.epa - d.n * temp.map(media).values
    return d


class QB:
    def __init__(self, d):
        self.d = d

    def ratings(self, fecha):
        s = self.d[self.d.fecha < fecha]
        w = 0.5 ** ((fecha - s.fecha).dt.days.values / VIDA_QB)
        e = pd.Series(w * s.epa_rel.values).groupby(s.passer_player_id.values).sum()
        n = pd.Series(w * s.n.values).groupby(s.passer_player_id.values).sum()
        r = (e + K_QB * M0) / (n + K_QB)
        # base del equipo: rating de quienes lanzaron sus pases recientes
        we = 0.5 ** ((fecha - s.fecha).dt.days.values / VIDA_EQ)
        rr = s.passer_player_id.map(r).values
        base = pd.Series(we * s.n.values * rr).groupby(s.posteam.values).sum() / pd.Series(we * s.n.values).groupby(s.posteam.values).sum()
        return r.to_dict(), base.to_dict()

    @staticmethod
    def ajuste(r, base, equipo, qb_id):
        if qb_id is None or (isinstance(qb_id, float) and np.isnan(qb_id)) or equipo not in base:
            return 0.0
        return (r.get(qb_id, M0) - base[equipo]) * PASES
