"""Análisis a fondo por juego para la página (datos/juegos_analisis.json): NFL, NBA y fútbol de las ligas principales.

Para cada juego de hoy y mañana (hora de Caracas) arma lo mismo que el resumen del cuaderno de Colab:
  - ¿quién gana? según el mercado (Pinnacle sin margen), cada motor y la probabilidad final (80 % mercado, 20 % motores);
  - cómo termina el margen contra el hándicap y la distribución del total;
  - valor esperado de cada apuesta con la mejor cuota disponible; veredicto (verde solo si valor >= 3 % y motores de acuerdo);
  - datos clave de los dos equipos y un «en pocas palabras».
Motores:
  NFL: Motor 1 (ratings EPA + puntos + mariscal) y Motor 2 (Monte Carlo serie por serie), como el cuaderno.
  NBA: el motor NBA del Centro de Mando (margen y total esperados de la vitrina); forma del resultado con la
       desviación real contra el cierre (SBR 2014-2023: margen 12,66; total 17,93).
  Fútbol: Poisson de goles con ataque y defensa por equipo (temporada actual y anterior de football-data), empates
          calibrados con la propia liga.
"""
import json
import math
import os
import sys
import zlib
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from scipy.stats import norm, poisson

sys.path.insert(0, os.path.dirname(__file__))
import motores_eeuu as ME  # noqa: E402  (descargas, TMP, nombres)
from actualizar import bajar, CARACAS, DATOS  # noqa: E402
from analisis import API_FD, filas_fd  # noqa: E402
from eeuu import nfl_motor, nfl_qb, nfl_series, nombres  # noqa: E402

SALIDA = os.path.join(DATOS, "juegos_analisis.json")
PESO_MOTORES = 0.2
VALOR_MIN = 0.03
SD_NBA = (12.66, 17.93)
LIGAS_FUT = {**API_FD, "soccer_uefa_champs_league": None}   # todas las ligas del vigilante con datos en football-data
NBA_NOMBRES = {"ATL": "Atlanta Hawks", "BOS": "Boston Celtics", "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
               "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers", "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
               "DET": "Detroit Pistons", "GSW": "Golden State Warriors", "HOU": "Houston Rockets", "IND": "Indiana Pacers",
               "LAC": "LA Clippers", "LAL": "Los Angeles Lakers", "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
               "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves", "NOP": "New Orleans Pelicans", "NYK": "New York Knicks",
               "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic", "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
               "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings", "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors",
               "UTA": "Utah Jazz", "WAS": "Washington Wizards"}
AVISOS = []
RES = {}   # (deporte, local, visita, fecha) -> (goles/puntos local, visita) de juegos terminados, para calificar picks
HIST = os.path.join(DATOS, "picks_historial.json")


# ---------------------------------------------------------------- utilidades
def am_dec(a):
    return a / 100 + 1 if a > 0 else 100 / -a + 1


def lo(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def sg(x):
    return 1 / (1 + math.exp(-x))


def mezcla2(pm, pk):
    if pk is None:
        return pm
    if pm is None:
        return pk
    return sg(PESO_MOTORES * lo(pm) + (1 - PESO_MOTORES) * lo(pk))


def mezcla3(pm, pk):
    """1X2: mezcla log-lineal y normaliza."""
    if pk is None:
        return pm
    q = np.exp(PESO_MOTORES * np.log(np.clip(pm, 1e-4, 1)) + (1 - PESO_MOTORES) * np.log(np.clip(pk, 1e-4, 1)))
    return q / q.sum()


def hist(valores, paso=1, recorte=None):
    v = np.asarray(valores)
    if recorte:
        v = v.clip(*recorte)
    b = np.floor(v / paso) * paso
    u, c = np.unique(b, return_counts=True)
    return [[float(x), round(float(y) / len(v), 5)] for x, y in zip(u, c)]


def tramos_hcp(m, linea_local, local, visita):
    """m: margen del local (muestras). linea_local: hándicap del local (negativo = favorito)."""
    L = -linea_local
    if L > 0:
        t = [(f"{visita} gana", (m < 0).mean(), "v"),
             (f"{local} gana por menos de {L:g}", ((m > 0) & (m < L)).mean(), "lc"),
             (f"{local} gana por {L:g} (push)", (m == L).mean(), "push") if float(L).is_integer() else None,
             (f"{local} gana por más de {L:g} (cubre)", (m > L).mean(), "l")]
    else:
        L2 = -L
        t = [(f"{local} gana", (m > 0).mean(), "l"),
             (f"{visita} gana por menos de {L2:g}", ((m < 0) & (m > -L2)).mean(), "vc"),
             (f"{visita} gana por {L2:g} (push)", (m == -L2).mean(), "push") if float(L2).is_integer() else None,
             (f"{visita} gana por más de {L2:g} (cubre)", (m < -L2).mean(), "v")]
    return [{"n": n, "p": round(float(p), 4), "c": c} for x in t if x for n, p, c in [x]]


def valor(apuestas, tope=0.20):
    """apuestas: (texto, casa, cuota_decimal, prob_final[, prob_motor, prob_mercado]). Ordenadas por valor esperado.
    «motor_ok»: el motor ve ese lado al menos tan probable como el mercado (si no, el valor sale solo de la cuota)."""
    out = []
    for x in apuestas:
        a, c, d, p = x[:4]
        if not (d and p):
            continue
        pm, pk = (x[4], x[5]) if len(x) >= 6 else (None, None)
        # el motor debe ver ese lado al menos tan probable como el mercado, pero sin irse a más de 20 puntos:
        # diferencias así casi siempre son un dato malo (cancha neutral mal cargada, lesión, pocos juegos)
        ok = bool(pm is not None and pk is not None and pk <= pm <= pk + tope)
        out.append({"apuesta": a, "casa": c, "cuota": round(d, 2), "p": round(p, 4), "ev": round(p * d - 1, 4),
                    "motor_ok": ok, "lejos": bool(pm is not None and pk is not None and pm > pk + tope),
                    "meta": x[6] if len(x) >= 7 else None})
    return sorted(out, key=lambda x: -x["ev"])


def lado_precio(p, nombre):
    return next((x for x in p["lados"] if x["nombre"] == nombre or x["clave"] == nombre), None)


def dec_de(lado):
    if not lado or not lado.get("mejor"):
        return None
    m = lado["mejor"]
    return m / 100 + 1 if m > 0 else 100 / -m + 1


_TOKEN = {}


def cartelera(fecha):
    """Cartelera del día en Drive (CENTRO_MANDO/cartelera/cartelera_AAAA-MM-DD.json); {} si no hay acceso."""
    import urllib.parse
    cid, sec, rt = (os.environ.get(k) for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))
    if not (cid and sec and rt):
        return {}
    try:
        if "h" not in _TOKEN:
            tok = json.loads(bajar("https://oauth2.googleapis.com/token", datos={
                "client_id": cid, "client_secret": sec, "refresh_token": rt, "grant_type": "refresh_token"}))["access_token"]
            _TOKEN["h"] = {"Authorization": f"Bearer {tok}"}
        q = f"name = 'cartelera_{fecha}.json' and trashed = false"
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode({"q": q, "fields": "files(id,modifiedTime)", "orderBy": "modifiedTime desc"})
        fs = json.loads(bajar(url, headers=_TOKEN["h"]))["files"]
        if not fs:
            return {}
        return json.loads(bajar(f"https://www.googleapis.com/drive/v3/files/{fs[0]['id']}?alt=media", headers=_TOKEN["h"]))
    except Exception as e:  # noqa: BLE001
        AVISOS.append(f"cartelera {fecha}: {e}")
        return {}


