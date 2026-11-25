"""Motores de simulación NCAAB, NHL y NFL para la página (datos/motores_eeuu.json).

Toma los juegos que sigue el vigilante de precios (datos/precios.json), ajusta los ratings de cada deporte con los
juegos ya jugados y simula cada partido. Publica el pronóstico del motor, el del mercado (Pinnacle sin margen) y la
mezcla, y guarda cada pronóstico antes del juego para medir después si el motor le gana al mercado.

Fuentes (sin créditos de The Odds API):
  NCAAB: cajas de ESPN (sportsdataverse)      NHL: calendario y marcadores (sportsdataverse)
  NFL: jugadas y juegos de nflverse (EPA)
Backtest (carpeta estudios/ del repo de motores; resumen en LEEME de herramientas/eeuu):
  NCAAB 2016-2021 (sin 2019-20, cierres dudosos): error medio del margen 8,7-9,1 contra 8,6-9,1 del cierre según
  los juegos jugados; mezclado al 10-15 % iguala o mejora apenas al cierre.
  NHL 2015-2023: log-loss 0,673 (cierre 0,667). NFL 2014-2026: error medio 10,33 (cierre 9,92).
"""
import json
import math
import zlib
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
TMP = os.environ.setdefault("EEUU_DATOS", "/tmp/eeuu_datos")
from actualizar import bajar, CARACAS, DATOS  # noqa: E402
from eeuu import ncaab_datos, ncaab_motor, nhl_motor, nfl_motor, nombres  # noqa: E402

SALIDA = os.path.join(DATOS, "motores_eeuu.json")
HIST = os.path.join(DATOS, "motores_eeuu_historial.json")
SDV = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download"
NFLV = "https://github.com/nflverse/nflverse-data/releases/download"
# peso del motor en la probabilidad final (el resto es el mercado). Solo NCAAB mejoró al cierre en el backtest.
MEZCLA = {"NCAAB": 0.1, "NHL": 0.0, "NFL": 0.0}
PJ_MEZCLA = 4  # con menos juegos de un equipo esta temporada, el motor no entra en la mezcla
SD_NCAAB = (11.3, 17.0)  # desviación del margen y del total (residuos del backtest con 6+ juegos)
NFL_B = (16.364, 0.704, 0.701, 0.058)  # margen = b0*epa_dif + b1*pts_dif + b2*local + b3 (temporadas 2012-2025)
NFL_BT = (0.658, 15.502)               # total = a*pts_tot + c
AVISOS = []


def _bajar(url, nombre):
    ruta = os.path.join(TMP, nombre)
    if not os.path.exists(ruta):
        with open(ruta, "wb") as f:
            f.write(bajar(url, timeout=180))
    return ruta


def temporada_actual(hoy):
    return hoy.year + 1 if hoy.month >= 8 else hoy.year


def _logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def mezclar(pm, pk, w):
    if pk is None:
        return pm
    if pm is None or w == 0:
        return pk
    return 1 / (1 + math.exp(-(w * _logit(pm) + (1 - w) * _logit(pk))))


