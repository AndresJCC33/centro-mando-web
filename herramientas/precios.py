"""Vigilante de precios: cuotas de Pinnacle y de casas blandas (The Odds API) para ligas elegidas.

Por cada partido publica el pronóstico (probabilidad justa de Pinnacle, sin margen), la cuota justa, la cuota mínima
que tendría que pagar tu casa para que valga la pena (justa x (1 + VENTAJA)) y los picks de valor: casas blandas que pagan
VENTAJA o más sobre el precio justo de Pinnacle. Guarda cada pick, toma la última foto antes del partido como cierre
(CLV) y lo califica con los marcadores de The Odds API.

Uso:  python herramientas/precios.py sondeo      (ver créditos y casas disponibles; gasta 2 créditos)
      python herramientas/precios.py             (corrida normal)
Escribe datos/precios.json y datos/precios_historial.json.
"""
import json
import os
import sys
import urllib.parse
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from actualizar import bajar, CARACAS, DATOS  # noqa: E402

API = "https://api.the-odds-api.com/v4"
VENTAJA = 0.04
VENTAJA_MAX = 0.15
# «Valor probado» (desde el 25-nov-2026): probabilidad de 25 % a 45 % y la casa paga 3 % o más sobre el precio justo.
# En 7 temporadas de 22 ligas de fútbol (football-data, mejor cuota contra Pinnacle de apertura sin margen por el
# método de potencia) ese tramo dio ROI de +4,0 % en 3.841 apuestas; los batacazos de menos de 12 % perdieron.
VENTAJA_VP = 0.03
PROB_VP = 0.25
# deporte en The Odds API -> (nombre en la página, deporte de la página, mercados)
LIGAS = {
    "soccer_uefa_champs_league": ("Champions League", "Fútbol", "h2h"),
    "soccer_epl": ("Inglaterra · Premier League", "Fútbol", "h2h"),
    "soccer_spain_la_liga": ("España · LaLiga", "Fútbol", "h2h"),
    "soccer_germany_bundesliga": ("Alemania · Bundesliga", "Fútbol", "h2h"),
    "soccer_italy_serie_a": ("Italia · Serie A", "Fútbol", "h2h"),
    "soccer_france_ligue_one": ("Francia · Ligue 1", "Fútbol", "h2h"),
    "soccer_greece_super_league": ("Grecia · Super League", "Fútbol", "h2h"),
    "soccer_netherlands_eredivisie": ("Países Bajos · Eredivisie", "Fútbol", "h2h"),
    "soccer_spain_segunda_division": ("España · LaLiga 2", "Fútbol", "h2h"),
    "soccer_germany_bundesliga2": ("Alemania · 2. Bundesliga", "Fútbol", "h2h"),
    "basketball_ncaab": ("NCAAB", "NCAAB", "h2h"),
    "icehockey_nhl": ("NHL", "NHL", "h2h"),
    "americanfootball_nfl": ("NFL", "NFL", "h2h"),
}
# Si quedan menos créditos que esto, el vigilante se detiene para no dejar sin cuotas a la cartelera automática.
RESERVA_CREDITOS = 60
SHARP = "pinnacle"
REGIONES = "eu"
NO_BLANDAS = {"pinnacle", "everygame", "gtbets", "betfair_ex_eu", "betfair_ex_uk", "betfair_ex_au", "smarkets", "matchbook", "betonlineag", "lowvig"}
PROB_MIN = 0.45
HORAS = 96
HIST = os.path.join(DATOS, "precios_historial.json")
SALIDA = os.path.join(DATOS, "precios.json")