# ---------------------------------------------------------------- NFL
def nfl(partidos, hoy, ahora):
    if not partidos:
        return []
    t = hoy.year if hoy.month >= 8 else hoy.year - 1
    ME._bajar(f"{ME.NFLV}/schedules/games.csv", "nfl_games.csv")
    for y in (t - 2, t - 1, t):
        ME._bajar(f"{ME.NFLV}/pbp/play_by_play_{y}.parquet", f"nfl_pbp_{y}.parquet")
    d = pd.Timestamp(hoy)
    g = nfl_motor.juegos()
    G0, G1 = g[g.season == t - 1], g[g.season == t]
    R = nfl_motor.ajustar(G1, d, nfl_motor.ajustar(G0, G0[G0.result.notna()].fecha.max() + pd.Timedelta(days=1)))
    qr, qbase = nfl_qb.QB(nfl_qb.dropbacks()).ratings(d)
    pbp = nfl_series.cargar((t - 1, t), d)
    m2 = nfl_series.Motor2(pbp, t, d)
    perf = nfl_series.perfil(pbp, t)
    hist_cierre = g[g.season.between(2012, t - 1) & g.result.notna()]
    for r_ in G1[G1.result.notna()].itertuples():
        RES[("NFL", r_.home_team, r_.away_team, str(r_.gameday))] = (int(r_.home_score), int(r_.away_score))
    sal = []
    for p in partidos:
        al, av = nombres.NFL.get(p["local"]), nombres.NFL.get(p["visita"])
        fila = G1[(G1.home_team == al) & (G1.away_team == av) & G1.result.isna()]
        if not al or not av or fila.empty:
            AVISOS.append(f"NFL sin datos: {p['visita']} @ {p['local']}")
            continue
        x = fila.iloc[0]
        f = nfl_motor.rasgos(R, al, av, bool(x.neutral))
        aj = nfl_qb.QB.ajuste(qr, qbase, al, x.home_qb_id) - nfl_qb.QB.ajuste(qr, qbase, av, x.away_qb_id)
        B = ME.NFL_B
        mu1 = B[0] * f["epa_dif"] + B[1] * f["pts_dif"] + B[2] * f["loc"] + B[3] * aj + B[4]
        tot1 = ME.NFL_BT[0] * f["pts_tot"] + ME.NFL_BT[1]
        rng = np.random.default_rng(zlib.crc32(x.game_id.encode()))
        cerca = hist_cierre[np.abs(hist_cierre.spread_line - mu1) <= 1.5]
        if len(cerca) < 300:
            cerca = hist_cierre.iloc[np.argsort(np.abs(hist_cierre.spread_line.values - mu1))[:600]]
        M1 = np.rint(mu1 + rng.choice((cerca.result - cerca.spread_line).values, 100_000))
        T1 = tot1 + rng.choice((hist_cierre.total - hist_cierre.total_line).dropna().values, 100_000)
        sa, sb, pa, pb = m2.simular(al, av, 100_000, zlib.crc32(x.game_id.encode()), bool(x.neutral))
        M2, T2 = sa - sb, sa + sb
        MARG, TOT = np.concatenate([M1, M2]), np.concatenate([T1, T2])
        pg = lambda m: float((m > 0).mean() / max(1e-9, (m != 0).mean()))  # noqa: E731
        p1, p2, pmot = pg(M1), pg(M2), pg(MARG)
        ll, lv = lado_precio(p, p["local"]), lado_precio(p, p["visita"])
        pk = ll["p"] if ll else None
        if pk is None and pd.notna(x.home_moneyline):
            a, b = 1 / am_dec(x.home_moneyline), 1 / am_dec(x.away_moneyline)
            pk = a / (a + b)
        pfin = mezcla2(pmot, pk)
        hcp = -float(x.spread_line)
        cub = float((MARG + hcp > 0).mean() / max(1e-9, (MARG + hcp != 0).mean()))
        hk = 1 / am_dec(x.home_spread_odds), 1 / am_dec(x.away_spread_odds)
        p_hcp = mezcla2(cub, hk[0] / sum(hk))
        ovm = float((TOT > x.total_line).mean() / max(1e-9, (TOT != x.total_line).mean()))
        ok = 1 / am_dec(x.over_odds), 1 / am_dec(x.under_odds)
        p_ov = mezcla2(ovm, ok[0] / sum(ok))
        hm, om = hk[0] / sum(hk), ok[0] / sum(ok)
        pk_ = pk if pk is not None else 0.5
        ml_ok_l = pk is not None and p1 >= pk and p2 >= pk
        ml_ok_v = pk is not None and p1 <= pk and p2 <= pk
        # moneyline: los dos motores tienen que ver ese lado por encima del mercado (se usa el más prudente)
        ap = [(f"{al} moneyline", ll["casa"] if ll else "", dec_de(ll), pfin, min(p1, p2), pk_, {"m": "ml", "lado": "l"}),
              (f"{av} moneyline", lv["casa"] if lv else "", dec_de(lv), 1 - pfin, 1 - max(p1, p2), 1 - pk_, {"m": "ml", "lado": "v"}),
              (f"{al} {hcp:+g}", "cierre nflverse", am_dec(x.home_spread_odds), p_hcp, cub, hm, {"m": "hcp", "lado": "l", "linea": hcp}),
              (f"{av} {-hcp:+g}", "cierre nflverse", am_dec(x.away_spread_odds), 1 - p_hcp, 1 - cub, 1 - hm, {"m": "hcp", "lado": "v", "linea": hcp}),
              (f"Over {x.total_line:g}", "cierre nflverse", am_dec(x.over_odds), p_ov, ovm, om, {"m": "tot", "lado": "o", "linea": float(x.total_line)}),
              (f"Under {x.total_line:g}", "cierre nflverse", am_dec(x.under_odds), 1 - p_ov, 1 - ovm, 1 - om, {"m": "tot", "lado": "u", "linea": float(x.total_line)})]
        V = valor(ap)
        acuerdo = pk is not None and (p1 - pk) * (p2 - pk) > 0
        datos = []
        for titulo, eq_a, eq_d in ((f"Ataque {al} contra defensa {av}", al, av), (f"Ataque {av} contra defensa {al}", av, al)):
            filas = []
            for mtr in perf["ataque"].columns:
                va, vd = perf["ataque"][mtr].get(eq_a), perf["defensa"][mtr].get(eq_d)
                filas.append([mtr, _fmt(mtr, va), nfl_series.puesto(perf["ataque"], mtr, eq_a, False),
                              _fmt(mtr, vd), nfl_series.puesto(perf["defensa"], mtr, eq_d, True)])
            datos.append({"t": titulo, "cab": ["", f"ataque {eq_a}", "puesto", f"defensa {eq_d}", "puesto"], "filas": filas})
        qbt = []
        for eq, qid, qn in ((al, x.home_qb_id, x.home_qb_name), (av, x.away_qb_id, x.away_qb_name)):
            d_ = pbp[(pbp.season == t) & (pbp.qb_dropback == 1) & (pbp.passer_player_id == qid) & pbp.epa.notna()]
            qbt.append([f"{qn} ({eq})", len(d_), f"{d_.epa.mean():+.3f}" if len(d_) else "—",
                        f"{d_.success.mean():.0%}" if len(d_) else "—", f"{d_.sack.mean():.1%}" if len(d_) else "—"])
        datos.append({"t": "Mariscales (temporada)", "cab": ["", "pases", "EPA por pase", "% éxito", "% capturas"], "filas": qbt})
        tabla_series = [[f"serie de {al}"] + [f"{v:.0%}" for v in pa[:4]], [f"serie de {av}"] + [f"{v:.0%}" for v in pb[:4]]]
        datos.append({"t": "Cómo termina cada serie (Motor 2)", "cab": ["", "TD", "gol de campo", "sin puntos", "pérdida"], "filas": tabla_series})
        sal.append(_tarjeta(
            "NFL", "NFL", p, al, av, pk, [("Motor 1 (ratings)", p1), ("Motor 2 (series)", p2)], pfin,
            MARG, TOT, hcp, float(x.total_line), V, acuerdo, datos,
            extra=[f"Mariscales: {x.home_qb_name} y {x.away_qb_name}" + (f" (ajuste {aj:+.1f} pts)" if abs(aj) >= 0.5 else ""),
                   f"Puntos medios: {al} {(sa.mean() + (tot1 + mu1) / 2) / 2:.1f}, {av} {(sb.mean() + (tot1 - mu1) / 2) / 2:.1f}"]))
        sal[-1]["res"] = ["NFL", al, av, str(x.gameday)]
    return sal


