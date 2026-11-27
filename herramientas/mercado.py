"""Hacia dónde se mueve el mercado, gratis y sin créditos.

Fuente: el marcador público de ESPN (site.api.espn.com), que trae para cada juego la línea de APERTURA y la ACTUAL
de DraftKings (ganador, hándicap y total). Cada corrida guarda además una foto propia de la línea, así se ve también
el movimiento de las últimas horas.

Ojo con la lectura: una línea se mueve por dinero fuerte (apostadores profesionales) o por noticias (lesiones,
alineaciones). Esta fuente no dice cuál de las dos fue; sí dice hacia dónde y cuánto.

Escribe datos/mercado.json (lo que lee la página) y datos/mercado_fotos.json (la foto de cada corrida).
Uso: python herramientas/mercado.py [sondeo]
"""
import difflib
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
from actualizar import bajar, CARACAS, DATOS  # noqa: E402

ESPN = "https://site.api.espn.com/apis/site/v2/sports"
SALIDA = os.path.join(DATOS, "mercado.json")
FOTOS = os.path.join(DATOS, "mercado_fotos.json")
# ruta de ESPN -> (deporte de la página, nombre de la liga como en Precios)
RUTAS = {
    "basketball/nba": ("NBA", "NBA"),
    "football/nfl": ("NFL", "NFL"),
    "football/college-football": ("NCAAF", "NCAAF"),
    "basketball/mens-college-basketball": ("NCAAB", "NCAAB"),
    "hockey/nhl": ("NHL", "NHL"),
    "soccer/uefa.champions": ("Fútbol", "Champions League"),
    "soccer/eng.1": ("Fútbol", "Inglaterra · Premier League"),
    "soccer/eng.2": ("Fútbol", "Inglaterra · Championship"),
    "soccer/eng.4": ("Fútbol", "Inglaterra · League Two"),
    "soccer/esp.1": ("Fútbol", "España · LaLiga"),
    "soccer/esp.2": ("Fútbol", "España · LaLiga 2"),
    "soccer/ger.1": ("Fútbol", "Alemania · Bundesliga"),
    "soccer/ger.2": ("Fútbol", "Alemania · 2. Bundesliga"),
    "soccer/ita.1": ("Fútbol", "Italia · Serie A"),
    "soccer/ita.2": ("Fútbol", "Italia · Serie B"),
    "soccer/fra.1": ("Fútbol", "Francia · Ligue 1"),
    "soccer/ned.1": ("Fútbol", "Países Bajos · Eredivisie"),
    "soccer/bel.1": ("Fútbol", "Bélgica · Pro League"),
    "soccer/aut.1": ("Fútbol", "Austria · Bundesliga"),
    "soccer/den.1": ("Fútbol", "Dinamarca · Superliga"),
    "soccer/gre.1": ("Fútbol", "Grecia · Super League"),
    "soccer/arg.1": ("Fútbol", "Argentina · Liga Profesional"),
    "soccer/bra.1": ("Fútbol", "Brasil · Serie A"),
    "soccer/mex.1": ("Fútbol", "México · Liga MX"),
    "soccer/jpn.1": ("Fútbol", "Japón · J1 League"),
}
# Umbrales para llamar «fuerte» a un movimiento (puntos de probabilidad del ganador; puntos de hándicap)
FUERTE_P = 0.04
FUERTE_HCP = {"NBA": 1.5, "NFL": 1.5, "NCAAF": 2.0, "NCAAB": 1.5}
RECIENTE_H = 3          # «en las últimas horas»
RECIENTE_P = 0.02


def am_dec(x):
    try:
        v = float(str(x).replace("+", ""))
    except (TypeError, ValueError):
        return None
    if str(x).upper() in ("EVEN", "EV"):
        v = 100
    if -100 < v < 100:
        return None
    return 1 + (v / 100 if v > 0 else 100 / -v)


def sin_margen(decs):
    """Probabilidad justa por el método de potencia (como en Precios)."""
    inv = [1 / d for d in decs]
    if sum(inv) <= 1:
        s = sum(inv)
        return [x / s for x in inv]
    lo, hi = 1.0, 10.0
    for _ in range(60):
        k = (lo + hi) / 2
        if sum(x ** k for x in inv) > 1:
            lo = k
        else:
            hi = k
    return [x ** k for x in inv]


def _linea(s):
    try:
        return float(re.sub(r"^[ou]", "", str(s)))
    except (TypeError, ValueError):
        return None


def _probs(ml, cual, tres):
    lados = ["home", "away"] + (["draw"] if tres else [])
    decs = [am_dec(((ml.get(l) or {}).get(cual) or {}).get("odds")) for l in lados]
    if any(d is None for d in decs):
        return None
    p = sin_margen(decs)
    return {"l": round(p[0], 4), "v": round(p[1], 4), **({"e": round(p[2], 4)} if tres else {})}


