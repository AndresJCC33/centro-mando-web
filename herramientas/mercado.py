"""Hacia dónde se mueve el mercado, gratis y sin créditos.

Fuente: el marcador público de ESPN (site.api.espn.com), que trae para cada juego la línea de APERTURA y la ACTUAL
de su casa asociada (moneyline, hándicap y total). Cada corrida guarda además una foto propia, así se ve también
el movimiento de las últimas horas. Escribe datos/mercado.json y datos/mercado_fotos.json.

Uso: python herramientas/mercado.py [sondeo]
"""
import json
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from actualizar import bajar, CARACAS, DATOS  # noqa: E402

ESPN = "https://site.api.espn.com/apis/site/v2/sports"


def _limpio(x):
    if isinstance(x, dict):
        return {k: _limpio(v) for k, v in x.items() if k not in ("link", "logos", "team", "tracking", "links")}
    if isinstance(x, list):
        return [_limpio(v) for v in x]
    return x


def sondeo():
    hoy = datetime.now(CARACAS)
    for ruta in ("basketball/nba", "football/nfl", "football/college-football", "basketball/mens-college-basketball",
                 "hockey/nhl", "soccer/eng.1", "soccer/eng.2", "soccer/arg.1", "soccer/bra.1", "soccer/mex.1"):
        for k in (0, 1):
            f = (hoy + timedelta(days=k)).strftime("%Y%m%d")
            try:
                d = json.loads(bajar(f"{ESPN}/{ruta}/scoreboard?dates={f}&limit=300"))
            except Exception as e:  # noqa: BLE001
                print(ruta, f, "ERROR", e)
                continue
            evs = d.get("events", [])
            con = [e for e in evs if e["competitions"][0].get("odds")]
            print(ruta, f, len(evs), "juegos,", len(con), "con cuotas")
            if con and (k == 1 or ruta.startswith("soccer")):
                print(json.dumps(_limpio(con[0]["competitions"][0]["odds"]), ensure_ascii=False)[:2500])


if __name__ == "__main__":
    sondeo()
