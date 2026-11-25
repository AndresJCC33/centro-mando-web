"""Vigilante de precios: cuotas de Pinnacle y de casas blandas (The Odds API) para ligas elegidas.

Por cada partido publica el pronóstico (probabilidad justa de Pinnacle, sin margen), la cuota justa, la cuota mínima
que tendría que pagar JEL para que valga la pena (justa x (1 + VENTAJA)) y los picks de valor: casas blandas que pagan
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
# deporte en The Odds API -> (nombre en la página, deporte de la página, mercados)
LIGAS = {
    "soccer_greece_super_league": ("Grecia · Super League", "Fútbol", "h2h"),
    "soccer_netherlands_eredivisie": ("Países Bajos · Eredivisie", "Fútbol", "h2h"),
    "soccer_spain_segunda_division": ("España · LaLiga 2", "Fútbol", "h2h"),
    "soccer_germany_bundesliga2": ("Alemania · 2. Bundesliga", "Fútbol", "h2h"),
    "basketball_ncaab": ("NCAAB", "NCAAB", "h2h"),
}
SHARP = "pinnacle"
REGIONES = "eu,uk"
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


if __name__ == "__main__":
    if sys.argv[1:] == ["sondeo"]:
        sondeo()
