"""NFL: perfil de equipos y Motor 2 (Monte Carlo serie por serie), igual que el cuaderno de Colab.

Cada serie ofensiva termina en TD, gol de campo, nada, pérdida, TD de la defensa o safety. Las probabilidades salen de
ataque x defensa / liga (log5 de varias salidas) con la temporada actual (las series recientes pesan más) y la anterior
al 35 %; encogidas con 40 series de prior. Puntos extra y conversiones de 2 con las tasas reales. Prórroga de temporada
regular (los dos tienen posesión, luego muerte súbita, puede quedar empate).
"""
import glob
import math
import os

import numpy as np
import pandas as pd

DIR = os.environ.get("EEUU_DATOS", os.path.join(os.path.dirname(__file__), "datos"))
CAT = ["TD", "FG", "NADA", "PERDIDA", "DEF_TD", "SAFETY"]
COLS = ["game_id", "season", "season_type", "game_date", "home_team", "away_team", "posteam", "defteam", "play_type", "epa",
        "success", "wp", "pass", "rush", "qb_dropback", "sack", "interception", "fumble_lost", "yards_gained", "down",
        "first_down", "half_seconds_remaining", "passer_player_id", "fixed_drive", "fixed_drive_result", "drive_inside20",
        "extra_point_result", "two_point_conv_result"]


def cargar(temporadas, hasta):
    p = pd.concat([pd.read_parquet(os.path.join(DIR, f"nfl_pbp_{y}.parquet"), columns=COLS) for y in temporadas
                   if os.path.exists(os.path.join(DIR, f"nfl_pbp_{y}.parquet"))], ignore_index=True)
    p["fecha"] = pd.to_datetime(p.game_date)
    return p[(p.fecha < hasta) & (p.season_type == "REG")]


def series(p):
    s = p.dropna(subset=["fixed_drive"]).groupby(["game_id", "posteam", "fixed_drive"]).agg(
        resultado=("fixed_drive_result", "first"), dentro20=("drive_inside20", "max"), defteam=("defteam", "first"),
        season=("season", "first"), fecha=("fecha", "first"), home=("home_team", "first")).reset_index()
    s["cat"] = s.resultado.map({"Touchdown": "TD", "Field goal": "FG", "Turnover": "PERDIDA", "Opp touchdown": "DEF_TD",
                                "Safety": "SAFETY"}).fillna("NADA")
    s["puntos"] = s.resultado.map({"Touchdown": 7, "Field goal": 3}).fillna(0)
    return s