# ---------------------------------------------------------------- NCAAB
def motor_ncaab(partidos, hoy):
    t = temporada_actual(hoy)
    for y in (t - 1, t):
        _bajar(f"{SDV}/espn_mens_college_basketball_team_boxscores/team_box_{y}.parquet", f"mbb_box_{y}.parquet")
        _bajar(f"{SDV}/espn_mens_college_basketball_schedules/mbb_schedule_{y}.parquet", f"mbb_sched_{y}.parquet")
    g = ncaab_datos.juegos([t - 1, t])
    G0, G1 = g[g.temporada == t - 1], g[g.temporada == t]
    previo = ncaab_motor.ajustar(G0, G0.fecha.max() + pd.Timedelta(days=1)) if len(G0) else None
    R = ncaab_motor.ajustar(G1, pd.Timestamp(hoy), previo["r"] if previo else None)
    cal = pd.read_parquet(os.path.join(TMP, f"mbb_sched_{t}.parquet"),
                          columns=["home_id", "away_id", "game_date", "neutral_site", "home_display_name", "away_display_name"])
    espn = {}
    for c in ("home", "away"):
        espn.update(dict(zip(cal[f"{c}_display_name"], pd.to_numeric(cal[f"{c}_id"]))))
    b = pd.read_parquet(os.path.join(TMP, f"mbb_box_{t - 1}.parquet"), columns=["team_display_name", "team_id"])
    for k, v in zip(b.team_display_name, b.team_id):
        espn.setdefault(k, v)
    neutral = {(int(h), int(a), str(d)[:10]): bool(n) for h, a, d, n in zip(pd.to_numeric(cal.home_id), pd.to_numeric(cal.away_id), cal.game_date, cal.neutral_site)}
    sal, sin = [], []
    for p in partidos:
        il, iv = nombres.ncaab(p["local"], espn), nombres.ncaab(p["visita"], espn)
        if il is None or iv is None:
            sin.append(p["local"] if il is None else p["visita"])
            continue
        fecha = p["inicio"][:10]
        neu = neutral.get((int(il), int(iv), fecha), False)
        pl, pv, pos = ncaab_motor.predecir(R, il, iv, neu)
        L, V = ncaab_motor.simular(pl, pv, pos, *SD_NCAAB, n=20000, rng=np.random.default_rng(zlib.crc32(f'{il}{iv}{fecha}'.encode())))
        r = ncaab_motor.resumen_sim(L, V)
        sal.append(dict(p_local=r["p_local"], pts_local=r["pts_local"], pts_visita=r["pts_visita"], posesiones=float(pos),
                        neutral=neu, pj_local=int(R["pj"].get(il, 0)), pj_visita=int(R["pj"].get(iv, 0)), _p=p,
                        id_local=int(il), id_visita=int(iv)))
    if sin:
        AVISOS.append("NCAAB sin equipo en los datos: " + ", ".join(sorted(set(sin))))
    # resultados para calificar: juegos terminados de la temporada (por ids y fecha)
    res = {(int(r.local), int(r.visita), r.fecha.strftime("%Y-%m-%d")): (int(r.pl), int(r.pv)) for r in G1.itertuples()}
    return sal, res


# ---------------------------------------------------------------- NHL
def motor_nhl(partidos, hoy):
    t = temporada_actual(hoy)
    gs = []
    for y in (t - 1, t):
        d = pd.read_parquet(_bajar(f"{SDV}/nhl_schedules/nhl_schedule_{y}.parquet", f"nhl_sched_{y}.parquet"))
        d = d[(d.game_type == "R") & d.home_score.notna() & d.game_state.isin(["OFF", "FINAL"])]
        gs.append(pd.DataFrame({"temporada": y, "fecha": pd.to_datetime(d.game_date), "local": d.home_team_abbr,
                                "visita": d.away_team_abbr, "gl": d.home_score.astype(int), "gv": d.away_score.astype(int)}))
    g = pd.concat(gs)
    G0, G1 = g[g.temporada == t - 1], g[g.temporada == t]
    previo = nhl_motor.ajustar(G0, G0.fecha.max() + pd.Timedelta(days=1)) if len(G0) else None
    R = nhl_motor.ajustar(G1, pd.Timestamp(hoy), previo) or previo
    sal, sin = [], []
    for p in partidos:
        al, av = nombres.NHL.get(p["local"]), nombres.NHL.get(p["visita"])
        if not al or not av:
            sin.append(p["local"] if not al else p["visita"])
            continue
        lh, la = nhl_motor.esperados(R, al, av)
        r = nhl_motor.probabilidades(lh, la)
        L, V = nhl_motor.simular(lh, la, 20000)
        top = pd.Series([f"{a}-{b}" for a, b in zip(L, V)]).value_counts(normalize=True).head(4)
        sal.append(dict(p_local=r["p_local"], pts_local=lh, pts_visita=la, p_prorroga=r["p_prorroga"],
                        p_local_m15=r["p_local_m15"], p_visita_m15=r["p_visita_m15"],
                        marcadores=", ".join(f"{k} {v * 100:.0f} %" for k, v in top.items()),
                        pj_local=int(R["pj"].get(al, 0)), pj_visita=int(R["pj"].get(av, 0)), _p=p, id_local=al, id_visita=av))
    if sin:
        AVISOS.append("NHL sin equipo: " + ", ".join(sorted(set(sin))))
    res = {(r.local, r.visita, r.fecha.strftime("%Y-%m-%d")): (int(r.gl), int(r.gv)) for r in G1.itertuples()}
    return sal, res