def leer_evento(ev, deporte, liga):
    comp = ev["competitions"][0]
    if not comp.get("odds"):
        return None
    od = comp["odds"][0]
    eq = {c["homeAway"]: c["team"] for c in comp["competitors"]}
    if "home" not in eq or "away" not in eq:
        return None
    ml = od.get("moneyline") or {}
    tres = deporte == "Fútbol"
    p0, p1 = _probs(ml, "open", tres), _probs(ml, "close", tres)
    ps = od.get("pointSpread") or {}
    tt = od.get("total") or {}
    h0, h1 = _linea(((ps.get("home") or {}).get("open") or {}).get("line")), _linea(((ps.get("home") or {}).get("close") or {}).get("line"))
    t0, t1 = _linea(((tt.get("over") or {}).get("open") or {}).get("line")), _linea(((tt.get("over") or {}).get("close") or {}).get("line"))
    if p1 is None and h1 is None:
        return None
    fav0 = "l" if (od.get("homeTeamOdds") or {}).get("favoriteAtOpen") else "v" if (od.get("awayTeamOdds") or {}).get("favoriteAtOpen") else None
    fav1 = "l" if (od.get("homeTeamOdds") or {}).get("favorite") else "v" if (od.get("awayTeamOdds") or {}).get("favorite") else None
    return {
        "id": ev["id"], "deporte": deporte, "liga": liga, "inicio": ev["date"],
        "estado": (comp.get("status") or ev.get("status") or {}).get("type", {}).get("state"),
        "local": eq["home"].get("displayName"), "visita": eq["away"].get("displayName"),
        "sl": eq["home"].get("abbreviation"), "sv": eq["away"].get("abbreviation"),
        "casa": (od.get("provider") or {}).get("displayName") or (od.get("provider") or {}).get("name"),
        "p0": p0, "p": p1, "hcp0": h0, "hcp": h1, "tot0": t0, "tot": t1,
        "volteo": bool(fav0 and fav1 and fav0 != fav1),
    }


# ---------------------------------------------------------------- unir con los nombres de la página
def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("st.", "saint").replace("utd", "united")
    quitar = {"fc", "cf", "afc", "sc", "ac", "cd", "ud", "club", "de", "the", "1", "sv", "vfb", "vfl", "rc"}
    return " ".join(t for t in re.findall(r"[a-z0-9]+", s) if t not in quitar)


def _parecido(a, b):
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    if ta <= tb or tb <= ta:
        return 0.9
    return difflib.SequenceMatcher(None, na, nb).ratio()


def nuestros_juegos():
    """(deporte, fecha, local, visita) de los juegos que muestra la página (análisis y precios)."""
    xs = []
    for ruta, clave in (("juegos_analisis.json", "juegos"),):
        try:
            for g in json.load(open(os.path.join(DATOS, ruta), encoding="utf-8"))[clave]:
                xs.append((g["deporte"], g["inicio"], g["local"], g["visita"]))
        except (OSError, ValueError, KeyError):
            pass
    try:
        for l in json.load(open(os.path.join(DATOS, "precios.json"), encoding="utf-8"))["ligas"]:
            for p in l["partidos"]:
                xs.append((l["deporte"], p["inicio"], p["local"], p["visita"]))
    except (OSError, ValueError, KeyError):
        pass
    return xs


def unir(j, nuestros):
    ini = datetime.fromisoformat(j["inicio"].replace("Z", "+00:00"))
    mejor, puntos = None, 0.0
    for dep, inicio, l, v in nuestros:
        if dep != j["deporte"]:
            continue
        try:
            if abs((datetime.fromisoformat(inicio) - ini).total_seconds()) > 14 * 3600:
                continue
        except ValueError:
            continue
        s = min(_parecido(j["local"], l), _parecido(j["visita"], v))
        if s > puntos:
            mejor, puntos = (l, v), s
    return mejor if puntos >= 0.72 else None


# ---------------------------------------------------------------- lectura del movimiento
def lectura(j):
    nombres = {"l": j["local"], "v": j["visita"], "e": "el empate"}
    out = {"hacia": None, "dp": 0.0, "fuerte": False, "texto": "", "total": None}
    if j["p0"] and j["p"]:
        d = {k: j["p"][k] - j["p0"][k] for k in j["p"]}
        k = max(d, key=d.get)
        out.update(hacia=k, dp=round(d[k], 4), nombre=nombres[k])
        if d[k] >= FUERTE_P:
            out["fuerte"] = True
    if j["hcp0"] is not None and j["hcp"] is not None:
        dh = j["hcp"] - j["hcp0"]   # hándicap del local: si baja, el mercado va con el local
        out["dhcp"] = round(dh, 2)
        if abs(dh) >= FUERTE_HCP.get(j["deporte"], 99):
            out["fuerte"] = True
            if out["hacia"] is None:
                out.update(hacia="l" if dh < 0 else "v", nombre=nombres["l" if dh < 0 else "v"])
    if j["tot0"] is not None and j["tot"] is not None and j["tot"] != j["tot0"]:
        out["total"] = "sube" if j["tot"] > j["tot0"] else "baja"
        out["dtot"] = round(j["tot"] - j["tot0"], 2)
    if j["volteo"]:
        out["fuerte"] = True
    return out