def clave_odds():
    cid, sec, rt = (os.environ.get(k) for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))
    tok = json.loads(bajar("https://oauth2.googleapis.com/token", datos={
        "client_id": cid, "client_secret": sec, "refresh_token": rt, "grant_type": "refresh_token"}))["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    def listar(q):
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
            {"q": q, "fields": "files(id,name)", "pageSize": 10})
        return json.loads(bajar(url, headers=h))["files"]

    cm = listar("name = 'CENTRO_MANDO' and 'root' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    cf = listar(f"name = 'config' and '{cm[0]['id']}' in parents and trashed = false")
    k = listar(f"name = 'odds_api_key.txt' and '{cf[0]['id']}' in parents and trashed = false")
    return bajar(f"https://www.googleapis.com/drive/v3/files/{k[0]['id']}?alt=media", headers=h).decode().strip()


def api(ruta, clave, **params):
    from curl_cffi import requests as creq
    params["apiKey"] = clave
    r = creq.get(f"{API}{ruta}?" + urllib.parse.urlencode(params), timeout=40)
    info = {k: r.headers.get(k) for k in ("x-requests-remaining", "x-requests-used", "x-requests-last")}
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json(), info


def sondeo():
    clave = clave_odds()
    deportes, info = api("/sports", clave, all="true")
    claves = {d["key"] for d in deportes}
    print("créditos:", info)
    for k in LIGAS:
        print(k, "OK" if k in claves else "NO ESTÁ")
    datos, info = api("/sports/soccer_greece_super_league/odds", clave, regions=REGIONES, markets="h2h", oddsFormat="decimal")
    print("créditos tras una llamada:", info)
    casas = sorted({b["key"] for e in datos for b in e["bookmakers"]})
    print("partidos:", len(datos), "casas:", casas)
    datos, info = api("/sports/basketball_ncaab/odds", clave, regions=REGIONES, markets="h2h", oddsFormat="decimal")
    print("NCAAB partidos:", len(datos), "con pinnacle:", sum(any(b["key"] == SHARP for b in e["bookmakers"]) for e in datos),
          "casas:", sorted({b["key"] for e in datos for b in e["bookmakers"]}), info)


def am(dec):
    if dec is None or dec <= 1:
        return None
    return round((dec - 1) * 100) if dec >= 2 else round(-100 / (dec - 1))


def leer(path, defecto):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return defecto


def sin_margen(inv):
    """Probabilidad justa por el método de potencia: p_i = (1/cuota_i)^k con k tal que sumen 1. A diferencia del
    reparto proporcional, no le regala probabilidad a los batacazos (sesgo favorito-batacazo)."""
    lo, hi = 1.0, 3.0
    for _ in range(60):
        k = (lo + hi) / 2
        if sum(v ** k for v in inv.values()) > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    tot = sum(v ** k for v in inv.values())
    return {n: v ** k / tot for n, v in inv.items()}


def analizar_evento(e, ahora):
    pin = next((b for b in e["bookmakers"] if b["key"] == SHARP), None)
    if pin is None:
        return None
    mk = next((m for m in pin["markets"] if m["key"] == "h2h"), None)
    if mk is None or len(mk["outcomes"]) < 2:
        return None
    inv = {o["name"]: 1 / o["price"] for o in mk["outcomes"] if o.get("price", 0) > 1}
    justa = sin_margen(inv)
    blandas = {}
    for b in e["bookmakers"]:
        if b["key"] in NO_BLANDAS:
            continue
        m = next((m for m in b["markets"] if m["key"] == "h2h"), None)
        if not m:
            continue
        # Mismo mercado que Pinnacle: en hockey algunas casas dan a 3 vías (90 minutos con empate) y su cuota
        # de cada equipo no es comparable con la de Pinnacle, que incluye la prórroga.
        if len(m["outcomes"]) != len(mk["outcomes"]) or {o["name"] for o in m["outcomes"]} != set(inv):
            continue
        for o in m["outcomes"]:
            blandas.setdefault(o["name"], []).append((o["price"], b["title"]))
    orden = [e["home_team"]] + (["Draw"] if "Draw" in justa else []) + [e["away_team"]]
    lados = []
    for nombre in orden:
        p = justa.get(nombre)
        if p is None:
            continue
        ofertas = sorted(blandas.get(nombre, []), reverse=True)
        mejor, casa = (ofertas[0] if ofertas else (None, None))
        ventaja = mejor * p - 1 if mejor else None
        if ventaja is not None and ventaja > VENTAJA_MAX:  # más que esto es casi siempre un error de la casa o del mercado
            ofertas = [(c, k) for c, k in ofertas if c * p - 1 <= VENTAJA_MAX]
            mejor, casa = (ofertas[0] if ofertas else (None, None))
            ventaja = mejor * p - 1 if mejor else None
        n_valor = sum(1 for c, _ in ofertas if c * p - 1 >= VENTAJA)
        tipo = ""
        if ventaja is not None and ventaja >= VENTAJA and p >= PROB_MIN:
            tipo = "PICK CONFIABLE"
        elif ventaja is not None and ventaja >= VENTAJA_VP and p >= PROB_VP:
            tipo = "VALOR PROBADO"
        elif ventaja is not None and ventaja >= VENTAJA:
            tipo = "VALOR SIN CONFIANZA"
        lados.append(dict(nombre="Empate" if nombre == "Draw" else nombre, clave=nombre, p=round(p, 4),
                          justa=am(1 / p), minima=am((1 / p) * (1 + VENTAJA)), minima_vp=am((1 / p) * (1 + VENTAJA_VP)),
                          mejor=am(mejor) if mejor else None, casa=casa, ventaja=round(ventaja, 4) if ventaja is not None else None,
                          casas_con_valor=n_valor, casas=len(ofertas), tipo=tipo))
    inicio = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
    return dict(id=e["id"], inicio=inicio.astimezone(CARACAS).isoformat(timespec="minutes"), local=e["home_team"],
                visita=e["away_team"], lados=lados, empezado=inicio <= ahora)


def ganador(ev):
    sc = {s["name"]: float(s["score"]) for s in (ev.get("scores") or []) if s.get("score") not in (None, "")}
    if len(sc) < 2 or not ev.get("completed"):
        return None, None
    a, b = ev["home_team"], ev["away_team"]
    marcador = f"{int(sc.get(a, 0))}-{int(sc.get(b, 0))}"
    if sc.get(a) == sc.get(b):
        return "Draw", marcador
    return (a if sc.get(a, 0) > sc.get(b, 0) else b), marcador


def correr():
    clave = clave_odds()
    ahora = datetime.now(timezone.utc)
    hist = leer(HIST, {"picks": []})
    picks = {p["id"]: p for p in hist["picks"]}
    ligas, creditos, avisos = [], None, []
    for k, (nombre, deporte, mercados) in LIGAS.items():
        try:
            datos, info = api(f"/sports/{k}/odds", clave, regions=REGIONES, markets=mercados, oddsFormat="decimal")
            creditos = info.get("x-requests-remaining")
        except Exception as ex:  # noqa: BLE001
            avisos.append(f"{nombre}: {ex}")
            continue
        if creditos is not None and float(creditos) < RESERVA_CREDITOS:
            avisos.append(f"Quedan {creditos} créditos de The Odds API: me detuve en {nombre} para guardar la reserva.")
            parar = True
        else:
            parar = False
        partidos = []
        for e in datos:
            inicio = datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00"))
            a = analizar_evento(e, ahora)
            if a is None:
                continue
            # foto de cierre para los picks guardados de este partido (la última antes de empezar)
            if inicio > ahora:
                for l in a["lados"]:
                    pid = f"{e['id']}|{l['clave']}"
                    if pid in picks and picks[pid]["resultado"] == "PENDIENTE":
                        picks[pid]["p_cierre"] = l["p"]
                        picks[pid]["foto_cierre"] = ahora.astimezone(CARACAS).isoformat(timespec="minutes")
                        picks[pid]["clv"] = round(picks[pid]["cuota_dec"] * l["p"] - 1, 4)
            if inicio > ahora + timedelta(hours=HORAS) or inicio <= ahora:
                continue
            partidos.append(a)
            for l in a["lados"]:
                pid = f"{e['id']}|{l['clave']}"
                if l["tipo"] and pid not in picks:
                    dec = (1 + l["ventaja"]) / l["p"]
                    picks[pid] = dict(id=pid, evento=e["id"], deporte_api=k, liga=nombre, deporte=deporte,
                                      fecha=a["inicio"][:10], inicio=a["inicio"], partido=f"{a['local']} vs {a['visita']}",
                                      seleccion=l["nombre"], clave=l["clave"], cuota=l["mejor"], cuota_dec=round(dec, 3),
                                      casa=l["casa"], p_justa=l["p"], ventaja=l["ventaja"], tipo=l["tipo"],
                                      detectado=ahora.astimezone(CARACAS).isoformat(timespec="minutes"),
                                      p_cierre=l["p"], clv=round(dec * l["p"] - 1, 4), resultado="PENDIENTE",
                                      marcador="", unidades=None)
        partidos.sort(key=lambda x: x["inicio"])
        ligas.append(dict(clave=k, nombre=nombre, deporte=deporte, partidos=partidos))
        if parar:
            break
    # Calificar con marcadores (solo deportes con picks ya jugados hace más de 3 horas)
    por_calificar = {p["deporte_api"] for p in picks.values() if p["resultado"] == "PENDIENTE"
                     and datetime.fromisoformat(p["inicio"]) < ahora - timedelta(hours=3)}
    for k in sorted(por_calificar):
        try:
            evs, info = api(f"/sports/{k}/scores", clave, daysFrom=3)
            creditos = info.get("x-requests-remaining")
        except Exception as ex:  # noqa: BLE001
            avisos.append(f"marcadores {k}: {ex}")
            continue
        res = {ev["id"]: ganador(ev) for ev in evs}
        for p in picks.values():
            if p["deporte_api"] == k and p["resultado"] == "PENDIENTE" and res.get(p["evento"], (None, None))[0]:
                g, marc = res[p["evento"]]
                p["marcador"] = marc
                p["resultado"] = "GANADO" if g == p["clave"] else "PERDIDO"
                p["unidades"] = round(p["cuota_dec"] - 1, 3) if p["resultado"] == "GANADO" else -1.0
    lista = sorted(picks.values(), key=lambda p: p["inicio"], reverse=True)
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump({"picks": lista}, f, ensure_ascii=False, indent=0)
    doc = dict(generado=ahora.astimezone(CARACAS).isoformat(timespec="minutes"), ventaja=VENTAJA, prob_min=PROB_MIN,
               creditos_restantes=creditos, avisos=avisos, ligas=ligas, picks=lista[:400])
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("créditos restantes:", creditos, "| ligas:", [(l["nombre"], len(l["partidos"])) for l in ligas],
          "| picks guardados:", len(lista), "| avisos:", avisos)


if __name__ == "__main__":
    if sys.argv[1:] == ["sondeo"]:
        sondeo()
    else:
        correr()