class Motor2:
    def __init__(self, p, temporada, fecha):
        self.S = series(p)
        s = self.S[(self.S.fecha < fecha) & self.S.season.between(temporada - 1, temporada)].copy()
        s["w"] = 0.5 ** ((fecha - s.fecha).dt.days.values / 120.0) * np.where(s.season < temporada, 0.35, 1.0)
        liga = s.groupby("cat").w.sum().reindex(CAT, fill_value=0)
        self.liga = (liga / liga.sum()).values

        def por(lado):
            t = s.groupby([lado, "cat"]).w.sum().unstack(fill_value=0).reindex(columns=CAT, fill_value=0)
            return (t + 40.0 * self.liga).div(t.sum(axis=1) + 40.0, axis=0)
        self.atq, self.dfn = por("posteam"), por("defteam")
        self.ritmo = s.groupby(["posteam", "game_id"]).size().groupby(level=0).mean()
        x = p[p.season >= temporada - 1]
        self.p_xp = (x.extra_point_result == "good").sum() / max(1, x.extra_point_result.notna().sum())
        n2 = x.two_point_conv_result.notna().sum()
        self.p_2int = n2 / max(1, n2 + x.extra_point_result.notna().sum())
        self.p_2 = (x.two_point_conv_result == "success").sum() / max(1, n2)
        sl = s[s.posteam == s.home]
        sv = s[s.posteam != s.home]
        self.vent = math.sqrt((sl.cat == "TD").mean() / max(1e-9, (sv.cat == "TD").mean()))

    def mezcla(self, a, d):
        p = self.atq.loc[a].values * self.dfn.loc[d].values / self.liga
        return p / p.sum()

    def _td(self, n, rng):
        dos = rng.random(n) < self.p_2int
        return np.where(dos, 6 + 2 * (rng.random(n) < self.p_2), 6 + (rng.random(n) < self.p_xp))

    def simular(self, local, visita, n=100_000, seed=1, neutral=False):
        rng = np.random.default_rng(seed)
        pa, pb = self.mezcla(local, visita), self.mezcla(visita, local)
        if not neutral:
            pa = pa * np.r_[self.vent, 1, 1, 1, 1, 1]
            pb = pb * np.r_[1 / self.vent, 1, 1, 1, 1, 1]
        pa, pb = pa / pa.sum(), pb / pb.sum()
        mu = (self.ritmo.get(local, self.ritmo.mean()) + self.ritmo.get(visita, self.ritmo.mean())) / 2
        nd = np.clip(np.rint(rng.normal(mu, 1.0, n)), 7, 16).astype(int)
        na = nd + (rng.random(n) < 0.5)
        sa, sb = np.zeros(n), np.zeros(n)
        for p, nn, propio in ((pa, na, "a"), (pb, nd, "b")):
            r = rng.choice(len(CAT), size=(n, int(nn.max())), p=p)
            act = np.arange(r.shape[1])[None, :] < nn[:, None]
            cnt = {c: ((r == k) & act).sum(axis=1) for k, c in enumerate(CAT)}
            pts = np.zeros(n)
            for i in range(1, int(cnt["TD"].max()) + 1):
                pts += np.where(cnt["TD"] >= i, self._td(n, rng), 0)
            yo, el = (sa, sb) if propio == "a" else (sb, sa)
            yo += pts + 3 * cnt["FG"]
            el += 7 * cnt["DEF_TD"] + 2 * cnt["SAFETY"]
        # prórroga
        emp = np.where(sa == sb)[0]
        k = len(emp)
        if k:
            a1 = rng.random(k) < 0.5

            def serie(p):
                c = (rng.random(k)[:, None] > np.cumsum(p)[None, :]).sum(axis=1)
                return np.where(c == 0, 7, np.where(c == 1, 3, 0))
            quien = np.array([[a if j % 2 == 0 else not a for j in range(6)] for a in a1])
            pts = np.stack([np.where(quien[:, j], serie(pa), serie(pb)) for j in range(6)], axis=1)
            la, lb = np.zeros(k), np.zeros(k)
            for j in (0, 1):
                la += np.where(quien[:, j], pts[:, j], 0)
                lb += np.where(~quien[:, j], pts[:, j], 0)
            sigue = la == lb
            for j in range(2, 6):
                an = sigue & (pts[:, j] > 0)
                la += np.where(an & quien[:, j], pts[:, j], 0)
                lb += np.where(an & ~quien[:, j], pts[:, j], 0)
                sigue &= ~an
            sa[emp] += la
            sb[emp] += lb
        return sa, sb, pa, pb


def perfil(p, temporada):
    """Métricas de ataque y defensa de la temporada (y puesto en la liga; 1 = mejor)."""
    j = p[(p.season == temporada) & p.play_type.isin(["pass", "run"]) & p.epa.notna()].copy()
    j["expl"] = ((j["pass"] == 1) & (j.yards_gained >= 20)) | ((j.rush == 1) & (j.yards_gained >= 10))
    s = series(p[p.season == temporada])
    out = {}
    for lado, ls in (("posteam", "ataque"), ("defteam", "defensa")):
        g = j.groupby(lado)
        db = j[j.qb_dropback == 1].groupby(lado)
        sg = s.groupby(lado)
        rz = s[s.dentro20 == 1].groupby(lado).resultado.apply(lambda r: (r == "Touchdown").mean())
        t = pd.DataFrame({"EPA por jugada": g.epa.mean(), "% jugadas exitosas": g.success.mean(),
                          "EPA por pase": db.epa.mean(), "% jugadas explosivas": g.expl.mean(),
                          "% capturas": db.sack.mean(), "% 3er intento convertido": j[j.down == 3].groupby(lado).first_down.mean(),
                          "puntos por serie": sg.puntos.mean(), "% TD en zona roja": rz})
        out[ls] = t
    return out


# en ataque más alto es mejor salvo capturas; en defensa más bajo es mejor salvo capturas
def puesto(tabla, metrica, equipo, defensa):
    alto_mejor = metrica != "% capturas"
    if defensa:
        alto_mejor = not alto_mejor
    return int(tabla[metrica].rank(ascending=not alto_mejor, method="min").get(equipo, 0))