def _fmt(m, v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    if m.startswith("%"):
        return f"{v:.0%}" if "capturas" not in m else f"{v:.1%}"
    return f"{v:+.3f}" if "EPA" in m else f"{v:.2f}"


# ---------------------------------------------------------------- NBA
def nba(hoy, ahora):
    try:
        vit = json.load(open(os.path.join(DATOS, "vitrina.json"), encoding="utf-8"))
        t = vit["tablas"]["previa"]
        rows = [dict(zip(t["cols"], r)) for r in t["data"]]
    except (OSError, KeyError, ValueError):
        return []
    try:
        an = json.load(open(os.path.join(DATOS, "analisis.json"), encoding="utf-8")).get("nba") or {}
    except (OSError, ValueError):
        an = {}
    for r in rows:
        if r["deporte"] in ("NBA", "LVBP") and r.get("marcador") and "-" in str(r["marcador"]):
            v_, l_ = (int(z) for z in str(r["marcador"]).split("-")[:2])
            RES[(r["deporte"], r["local"], r["visitante"], r["fecha"])] = (l_, v_)
    fechas = {(hoy + timedelta(days=k)).isoformat() for k in (0, 1)}
    cart = {}
    for f in sorted(fechas):
        for j in (cartelera(f).get("NBA") or {}).get("JUEGOS_HOY_NBA", []):
            cart[(f, j["local"], j["visitante"])] = j
    sal = []
    for r in rows:
        if r["deporte"] != "NBA" or r["fecha"] not in fechas or r.get("marcador") or r.get("margen_pred") is None:
            continue
        L, V_ = r["local"], r["visitante"]
        mu, tot = float(r["margen_pred"]), float(r["total_pred"])
        rng = np.random.default_rng(zlib.crc32(f"{L}{V_}{r['fecha']}".encode()))
        M = np.rint(rng.normal(mu, SD_NBA[0], 200_000))
        M = np.where(M == 0, np.where(rng.random(len(M)) < norm.cdf(mu / SD_NBA[0]), 1, -1), M)  # prórroga: nadie empata
        T = np.rint(rng.normal(tot, SD_NBA[1], 200_000))
        pm = float(r["p_local"]) if r.get("p_local") is not None else float((M > 0).mean())
        pk = None
        if r.get("p_mer_fav") is not None:
            pk = r["p_mer_fav"] if r["favorito"] == L else 1 - r["p_mer_fav"]
        pfin = mezcla2(pm, pk)
        c = cart.get((r["fecha"], L, V_))
        ap, hcp, lt = [], None, r.get("linea_total")
        if c:
            if c.get("ml_local") and c.get("ml_visitante"):
                pkk = pk if pk is not None else 0.5
                ap += [(f"{L} moneyline", "cuota típica", am_dec(c["ml_local"]), pfin, pm, pkk, {"m": "ml", "lado": "l"}),
                       (f"{V_} moneyline", "cuota típica", am_dec(c["ml_visitante"]), 1 - pfin, 1 - pm, 1 - pkk, {"m": "ml", "lado": "v"})]
            if c.get("handicap_local") is not None and c.get("cuota_hcp_local") and c.get("cuota_hcp_visitante"):
                hcp = float(c["handicap_local"])
                cub = float((M + hcp > 0).mean() / max(1e-9, (M + hcp != 0).mean()))
                hk = 1 / am_dec(c["cuota_hcp_local"]), 1 / am_dec(c["cuota_hcp_visitante"])
                ph = mezcla2(cub, hk[0] / sum(hk))
                hm = hk[0] / sum(hk)
                ap += [(f"{L} {hcp:+g}", "cuota típica", am_dec(c["cuota_hcp_local"]), ph, cub, hm, {"m": "hcp", "lado": "l", "linea": hcp}),
                       (f"{V_} {-hcp:+g}", "cuota típica", am_dec(c["cuota_hcp_visitante"]), 1 - ph, 1 - cub, 1 - hm, {"m": "hcp", "lado": "v", "linea": hcp})]
            if c.get("total") and c.get("cuota_over") and c.get("cuota_under"):
                lt = float(c["total"])
                ovm = float((T > lt).mean() / max(1e-9, (T != lt).mean()))
                ok = 1 / am_dec(c["cuota_over"]), 1 / am_dec(c["cuota_under"])
                po = mezcla2(ovm, ok[0] / sum(ok))
                om = ok[0] / sum(ok)
                ap += [(f"Over {lt:g}", "cuota típica", am_dec(c["cuota_over"]), po, ovm, om, {"m": "tot", "lado": "o", "linea": lt}),
                       (f"Under {lt:g}", "cuota típica", am_dec(c["cuota_under"]), 1 - po, 1 - ovm, 1 - om, {"m": "tot", "lado": "u", "linea": lt})]
        elif r.get("cuota_fav_am"):
            ap.append((f"{r['favorito']} moneyline", "cuota típica", am_dec(r["cuota_fav_am"]), pfin if r["favorito"] == L else 1 - pfin,
                       pm if r["favorito"] == L else 1 - pm, None, {"m": "ml", "lado": "l" if r["favorito"] == L else "v"}))
        datos = []
        if L in an and V_ in an:
            a, b = an[L], an[V_]
            filas = [[n, f"{a.get(k):.1f}" if a.get(k) is not None else "—", f"{b.get(k):.1f}" if b.get(k) is not None else "—"]
                     for k, n in (("pts", "puntos a favor"), ("pts_c", "puntos en contra"), ("reb", "rebotes"), ("ast", "asistencias"),
                                  ("tri", "triples"), ("perd", "pérdidas"), ("robos", "robos"), ("tapones", "tapones"))]
            filas.append(["últimos 5", " ".join(x["r"] for x in a.get("ultimos", [])), " ".join(x["r"] for x in b.get("ultimos", []))])
            datos.append({"t": "Promedios de la temporada", "cab": ["", L, V_], "filas": filas})
            for eq, E in ((L, a), (V_, b)):
                if E.get("jugadores"):
                    datos.append({"t": f"Jugadores de {eq} (más minutos)", "cab": ["", "min", "pts", "reb", "ast", "3P"],
                                  "filas": [[j["n"], j["min"], j["pts"], j["reb"], j["ast"], j["tri"]] for j in E["jugadores"][:6]]})
        p = {"local": NBA_NOMBRES.get(L, L), "visita": NBA_NOMBRES.get(V_, V_), "inicio": r["fecha"] + "T19:00-04:00", "sin_hora": True}
        sal.append(_tarjeta("NBA", "NBA", p, L, V_, pk, [("Motor NBA", pm)], pfin, M, T, hcp, lt, valor(ap),
                            True, datos, extra=[f"Señal del motor: {r['senal']} ({r['filtro'].lower()})" if r.get("senal") else ""]))
        sal[-1]["res"] = ["NBA", L, V_, r["fecha"]]
    return sal


# ---------------------------------------------------------------- LVBP
def _lvbp_k():
    """Dispersión de las carreras por equipo (binomial negativa) medida en los juegos de la temporada."""
    try:
        c = json.load(open(os.path.join(DATOS, "cache", "lvbp_cajas.json"), encoding="utf-8"))
        r = np.array([x["carreras"] for v in c.values() for x in v["eq"].values() if x.get("carreras") is not None], float)
        m, v = r.mean(), r.var()
        return float(m ** 2 / (v - m)) if v > m and len(r) >= 60 else 6.0
    except (OSError, ValueError, KeyError):
        return 6.0


def _negbin(mu, k, n, rng):
    return rng.negative_binomial(k, k / (k + mu), n)


def lvbp(hoy):
    try:
        vit = json.load(open(os.path.join(DATOS, "vitrina.json"), encoding="utf-8"))
        t = vit["tablas"]["previa"]
        rows = [dict(zip(t["cols"], r)) for r in t["data"]]
        an = json.load(open(os.path.join(DATOS, "analisis.json"), encoding="utf-8")).get("lvbp") or {}
    except (OSError, KeyError, ValueError):
        return []
    fechas = {(hoy + timedelta(days=k)).isoformat() for k in (0, 1)}
    k = _lvbp_k()
    sal = []
    for r in rows:
        if r["deporte"] != "LVBP" or r["fecha"] not in fechas or r.get("marcador") or r.get("p_local") is None or not r.get("total_pred"):
            continue
        L, V_ = r["local"], r["visitante"]
        p_obj, tot = float(r["p_local"]), float(r["total_pred"])
        rng = np.random.default_rng(zlib.crc32(f"{L}{V_}{r['fecha']}".encode()))
        # reparto del total entre los dos que reproduce la probabilidad del motor (extra innings: según fuerza)
        lo_, hi_ = 0.25, 0.75
        for _ in range(20):
            sh = (lo_ + hi_) / 2
            a, b = _negbin(tot * sh, k, 40000, np.random.default_rng(3)), _negbin(tot * (1 - sh), k, 40000, np.random.default_rng(4))
            pw = (a > b).mean() + (a == b).mean() * sh
            lo_, hi_ = (sh, hi_) if pw < p_obj else (lo_, sh)
        A, B = _negbin(tot * sh, k, 200_000, rng), _negbin(tot * (1 - sh), k, 200_000, rng)
        emp = A == B
        gana_l = rng.random(len(A)) < sh
        A = A + (emp & gana_l)
        B = B + (emp & ~gana_l)
        M, T = (A - B).astype(float), (A + B).astype(float)
        fav_l = p_obj >= 0.5
        hcp = -1.5 if fav_l else 1.5
        datos = []
        if L in an and V_ in an:
            a_, b_ = an[L], an[V_]
            filas = [[n, f"{a_.get(c):.2f}" if a_.get(c) is not None else "—", f"{b_.get(c):.2f}" if b_.get(c) is not None else "—"]
                     for c, n in (("carreras", "carreras anotadas"), ("carreras_c", "carreras permitidas"), ("hits", "hits"),
                                  ("hr", "jonrones"), ("ponches", "ponches (bateando)"), ("boletos", "boletos (bateando)"),
                                  ("total_prom", "total por juego"))]
            filas.append(["últimos 5", " ".join(x["r"] for x in a_.get("ultimos", [])), " ".join(x["r"] for x in b_.get("ultimos", []))])
            datos.append({"t": "Promedios por juego de la temporada", "cab": ["", _corto(L), _corto(V_)], "filas": filas})
        p = {"local": L, "visita": V_, "inicio": r["fecha"] + "T19:00-04:00", "sin_hora": True}
        g = _tarjeta("LVBP", "LVBP", p, _corto(L), _corto(V_), None, [("Motor LVBP", p_obj)], p_obj, M, T, hcp,
                     float(r["linea_total"]) if r.get("linea_total") else None, [], True, datos,
                     extra=[f"Carreras esperadas: {_corto(L)} {tot * sh:.1f} – {tot * (1 - sh):.1f} {_corto(V_)}"])
        g["aviso"] = "Sin cuotas: The Odds API no cubre la LVBP. Compara tú: cuota justa del favorito " + \
                     f"{1 / max(p_obj, 1 - p_obj):.2f} (si tu casa paga más que eso con 3 % de margen, hay valor)."
        sal.append(g)
    return sal


def _corto(n):
    return n.split(" de ")[0].split(" del ")[0] if " de" in n else n


# ---------------------------------------------------------------- NCAAB
def ncaab(hoy):
    try:
        me = json.load(open(os.path.join(DATOS, "motores_eeuu.json"), encoding="utf-8"))["deportes"]["NCAAB"]["juegos"]
    except (OSError, KeyError, ValueError):
        return []
    try:
        for x in json.load(open(os.path.join(DATOS, "motores_eeuu_historial.json"), encoding="utf-8"))["juegos"]:
            if x.get("deporte") == "NCAAB" and x.get("marcador"):
                gl_, gv_ = (int(z) for z in x["marcador"].split("-"))
                RES[("NCAAB", str(x["k_local"]), str(x["k_visita"]), x["fecha"])] = (gl_, gv_)
    except (OSError, ValueError, KeyError):
        pass
    dias = {hoy.isoformat(), (hoy + timedelta(days=1)).isoformat()}
    t = ME.temporada_actual(hoy)
    caja = os.path.join(ME.TMP, f"mbb_box_{t}.parquet")
    ff, R = {}, None
    if os.path.exists(caja):
        from eeuu import ncaab_datos, ncaab_motor
        b = pd.read_parquet(caja)
        b = b[b.game_date < pd.Timestamp(hoy)] if b.game_date.dtype.kind == "M" else b[pd.to_datetime(b.game_date) < pd.Timestamp(hoy)]
        num = ["field_goals_made", "field_goals_attempted", "three_point_field_goals_made", "three_point_field_goals_attempted",
               "free_throws_made", "free_throws_attempted", "offensive_rebounds", "defensive_rebounds", "total_turnovers",
               "team_score", "opponent_team_score", "assists", "steals", "blocks"]
        for c in num:
            b[c] = pd.to_numeric(b[c], errors="coerce")
        b["pos"] = ncaab_datos.posesiones(b)
        op = b[["game_id", "team_id"] + num + ["pos"]].rename(columns={c: "op_" + c for c in num + ["pos", "team_id"]})
        x = b.merge(op, on="game_id")
        x = x[x.team_id != x.op_team_id]
        gq = x.groupby("team_id").sum(numeric_only=True)
        n = x.groupby("team_id").size()
        ff = pd.DataFrame({
            "juegos": n,
            "pts/100 pos (ataque)": 100 * gq.team_score / gq.pos, "pts/100 pos (defensa)": 100 * gq.opponent_team_score / gq.op_pos,
            "ritmo (posesiones)": gq.pos / n,
            "% tiro efectivo": (gq.field_goals_made + 0.5 * gq.three_point_field_goals_made) / gq.field_goals_attempted,
            "% tiro efectivo rival": (gq.op_field_goals_made + 0.5 * gq.op_three_point_field_goals_made) / gq.op_field_goals_attempted,
            "% pérdidas": gq.total_turnovers / gq.pos, "% pérdidas forzadas": gq.op_total_turnovers / gq.op_pos,
            "% rebote ofensivo": gq.offensive_rebounds / (gq.offensive_rebounds + gq.op_defensive_rebounds),
            "tiros libres / tiros": gq.free_throws_attempted / gq.field_goals_attempted,
            "% triples": gq.three_point_field_goals_made / gq.three_point_field_goals_attempted,
        })
        try:
            g = ncaab_datos.juegos([t - 1, t])
            G0, G1 = g[g.temporada == t - 1], g[g.temporada == t]
            prev = ncaab_motor.ajustar(G0, G0.fecha.max() + pd.Timedelta(days=1))
            R = ncaab_motor.ajustar(G1, pd.Timestamp(hoy), prev["r"] if prev else None)
        except Exception as e:  # noqa: BLE001
            AVISOS.append(f"NCAAB ratings: {e}")
    sal = []
    ahora = datetime.now(timezone.utc)
    for j in me:
        if j["inicio"][:10] not in dias or datetime.fromisoformat(j["inicio"]) < ahora - timedelta(hours=3):
            continue
        il, iv = j.get("id_local"), j.get("id_visita")
        mu, tm = j["pts_local"] - j["pts_visita"], j["pts_local"] + j["pts_visita"]
        rng = np.random.default_rng(zlib.crc32(f"{il}{iv}{j['inicio']}".encode()))
        M = np.rint(rng.normal(mu, ME.SD_NCAAB[0], 200_000))
        M = np.where(M == 0, np.where(rng.random(len(M)) < norm.cdf(mu / ME.SD_NCAAB[0]), 1, -1), M)
        T = np.rint(rng.normal(tm, ME.SD_NCAAB[1], 200_000))
        pm, pk, pf = j["p_motor"], j.get("p_mercado"), j.get("p_final") or j["p_motor"]
        ap = []
        for lado in j.get("lados", []):
            es_l = lado["nombre"] == j["local"]
            pp = lado["p_final"]
            dec = (1 + lado["ventaja_final"]) / pp if pp else None
            ap.append((f"{lado['nombre']}", lado.get("casa") or "mejor casa", dec, pp, pm if es_l else 1 - pm, (pk if es_l else 1 - pk) if pk is not None else None, {"m": "ml", "lado": "l" if es_l else "v"}))
        V = valor(ap)
        datos = []
        if len(ff) and il in ff.index and iv in ff.index:
            filas = []
            for c in ff.columns:
                a_, b_ = ff.loc[il, c], ff.loc[iv, c]
                fmt = (lambda v: f"{v:.0%}") if c.startswith("%") else (lambda v: f"{v:.2f}" if c == "tiros libres / tiros" else f"{v:.1f}")
                filas.append([c, fmt(a_), fmt(b_)])
            datos.append({"t": "Cuatro factores y eficiencia (temporada)", "cab": ["", j["local"], j["visita"]], "filas": filas})
        if R:
            orden = sorted(R["r"], key=lambda e: -(R["r"][e][0] + R["r"][e][1]))
            pos = {e: i + 1 for i, e in enumerate(orden)}
            filas = [[n, f"{R['r'].get(e, (0, 0, 0))[0]:+.1f} / {R['r'].get(e, (0, 0, 0))[1]:+.1f}", str(pos.get(e, '—'))]
                     for n, e in ((j["local"], il), (j["visita"], iv))]
            datos.append({"t": "Rating ajustado por rival (ataque / defensa, pts por 100 posesiones sobre la media)", "cab": ["", "ataque / defensa", f"puesto de {len(orden)}"], "filas": filas})
        p = {"local": j["local"], "visita": j["visita"], "inicio": j["inicio"]}
        sal.append(_tarjeta("NCAAB", "NCAAB", p, _sigla(j["local"]), _sigla(j["visita"]), pk, [("Motor NCAAB", pm)], pf, M, T, None, None, V, True, datos,
                            extra=[f"Posesiones esperadas: {j.get('posesiones', 0):.0f}" + (" · cancha neutral" if j.get("neutral") else ""),
                                   "Pocos juegos esta temporada: el motor se apoya en la anterior." if (j.get("pj_local") or 0) < 5 or (j.get("pj_visita") or 0) < 5 else ""]))
        sal[-1]["res"] = ["NCAAB", str(il), str(iv), j["inicio"][:10]]
    return sal


def _sigla(n):
    w = n.split()
    return " ".join(w[:-1]) if len(w) > 1 else n

# ---------------------------------------------------------------- Fútbol
def _poisson_ratings(g, fecha, vida=240.0, ancla=8.0):
    from scipy.optimize import minimize
    g = g[g.fecha < fecha]
    w = 0.5 ** ((fecha - g.fecha).dt.days.values / vida)
    eq = pd.Index(sorted(set(g.local) | set(g.visita)))
    n = len(eq)
    il, iv = eq.get_indexer(g.local), eq.get_indexer(g.visita)
    gl, gv = g.gl.values.astype(float), g.gv.values.astype(float)

    def f(x):
        mu, h, a, d = x[0], x[1], x[2:2 + n], x[2 + n:]
        ll_ = mu + h + a[il] - d[iv]
        lv_ = mu + a[iv] - d[il]
        el, ev = np.exp(ll_), np.exp(lv_)
        rl, rv = w * (el - gl), w * (ev - gv)
        val = np.sum(w * (el - gl * ll_)) + np.sum(w * (ev - gv * lv_)) + ancla * (a @ a + d @ d)
        ga = np.bincount(il, rl, n) + np.bincount(iv, rv, n) + 2 * ancla * a
        gd = -np.bincount(iv, rl, n) - np.bincount(il, rv, n) + 2 * ancla * d
        return val, np.concatenate([[rl.sum() + rv.sum(), rl.sum()], ga, gd])
    x = minimize(f, np.concatenate([[0.3, 0.2], np.zeros(2 * n)]), jac=True, method="L-BFGS-B").x
    return {"mu": x[0], "h": x[1], "r": {e: (x[2 + k], x[2 + n + k]) for k, e in enumerate(eq)}}


def _esperados(R, l, v):
    al, dl = R["r"][l]
    av, dv = R["r"][v]
    return math.exp(R["mu"] + R["h"] + al - dv), math.exp(R["mu"] + av - dl)


def _matriz(lh, la, emp, mx=10):
    M = np.outer(poisson.pmf(np.arange(mx + 1), lh), poisson.pmf(np.arange(mx + 1), la))
    M[np.diag_indices_from(M)] *= emp
    return M / M.sum()


def futbol(partidos, hoy):
    if not partidos:
        return []
    try:
        an = json.load(open(os.path.join(DATOS, "analisis.json"), encoding="utf-8")).get("futbol") or {}
    except (OSError, ValueError):
        an = {}
    nom = an.get("nombres", {})
    eqs = an.get("equipos", {})
    a = hoy.year if hoy.month >= 7 else hoy.year - 1
    temps = [f"{str(a - 1)[2:]}{str(a)[2:]}", f"{str(a)[2:]}{str(a + 1)[2:]}"]
    modelos = {}
    d = pd.Timestamp(hoy)
    for cod in {c for c in LIGAS_FUT.values() if c}:
        filas = []
        try:
            for r in filas_fd(cod, temps, dias=730):
                dd = r["Date"]
                f = datetime.strptime(dd, "%d/%m/%Y" if len(dd) == 10 else "%d/%m/%y")
                filas.append((f, r["HomeTeam"], r["AwayTeam"], int(float(r["FTHG"])), int(float(r["FTAG"]))))
        except Exception as e:  # noqa: BLE001
            AVISOS.append(f"football-data {cod}: {e}")
        if not filas:
            continue
        g = pd.DataFrame(filas, columns=["fecha", "local", "visita", "gl", "gv"])
        for r_ in g.itertuples():
            RES[("F", r_.local, r_.visita, r_.fecha.strftime("%Y-%m-%d"))] = (int(r_.gl), int(r_.gv))
        R = _poisson_ratings(g, d)
        # empates: cociente real / Poisson en los partidos del último año (sirve igual para ligas de año calendario)
        act = g[g.fecha >= d - pd.Timedelta(days=365)]
        pe = [np.trace(_matriz(*_esperados(R, r.local, r.visita), 1.0)) for r in act.itertuples()
              if r.local in R["r"] and r.visita in R["r"]]
        emp = float(np.clip((act.gl == act.gv).mean() / np.mean(pe), 0.85, 1.35)) if len(pe) >= 30 else 1.0
        modelos[cod] = (R, emp)
    sal = []
    for p in partidos:
        cod = LIGAS_FUT.get(p["_clave"])
        l, v = nom.get(p["local"], p["local"]), nom.get(p["visita"], p["visita"])
        ll, le, lv = lado_precio(p, p["local"]), next((x for x in p["lados"] if x["clave"] == "Draw"), None), lado_precio(p, p["visita"])
        pk = np.array([ll["p"], le["p"], lv["p"]]) if ll and le and lv else None
        mot = None
        if cod in modelos and l in modelos[cod][0]["r"] and v in modelos[cod][0]["r"]:
            R, emp = modelos[cod]
            lh, la = _esperados(R, l, v)
            Mx = _matriz(lh, la, emp)
            i, j = np.indices(Mx.shape)
            pm = np.array([Mx[i > j].sum(), np.trace(Mx), Mx[i < j].sum()])
            mot = (lh, la, Mx, pm)
        if mot is None and pk is None:
            continue
        pfin = mezcla3(mot[3], pk) if mot else pk
        if mot:
            lh, la, Mx, pm = mot
            i, j = np.indices(Mx.shape)
            tot = i + j
            goles = [[float(k), round(float(Mx[tot == k].sum()), 5)] for k in range(0, 9)]
            extras = {"o15": float(Mx[tot > 1.5].sum()), "o25": float(Mx[tot > 2.5].sum()), "o35": float(Mx[tot > 3.5].sum()),
                      "ambos": float(Mx[(i > 0) & (j > 0)].sum()),
                      "marcadores": [[f"{a_}-{b_}", round(float(Mx[a_, b_]), 4)] for a_, b_ in
                                     sorted(((a_, b_) for a_ in range(6) for b_ in range(6)), key=lambda x: -Mx[x])[:6]],
                      "xg": [round(lh, 2), round(la, 2)]}
        else:
            goles, extras = None, {}
        pmm = mot[3] if mot else [None] * 3
        pkk = pk if pk is not None else [None] * 3
        ap = [(f"{p['local']}", ll["casa"] if ll else "", dec_de(ll), pfin[0], pmm[0], pkk[0], {"m": "1x2", "lado": "l"}),
              ("Empate", le["casa"] if le else "", dec_de(le), pfin[1], pmm[1], pkk[1], {"m": "1x2", "lado": "e"}),
              (f"{p['visita']}", lv["casa"] if lv else "", dec_de(lv), pfin[2], pmm[2], pkk[2], {"m": "1x2", "lado": "v"})]
        V = valor(ap)
        # en fútbol el «acuerdo» es que el motor y el mercado señalen el mismo lado con más valor
        acuerdo = bool(mot) and pk is not None and int(np.argmax(mot[3] - pk)) == int(np.argmax(pfin - pk))
        datos = []
        if l in eqs and v in eqs:
            A, B = eqs[l], eqs[v]
            c, f_ = A.get("casa", {}), B.get("fuera", {})
            filas = [[n, f"{c.get(k):.1f} / {c.get(k + '_c'):.1f}" if c.get(k) is not None else "—",
                      f"{f_.get(k):.1f} / {f_.get(k + '_c'):.1f}" if f_.get(k) is not None else "—"]
                     for k, n in (("goles", "goles (a favor / en contra)"), ("tiros", "tiros"), ("arco", "tiros al arco"),
                                  ("corners", "córners"), ("faltas", "faltas"), ("amarillas", "amarillas"))]
            filas.append(["% más de 2.5 / ambos anotan", f"{A.get('mas25', 0):.0%} / {A.get('ambos', 0):.0%}",
                          f"{B.get('mas25', 0):.0%} / {B.get('ambos', 0):.0%}"])
            filas.append(["últimos 5", " ".join(x["r"] for x in A.get("ultimos", [])), " ".join(x["r"] for x in B.get("ultimos", []))])
            datos.append({"t": f"{p['local']} en casa y {p['visita']} fuera (promedios por partido)", "cab": ["", p["local"], p["visita"]], "filas": filas})
        liga = p["_liga"]
        sal.append(_tarjeta_futbol(liga, p, pk, mot, pfin, goles, extras, V, acuerdo, datos))
        sal[-1]["res"] = ["F", l, v, p["inicio"][:10]]
    return sal


def _razon(m, apostar, futbol=False):
    if not m or apostar or m["ev"] < VALOR_MIN:
        return ""
    if futbol and m["p"] < 0.25:
        return "llega a 3 % pero es un batacazo (menos de 25 %): no se apuesta"
    if m.get("lejos"):
        return "el motor se separa más de 20 puntos del mercado: dato dudoso, no se apuesta"
    if not m["motor_ok"]:
        return "llega a 3 % solo por la cuota: el motor no respalda ese lado"
    return ""


def _tarjeta_futbol(liga, p, pk, mot, pfin, goles, ex, V, acuerdo, datos):
    mejor = V[0] if V else None
    apostar = bool(mejor and mejor["ev"] >= VALOR_MIN and mejor["p"] >= 0.25 and mejor["motor_ok"])
    razon = _razon(mejor, apostar, futbol=True)
    fav_i = int(np.argmax(pfin))
    fav = [p["local"], "Empate", p["visita"]][fav_i]
    fuentes = []
    if pk is not None:
        fuentes.append({"n": "Mercado (Pinnacle)", "p": [round(float(x), 4) for x in pk]})
    if mot:
        fuentes.append({"n": "Motor (Poisson)", "p": [round(float(x), 4) for x in mot[3]]})
    fuentes.append({"n": "FINAL", "p": [round(float(x), 4) for x in pfin]})
    pocas = [f"{'Gana ' + fav if fav_i != 1 else 'Lo más probable es el empate'} ({pfin[fav_i]:.0%}); empate {pfin[1]:.0%}."]
    if mot:
        pocas.append(f"Goles esperados: {p['local']} {ex['xg'][0]:.2f} – {ex['xg'][1]:.2f} {p['visita']}. Más de 2.5: {ex['o25']:.0%}; ambos anotan: {ex['ambos']:.0%}.")
        pocas.append(f"Marcador más probable: {ex['marcadores'][0][0]} ({ex['marcadores'][0][1]:.0%}).")
    if mejor:
        pocas.append(("Apuesta con valor: " if apostar else "Mejor valor esperado: ") + f"{mejor['apuesta']} en {mejor['casa']} a {mejor['cuota']:.2f} ({mejor['ev']:+.1%}).")
    return {"id": f"F|{p['local']}|{p['visita']}|{p['inicio'][:10]}", "deporte": "Fútbol", "liga": liga, "inicio": p["inicio"],
            "local": p["local"], "visita": p["visita"], "tres": True, "fuentes": fuentes, "favorito": fav, "p_fav": round(float(pfin[fav_i]), 4),
            "goles": goles, "extras": ex, "valor": V, "apostar": apostar, "razon": razon, "mejor": mejor, "datos": datos, "pocas": pocas,
            "sub": (f"xG {ex['xg'][0]:.2f} – {ex['xg'][1]:.2f}" if mot else "sin modelo para este partido: solo mercado")}


def _tarjeta(dep, liga, p, l, v, pk, motores, pfin, MARG, TOT, hcp, lt, V, acuerdo, datos, extra=()):
    mejor = V[0] if V else None
    pmot = float(np.mean([x[1] for x in motores]))
    acuerdo_ok = acuerdo and (pk is None or (pmot - pk) * (motores[0][1] - pk) > 0)
    apostar = bool(mejor and mejor["ev"] >= VALOR_MIN and mejor["motor_ok"])
    razon = _razon(mejor, apostar)
    fav, pf = (p["local"], pfin) if pfin >= 0.5 else (p["visita"], 1 - pfin)
    fuentes = ([{"n": "Mercado", "p": [round(pk, 4)]}] if pk is not None else []) + \
              [{"n": n, "p": [round(x, 4)]} for n, x in motores] + [{"n": "FINAL", "p": [round(pfin, 4)]}]
    ml, tm = float(np.mean(MARG)), float(np.mean(TOT))
    pl_, pv_ = (tm + ml) / 2, (tm - ml) / 2
    t = {"linea": lt, "over": round(float((TOT > lt).mean()), 4), "under": round(float((TOT < lt).mean()), 4)} if lt else {}
    rango = {"NFL": (3, (12, 84)), "NCAAF": (3, (10, 100)), "NBA": (4, (170, 280)), "NCAAB": (3, (100, 190)), "LVBP": (1, (0, 30))}[dep]
    t["hist"] = hist(TOT, rango[0], rango[1])
    pocas = [f"Gana {fav} con {pf:.0%}" + (f" (mercado {max(pk, 1 - pk):.0%}, motores {max(pmot, 1 - pmot):.0%})." if pk is not None else ".")]
    if hcp is not None:
        L = -hcp
        pocas.append(f"Hándicap {l} {hcp:+g}: cubre {(MARG > L).mean():.0%}" + (f", push {(MARG == L).mean():.0%}" if float(L).is_integer() else "")
                     + f", no cubre {(MARG < L).mean():.0%}.")
    if lt:
        pocas.append(f"Total {lt:g}: over {t['over']:.0%} / under {t['under']:.0%}.")
    pocas += [e for e in extra if e]
    if mejor:
        pocas.append(("Apuesta con valor: " if apostar else "Mejor valor esperado: ") + f"{mejor['apuesta']} en {mejor['casa']} a {mejor['cuota']:.2f} ({mejor['ev']:+.1%}).")
    return {"id": f"{dep}|{l}|{v}|{p['inicio'][:10]}", "deporte": dep, "liga": liga, "inicio": p["inicio"], "sin_hora": p.get("sin_hora", False),
            "local": p["local"], "visita": p["visita"], "cod": [l, v], "tres": False, "fuentes": fuentes,
            "favorito": fav, "p_fav": round(pf, 4), "marcador": [round(pl_, 1), round(pv_, 1)], "total_esp": round(tm, 1),
            "hcp": {"linea": hcp, "tramos": tramos_hcp(MARG, hcp, l, v)} if hcp is not None else None,
            "total": t, "valor": V, "apostar": apostar, "razon": razon, "mejor": mejor, "datos": datos, "pocas": pocas}


def ncaaf(hoy):
    """Fútbol americano universitario: motor de puntos + Elo de CFBD (motores_eeuu.json) contra el precio de Pinnacle;
    hándicap y total con la línea de DraftKings que trae el mercado (datos/mercado.json), sin cuota: solo como referencia."""
    try:
        me = json.load(open(os.path.join(DATOS, "motores_eeuu.json"), encoding="utf-8"))["deportes"]["NCAAF"]["juegos"]
    except (OSError, KeyError, ValueError):
        return []
    try:
        mk = {(j.get("n_local"), j.get("n_visita")): j for j in json.load(open(os.path.join(DATOS, "mercado.json"), encoding="utf-8"))["juegos"]
              if j.get("deporte") == "NCAAF"}
    except (OSError, KeyError, ValueError):
        mk = {}
    try:
        for x in json.load(open(os.path.join(DATOS, "motores_eeuu_historial.json"), encoding="utf-8"))["juegos"]:
            if x.get("deporte") == "NCAAF" and x.get("marcador"):
                gl_, gv_ = (int(z) for z in x["marcador"].split("-"))
                RES[("NCAAF", str(x["k_local"]), str(x["k_visita"]), x["fecha"])] = (gl_, gv_)
    except (OSError, ValueError, KeyError):
        pass
    dias = {(hoy + timedelta(days=k)).isoformat() for k in (0, 1, 2)}   # el sábado es la jornada grande: se ve desde el jueves
    ahora = datetime.now(timezone.utc)
    sal = []
    for j in me:
        if j["inicio"][:10] not in dias or datetime.fromisoformat(j["inicio"]) < ahora - timedelta(hours=4):
            continue
        mu, tm = j["margen"], j["total"]
        rng = np.random.default_rng(zlib.crc32(f"{j['local']}{j['visita']}{j['inicio']}".encode()))
        M = np.rint(rng.normal(mu, ME.NCAAF_SD[0], 200_000))
        M = np.where(M == 0, np.where(rng.random(len(M)) < norm.cdf(mu / ME.NCAAF_SD[0]), 1, -1), M)  # prórroga
        T = np.rint(rng.normal(tm, ME.NCAAF_SD[1], 200_000))
        pm, pk = j["p_motor"], j.get("p_mercado")
        pfin = mezcla2(pm, pk)
        ap = []
        for lado in j.get("lados", []):
            es_l = lado["nombre"] == j["local"]
            pp = lado["p_final"]   # probabilidad del mercado con la que se calculó su ventaja
            dec = (1 + lado["ventaja_final"]) / pp if pp else None
            ap.append((f"{lado['nombre']}", lado.get("casa") or "mejor casa", dec, pfin if es_l else 1 - pfin, pm if es_l else 1 - pm,
                       (pk if es_l else 1 - pk) if pk is not None else None, {"m": "ml", "lado": "l" if es_l else "v"}))
        # En NCAAF las noticias pesan mucho (un mariscal lesionado mueve 7-10 puntos) y el motor no las ve:
        # si se aparta más de 10 puntos del mercado, no respalda la apuesta.
        V = valor(ap, tope=0.10)
        m = mk.get((j["local"], j["visita"])) or {}
        hcp, lt = m.get("hcp"), m.get("tot")
        motores = [("Motor NCAAF", pm)] + ([("Elo de CFBD", j["p_elo"])] if j.get("p_elo") is not None else [])
        datos = [{"t": "Cómo los ve el motor", "cab": ["", j["local"], j["visita"]], "filas": [
            ["Elo previo (CFBD)", f"{j['elo_local']:.0f}" if j.get("elo_local") else "—", f"{j['elo_visita']:.0f}" if j.get("elo_visita") else "—"],
            ["Juegos esta temporada", str(j.get("pj_local") or 0), str(j.get("pj_visita") or 0)],
        ]}]
        extra = [f"Margen esperado {j['local']} {mu:+.1f} (modelo de puntos {j['margen_puntos']:+.1f}); total {tm:.1f}."
                 + (" Cancha neutral." if j.get("neutral") else ""),
                 "Hándicap y total con la línea de DraftKings, sin cuota: sirven de referencia, el valor se mide en el ganador." if (hcp is not None or lt) else ""]
        if pk is not None and abs(pm - pk) >= 0.12:
            extra.append(f"El motor se aparta {abs(pm - pk):.0%} del mercado: casi siempre es una noticia que el motor no ve "
                         "(lesión del mariscal, suspensiones, clima). Revisa antes de apostar.")
        p = {"local": j["local"], "visita": j["visita"], "inicio": j["inicio"]}
        sal.append(_tarjeta("NCAAF", "NCAAF", p, _sigla(j["local"]), _sigla(j["visita"]), pk, motores, pfin,
                            M, T, hcp, lt, V, True, datos, extra=extra))
        sal[-1]["res"] = ["NCAAF", str(j["id_local"]), str(j["id_visita"]), j["inicio"][:10]]
    return sal


def calificar(meta, gl, gv):
    m, lado = meta["m"], meta["lado"]
    if m in ("ml", "1x2"):
        gano = {"l": gl > gv, "v": gl < gv, "e": gl == gv}[lado]
        return "GANADO" if gano else "PERDIDO"
    if m == "hcp":
        d = gl - gv + meta["linea"]
        d = d if lado == "l" else -d
    else:
        d = (gl + gv - meta["linea"]) * (1 if lado == "o" else -1)
    return "GANADO" if d > 0 else "PUSH" if d == 0 else "PERDIDO"


def picks_historial(juegos, ahora):
    try:
        H = {x["id"]: x for x in json.load(open(HIST, encoding="utf-8"))["picks"]}
    except (OSError, ValueError, KeyError):
        H = {}
    vivos = set()
    for g in juegos:
        empezo = datetime.fromisoformat(g["inicio"]) <= ahora and not g.get("sin_hora")
        if g.get("sin_hora"):  # NBA: la hora real no está; se congela al día siguiente
            empezo = datetime.fromisoformat(g["inicio"][:10] + "T23:59-04:00") <= ahora
        pid = None
        if g["apostar"] and g.get("mejor") and g["mejor"].get("meta"):
            m = g["mejor"]
            pid = f"{g['id']}|{m['apuesta']}"
            vivos.add(pid)
            if not empezo:
                prev = H.get(pid, {})
                H[pid] = dict(id=pid, juego=g["id"], deporte=g["deporte"], liga=g["liga"], inicio=g["inicio"], sin_hora=g.get("sin_hora", False),
                              partido=f"{g['visita']} @ {g['local']}", apuesta=m["apuesta"], casa=m["casa"], cuota=m["cuota"], p=m["p"],
                              ev=m["ev"], meta=m["meta"], res=g.get("res"), resultado="PENDIENTE", unidades=None, marcador=None,
                              guardado=prev.get("guardado") or ahora.isoformat(timespec="minutes"), actualizado=ahora.isoformat(timespec="minutes"))
        if not empezo:  # un pick que dejó de ser verde antes de empezar se retira
            for k in [k for k, x in H.items() if x["juego"] == g["id"] and x["resultado"] == "PENDIENTE" and k != pid]:
                del H[k]
    for x in H.values():
        if x["resultado"] != "PENDIENTE" or not x.get("res"):
            continue
        dep, l, v, f = x["res"]
        f0 = datetime.strptime(f, "%Y-%m-%d").date()
        for dd in (0, -1, 1):
            k = (dep, l, v, (f0 + timedelta(days=dd)).isoformat())
            if k in RES:
                gl, gv = RES[k]
                x["resultado"] = calificar(x["meta"], gl, gv)
                x["unidades"] = round(x["cuota"] - 1, 3) if x["resultado"] == "GANADO" else 0.0 if x["resultado"] == "PUSH" else -1.0
                x["marcador"] = f"{gl}-{gv}"
                break
    lista = sorted(H.values(), key=lambda x: x["inicio"], reverse=True)
    with open(HIST, "w", encoding="utf-8") as fh:
        json.dump({"picks": lista}, fh, ensure_ascii=False, indent=0)
    return lista


def correr():
    os.makedirs(ME.TMP, exist_ok=True)
    ahora = datetime.now(timezone.utc)
    hoy = datetime.now(CARACAS).date()
    dias = {hoy.isoformat(), (hoy + timedelta(days=1)).isoformat()}
    pr = json.load(open(os.path.join(DATOS, "precios.json"), encoding="utf-8"))
    sel = {"NFL": [], "Fútbol": []}
    for l in pr.get("ligas", []):
        for p in l.get("partidos", []):
            if p["inicio"][:10] not in dias or datetime.fromisoformat(p["inicio"]) < ahora - timedelta(hours=3):
                continue
            if l["deporte"] == "NFL":
                sel["NFL"].append(p)
            elif l["clave"] in LIGAS_FUT:
                sel["Fútbol"].append(dict(p, _clave=l["clave"], _liga=l["nombre"]))
    juegos = []
    for nombre, fn in (("NFL", lambda: nfl(sel["NFL"], hoy, ahora)), ("NBA", lambda: nba(hoy, ahora)),
                       ("Fútbol", lambda: futbol(sel["Fútbol"], hoy)), ("LVBP", lambda: lvbp(hoy)), ("NCAAB", lambda: ncaab(hoy)),
                       ("NCAAF", lambda: ncaaf(hoy))):
        try:
            juegos += fn()
        except Exception as e:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            AVISOS.append(f"{nombre}: {type(e).__name__}: {e}")
    juegos.sort(key=lambda j: j["inicio"])
    try:
        picks = picks_historial(juegos, ahora)
    except Exception as e:  # noqa: BLE001
        AVISOS.append(f"historial de picks: {type(e).__name__}: {e}")
        picks = []
    doc = {"generado": datetime.now(CARACAS).isoformat(timespec="minutes"), "dias": sorted(dias), "juegos": juegos,
           "picks": picks[:300], "avisos": AVISOS}
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("análisis por juego:", {d: sum(j["deporte"] == d for j in juegos) for d in ("NFL", "NBA", "Fútbol", "LVBP", "NCAAB")}, "| avisos:", AVISOS)


if __name__ == "__main__":
    correr()