def correr():
    ahora = datetime.now(timezone.utc)
    hoy = ahora.astimezone(CARACAS).date()
    dias = {hoy.isoformat(), (hoy + timedelta(days=1)).isoformat()}
    try:
        fotos = json.load(open(FOTOS, encoding="utf-8"))
    except (OSError, ValueError):
        fotos = {}
    nuestros = nuestros_juegos()
    juegos, avisos = [], []
    for ruta, (dep, liga) in RUTAS.items():
        vistos = set()
        for k in (-1, 0, 1):
            f = (hoy + timedelta(days=k)).strftime("%Y%m%d")
            try:
                d = json.loads(bajar(f"{ESPN}/{ruta}/scoreboard?dates={f}&limit=400"
                                     + ("&groups=50" if ruta == "basketball/mens-college-basketball" else "")))
            except Exception as e:  # noqa: BLE001
                avisos.append(f"{liga} {f}: {type(e).__name__}")
                continue
            for ev in d.get("events", []):
                if ev["id"] in vistos:
                    continue
                vistos.add(ev["id"])
                j = leer_evento(ev, dep, liga)
                if not j:
                    continue
                ini = datetime.fromisoformat(j["inicio"].replace("Z", "+00:00"))
                if ini.astimezone(CARACAS).date().isoformat() not in dias or ini < ahora - timedelta(hours=4):
                    continue
                # foto propia (solo antes de empezar: en vivo la línea ya no es de apertura a cierre)
                fs = fotos.setdefault(j["id"], {"inicio": j["inicio"], "f": []})
                if j["estado"] == "pre" and j["p"]:
                    fs["f"].append([ahora.isoformat(timespec="minutes"), j["p"]["l"], j["hcp"], j["tot"]])
                    fs["f"] = fs["f"][-60:]
                serie = fs["f"]
                j["serie"] = [x[1] for x in serie]
                atras = [x for x in serie if datetime.fromisoformat(x[0]) <= ahora - timedelta(hours=RECIENTE_H)]
                if atras and j["p"]:
                    j["d3h"] = round(j["p"]["l"] - atras[-1][1], 4)   # cambio del local en las últimas horas
                j.update(lectura(j))
                j["reciente"] = bool(j.get("d3h") is not None and abs(j["d3h"]) >= RECIENTE_P)
                n = unir(j, nuestros)
                if n:
                    j["n_local"], j["n_visita"] = n
                juegos.append(j)
    # fotos de juegos viejos fuera
    fotos = {k: v for k, v in fotos.items()
             if datetime.fromisoformat(v["inicio"].replace("Z", "+00:00")) > ahora - timedelta(days=2)}
    juegos.sort(key=lambda j: j["inicio"])
    doc = {"generado": ahora.astimezone(CARACAS).isoformat(timespec="minutes"), "fuente": "ESPN (líneas de DraftKings)",
           "juegos": juegos, "avisos": avisos}
    with open(SALIDA, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    with open(FOTOS, "w", encoding="utf-8") as fh:
        json.dump(fotos, fh, ensure_ascii=False, separators=(",", ":"))
    from collections import Counter
    print("mercado:", len(juegos), "juegos", dict(Counter(j["deporte"] for j in juegos)),
          "| fuertes:", sum(j["fuerte"] for j in juegos), "| unidos a la página:", sum("n_local" in j for j in juegos),
          "| avisos:", avisos[:5])


def _limpio(x):
    if isinstance(x, dict):
        return {k: _limpio(v) for k, v in x.items() if k not in ("link", "logos", "team", "tracking", "links")}
    if isinstance(x, list):
        return [_limpio(v) for v in x]
    return x


def sondeo():
    hoy = datetime.now(CARACAS)
    for ruta in RUTAS:
        f = (hoy + timedelta(days=1)).strftime("%Y%m%d")
        try:
            d = json.loads(bajar(f"{ESPN}/{ruta}/scoreboard?dates={f}&limit=300"))
        except Exception as e:  # noqa: BLE001
            print(ruta, f, "ERROR", e)
            continue
        evs = d.get("events", [])
        print(ruta, f, len(evs), "juegos,", sum(bool(e["competitions"][0].get("odds")) for e in evs), "con cuotas")


if __name__ == "__main__":
    if sys.argv[1:] == ["sondeo"]:
        sondeo()
    else:
        correr()