# ---------------------------------------------------------------- NFL
def motor_nfl(partidos, hoy):
    t = hoy.year if hoy.month >= 8 else hoy.year - 1
    _bajar(f"{NFLV}/schedules/games.csv", "nfl_games.csv")
    for y in (t - 1, t):
        _bajar(f"{NFLV}/pbp/play_by_play_{y}.parquet", f"nfl_pbp_{y}.parquet")
    g = nfl_motor.juegos()
    G0, G1 = g[g.season == t - 1], g[g.season == t]
    previo = nfl_motor.ajustar(G0, G0[G0.result.notna()].fecha.max() + pd.Timedelta(days=1))
    R = nfl_motor.ajustar(G1, pd.Timestamp(hoy), previo) or previo
    sim = nfl_motor.Simulador(pd.read_csv(os.path.join(os.path.dirname(__file__), "eeuu", "nfl_residuos.csv")))
    sal, sin = [], []
    for p in partidos:
        al, av = nombres.NFL.get(p["local"]), nombres.NFL.get(p["visita"])
        if not al or not av:
            sin.append(p["local"] if not al else p["visita"])
            continue
        fila = G1[(G1.home_team == al) & (G1.away_team == av)]
        neu = bool(fila.neutral.iloc[0]) if len(fila) else False
        f = nfl_motor.rasgos(R, al, av, neu)
        mu = NFL_B[0] * f["epa_dif"] + NFL_B[1] * f["pts_dif"] + NFL_B[2] * f["loc"] + NFL_B[3]
        tot = NFL_BT[0] * f["pts_tot"] + NFL_BT[1]
        r = sim.probabilidades(mu, tot)
        sal.append(dict(p_local=r["p_local"], pts_local=(tot + mu) / 2, pts_visita=(tot - mu) / 2, _p=p,
                        id_local=al, id_visita=av, pj_local=None, pj_visita=None))
    if sin:
        AVISOS.append("NFL sin equipo: " + ", ".join(sorted(set(sin))))
    res = {(r.home_team, r.away_team, r.fecha.strftime("%Y-%m-%d")): (int(r.home_score), int(r.away_score))
           for r in G1[G1.result.notna()].itertuples()}
    return sal, res


MOTORES = {"NCAAB": motor_ncaab, "NHL": motor_nhl, "NFL": motor_nfl}


