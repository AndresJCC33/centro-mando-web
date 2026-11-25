"""Tabla de juegos NCAAB (ESPN vía sportsdataverse): un juego por fila con puntos y posesiones de cada equipo."""
import glob
import os

import numpy as np
import pandas as pd

DIR = os.environ.get("EEUU_DATOS", os.path.join(os.path.dirname(__file__), "datos"))


def posesiones(b):
    """Posesiones de un equipo en un juego (fórmula estándar de Oliver)."""
    return b["field_goals_attempted"] - b["offensive_rebounds"] + b["total_turnovers"] + 0.475 * b["free_throws_attempted"]


def juegos(temporadas=None):
    cajas, cal = [], []
    for f in sorted(glob.glob(os.path.join(DIR, "mbb_box_*.parquet"))):
        t = int(f[-12:-8])
        if temporadas and t not in temporadas:
            continue
        cajas.append(pd.read_parquet(f))
        s = os.path.join(DIR, f"mbb_sched_{t}.parquet")
        if os.path.exists(s):
            cal.append(pd.read_parquet(s, columns=["game_id", "neutral_site", "status_type_completed"]))
    b = pd.concat(cajas, ignore_index=True)
    for c in ["field_goals_attempted", "offensive_rebounds", "total_turnovers", "free_throws_attempted", "team_score",
              "opponent_team_score"]:
        b[c] = pd.to_numeric(b[c], errors="coerce")
    b["pos"] = posesiones(b)
    h = b[b.team_home_away == "home"].set_index("game_id")
    a = b[b.team_home_away == "away"].set_index("game_id")
    comun = h.index.intersection(a.index)
    h, a = h.loc[comun], a.loc[comun]
    g = pd.DataFrame({
        "game_id": comun, "temporada": h["season"].values, "tipo": h["season_type"].values,
        "fecha": pd.to_datetime(h["game_date"].values),
        "local": h["team_id"].values, "visita": a["team_id"].values,
        "local_nombre": h["team_display_name"].values, "visita_nombre": a["team_display_name"].values,
        "pl": h["team_score"].values, "pv": a["team_score"].values,
        "pos": (h["pos"].values + a["pos"].values) / 2,
    })
    if cal:
        c = pd.concat(cal).drop_duplicates("game_id").set_index("game_id")
        g["neutral"] = g["game_id"].map(c["neutral_site"]).fillna(False).astype(bool)
    else:
        g["neutral"] = False
    g = g.dropna(subset=["pl", "pv", "pos"])
    g = g[(g.pos > 40) & (g.pos < 110) & (g.pl + g.pv > 60)]  # cajas rotas fuera
    g = g.drop_duplicates("game_id").sort_values(["fecha", "game_id"]).reset_index(drop=True)
    return g


if __name__ == "__main__":
    g = juegos()
    print(g.shape)
    print(g.groupby("temporada").agg(n=("game_id", "size"), pos=("pos", "mean"), pts=("pl", "mean"),
                                      neutral=("neutral", "mean"), local_gana=("pl", lambda s: 0)).round(2))
    print((g.pl > g.pv)[~g.neutral].mean(), (g.pl - g.pv)[~g.neutral].mean())