def leer(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def correr():
    os.makedirs(TMP, exist_ok=True)
    pr = leer(os.path.join(DATOS, "precios.json"), {})
    ahora = datetime.now(timezone.utc)
    hoy = datetime.now(CARACAS).date()
    hist = leer(HIST, {"juegos": []})
    H = {x["id"]: x for x in hist["juegos"]}
    doc = {"generado": datetime.now(CARACAS).isoformat(timespec="minutes"), "mezcla": MEZCLA, "deportes": {}}
    for dep, fn in MOTORES.items():
        partidos = [p for l in pr.get("ligas", []) if l.get("deporte") == dep for p in l.get("partidos", [])]
        try:
            sal, res = fn(partidos, hoy)
        except Exception as e:  # noqa: BLE001 — un deporte roto no tumba a los demás
            AVISOS.append(f"{dep}: {type(e).__name__}: {e}")
            continue
        juegos = []
        for s in sal:
            p = s.pop("_p")
            lado_l = next((x for x in p["lados"] if x["clave"] == p["local"] or x["nombre"] == p["local"]), None)
            lado_v = next((x for x in p["lados"] if x["clave"] == p["visita"] or x["nombre"] == p["visita"]), None)
            pk = lado_l["p"] if lado_l else None
            w = MEZCLA[dep] if (s.get("pj_local") or 0) >= PJ_MEZCLA and (s.get("pj_visita") or 0) >= PJ_MEZCLA else 0.0
            pf = mezclar(s["p_local"], pk, w)
            lados = []
            for lado, pp in ((lado_l, pf), (lado_v, None if pf is None else 1 - pf)):
                if not lado or not lado.get("mejor"):
                    continue
                dec = lado["mejor"] / 100 + 1 if lado["mejor"] > 0 else 100 / -lado["mejor"] + 1
                lados.append({"nombre": lado["nombre"], "p_final": round(pp, 4), "ventaja_final": round(dec * pp - 1, 4),
                              "tipo_precio": lado.get("tipo") or ""})
            j = dict(local=p["local"], visita=p["visita"], inicio=p["inicio"], p_motor=round(s["p_local"], 4),
                     p_mercado=None if pk is None else round(pk, 4), p_final=round(pf, 4) if pf is not None else None,
                     pts_local=round(s["pts_local"], 1), pts_visita=round(s["pts_visita"], 1), lados=lados,
                     **{k: (round(v, 4) if isinstance(v, float) else v) for k, v in s.items()
                        if k not in ("p_local", "pts_local", "pts_visita", "id_local", "id_visita")})
            juegos.append(j)
            # historial: el pronóstico que vale es el último antes de empezar
            fecha_loc = p["inicio"][:10]
            hid = f"{dep}|{s['id_local']}|{s['id_visita']}|{fecha_loc}"
            if datetime.fromisoformat(p["inicio"]) > ahora:
                H[hid] = dict(id=hid, deporte=dep, fecha=fecha_loc, partido=f"{p['visita']} @ {p['local']}",
                              k_local=s["id_local"], k_visita=s["id_visita"], p_motor=j["p_motor"], p_mercado=j["p_mercado"],
                              p_final=j["p_final"], pts_local=j["pts_local"], pts_visita=j["pts_visita"],
                              marcador=H.get(hid, {}).get("marcador"), gano_local=H.get(hid, {}).get("gano_local"))
        # calificar con marcadores (la fecha de la fuente puede ir un día antes o después por la zona horaria)
        for x in H.values():
            if x["deporte"] != dep or x.get("marcador"):
                continue
            f0 = datetime.strptime(x["fecha"], "%Y-%m-%d").date()
            for dd in (0, -1, 1):
                k = (x["k_local"], x["k_visita"], (f0 + timedelta(days=dd)).isoformat())
                if dep == "NCAAB":
                    k = (int(k[0]), int(k[1]), k[2])
                if k in res:
                    gl, gv = res[k]
                    x["marcador"] = f"{gl}-{gv}"
                    x["gano_local"] = gl > gv
                    break
        juegos.sort(key=lambda j: j["inicio"])
        cal = [x for x in H.values() if x["deporte"] == dep and x.get("marcador") and x.get("p_mercado") is not None]

        def ll(campo):
            if not cal:
                return None
            return round(-sum(math.log(x[campo] if x["gano_local"] else 1 - x[campo]) for x in cal) / len(cal), 4)
        doc["deportes"][dep] = {"juegos": juegos, "calificados": len(cal), "ll_motor": ll("p_motor"),
                                "ll_mercado": ll("p_mercado"), "ll_final": ll("p_final"),
                                "acierto_motor": round(sum((x["p_motor"] > 0.5) == x["gano_local"] for x in cal) / len(cal), 3) if cal else None}
    doc["avisos"] = AVISOS
    lista = sorted(H.values(), key=lambda x: x["fecha"], reverse=True)
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump({"juegos": lista}, f, ensure_ascii=False, indent=0)
    doc["historial"] = lista[:600]
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("motores EE. UU.:", {d: len(v["juegos"]) for d, v in doc["deportes"].items()}, "| avisos:", AVISOS)


if __name__ == "__main__":
    correr()
