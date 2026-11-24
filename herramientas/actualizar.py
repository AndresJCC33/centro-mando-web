"""Actualiza los datos de la página:
  datos/vitrina.json     copia de CENTRO_MANDO/datos/vitrina.json en Drive (lo escribe el hub)
  datos/futbol_dia.json  análisis del día del motor de fútbol (UCL_ENGINE/salidas/ucl_AAAA-MM-DD.csv)
  datos/posiciones.json  tablas de posiciones con últimos 5, racha y promedios, calculadas de fuentes públicas:
                         NBA (cdn.nba.com), LVBP (statsapi.mlb.com) y ligas de fútbol (football-data.co.uk)
Cada fuente es independiente: si una falla, se conserva lo que ya había de esa liga y se avisa.
"""
import re
import csv
import io
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATOS = os.path.join(RAIZ, "datos")
CARACAS = timezone(timedelta(hours=-4))
AVISOS = []


def bajar(url, headers=None, datos=None, timeout=40):
    try:
        from curl_cffi import requests as creq
        if datos is None:
            r = creq.get(url, impersonate="chrome", timeout=timeout, headers=headers or {})
        else:
            r = creq.post(url, data=datos, timeout=timeout, headers=headers or {})
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} {(r.text or '')[:200]}")
        return r.content
    except ImportError:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(datos).encode() if datos else None,
                                     headers={"User-Agent": "Mozilla/5.0", **(headers or {})})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()


# ---------------------------------------------------------------- Drive
def bajar_vitrina():
    cid, sec, rt = (os.environ.get(k) for k in ("GDRIVE_CLIENT_ID", "GDRIVE_CLIENT_SECRET", "GDRIVE_REFRESH_TOKEN"))
    if not (cid and sec and rt):
        raise RuntimeError("faltan los secretos GDRIVE_CLIENT_ID, GDRIVE_CLIENT_SECRET y GDRIVE_REFRESH_TOKEN")
    tok = json.loads(bajar("https://oauth2.googleapis.com/token", datos={
        "client_id": cid, "client_secret": sec, "refresh_token": rt, "grant_type": "refresh_token"}))["access_token"]
    h = {"Authorization": f"Bearer {tok}"}

    def listar(q):
        url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
            {"q": q, "fields": "files(id,name,modifiedTime)", "orderBy": "modifiedTime desc", "pageSize": 10})
        return json.loads(bajar(url, headers=h))["files"]

    cm = listar("name = 'CENTRO_MANDO' and 'root' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    if not cm:
        raise RuntimeError("no encontré CENTRO_MANDO en Drive")
    dat = listar(f"name = 'datos' and '{cm[0]['id']}' in parents and trashed = false")
    if not dat:
        raise RuntimeError("no encontré CENTRO_MANDO/datos")
    vit = listar(f"name = 'vitrina.json' and '{dat[0]['id']}' in parents and trashed = false")
    if not vit:
        raise RuntimeError("no encontré vitrina.json")
    cuerpo = bajar(f"https://www.googleapis.com/drive/v3/files/{vit[0]['id']}?alt=media", headers=h)
    doc = json.loads(cuerpo)
    faltan = {"picks", "previa", "motores"} - set(doc.get("tablas", {}))
    if faltan:
        raise RuntimeError(f"vitrina.json sin las tablas {sorted(faltan)}")
    with open(os.path.join(DATOS, "vitrina.json"), "wb") as f:
        f.write(cuerpo)
    try:
        print("fútbol del día:", bajar_futbol(listar, h))
    except Exception as e:  # noqa: BLE001
        AVISOS.append(f"fútbol del día: {type(e).__name__}: {e}")
    return doc.get("generado")


CAMPOS_FUTBOL = ["competicion", "partido", "local", "visita", "confianza", "referencia", "pL", "pE", "pV",
                 "mL", "mE", "mV", "mkL", "mkE", "mkV", "EV_L", "EV_E", "EV_V", "justa_L", "justa_E", "justa_V",
                 "O15", "O25", "O35", "U25", "BTTS", "O25_justa", "U25_justa", "xG_L", "xG_V",
                 "marcadores_top5", "tipo_pick", "pick_txt", "pick_ev", "pick_prob", "razon", "tot_pick_txt"]


def bajar_futbol(listar, h):
    """Análisis del día del motor de fútbol: la tabla ucl_AAAA-MM-DD.csv más reciente de UCL_ENGINE/salidas."""
    raiz = listar("name = 'UCL_ENGINE' and 'root' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false")
    if not raiz:
        raise RuntimeError("no encontré UCL_ENGINE")
    sal = listar(f"name = 'salidas' and '{raiz[0]['id']}' in parents and trashed = false")
    if not sal:
        raise RuntimeError("no encontré UCL_ENGINE/salidas")
    xs = [x for x in listar(f"name contains 'ucl_20' and '{sal[0]['id']}' in parents and trashed = false")
          if re.fullmatch(r"ucl_\d{4}-\d{2}-\d{2}\.csv", x["name"])]
    if not xs:
        raise RuntimeError("no hay ucl_AAAA-MM-DD.csv")
    x = max(xs, key=lambda x: x["name"])
    texto = bajar(f"https://www.googleapis.com/drive/v3/files/{x['id']}?alt=media", headers=h).decode("utf-8-sig")
    partidos = []
    for r in csv.DictReader(io.StringIO(texto)):
        d = {}
        for k in CAMPOS_FUTBOL:
            v = (r.get(k) or "").strip()
            if v in ("", "nan", "NaN"):
                d[k] = None
                continue
            try:
                d[k] = float(v) if k not in ("competicion", "partido", "local", "visita", "confianza", "referencia",
                                             "marcadores_top5", "tipo_pick", "pick_txt", "razon", "tot_pick_txt") else v
            except ValueError:
                d[k] = v
        partidos.append(d)
    fecha = x["name"][4:14]
    doc = {"fecha": fecha, "archivo_modificado": x["modifiedTime"], "partidos": partidos}
    with open(os.path.join(DATOS, "futbol_dia.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    return f"{fecha} ({len(partidos)} partidos)"


# ---------------------------------------------------------------- posiciones
def tabla(juegos, empates=False, nombres=None):
    """juegos: [(fecha, local, visitante, pts_local, pts_visitante)] ya terminados, en cualquier orden."""
    eq = {}
    for fecha, loc, vis, pl, pv in sorted(juegos, key=lambda j: j[0]):
        for yo, rival, pf, pc, casa in ((loc, vis, pl, pv, True), (vis, loc, pv, pl, False)):
            e = eq.setdefault(yo, {"pj": 0, "g": 0, "e": 0, "p": 0, "pf": 0, "pc": 0, "gl": 0, "pl": 0, "gv": 0, "pv": 0, "res": []})
            r = "G" if pf > pc else "P" if pf < pc else "E"
            e["pj"] += 1
            e["pf"] += pf
            e["pc"] += pc
            e[{"G": "g", "P": "p", "E": "e"}[r]] += 1
            if r != "E":
                e[("g" if r == "G" else "p") + ("l" if casa else "v")] += 1
            e["res"].append(r)
    filas = []
    for nombre, e in eq.items():
        racha = 1
        for r in reversed(e["res"][:-1]):
            if r != e["res"][-1]:
                break
            racha += 1
        f = {"equipo": (nombres or {}).get(nombre, nombre), "pj": e["pj"], "g": e["g"], "p": e["p"],
             "ult5": "".join(e["res"][-5:]), "racha": f"{e['res'][-1]}{racha}",
             "casa": f"{e['gl']}-{e['pl']}", "visita": f"{e['gv']}-{e['pv']}",
             "pf": round(e["pf"] / e["pj"], 1), "pc": round(e["pc"] / e["pj"], 1),
             "dif": e["pf"] - e["pc"]}
        if empates:
            f["e"] = e["e"]
            f["pts"] = 3 * e["g"] + e["e"]
        else:
            f["pct"] = round(e["g"] / e["pj"], 3)
        filas.append(f)
    clave = (lambda f: (-f["pts"], -f["dif"], -f["pf"])) if empates else (lambda f: (-f["pct"], -f["g"], -f["dif"]))
    return sorted(filas, key=clave)


def nba():
    ls = json.loads(bajar("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json",
                          headers={"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"}, timeout=60))["leagueSchedule"]
    juegos, conf = [], {}
    for d in ls["gameDates"]:
        for g in d["games"]:
            if not str(g.get("gameId", "")).startswith("002") or g.get("gameStatus") != 3:
                continue
            h, a = g["homeTeam"], g["awayTeam"]
            juegos.append((g["gameDateTimeUTC"], h["teamTricode"], a["teamTricode"], int(h["score"]), int(a["score"])))
    if not juegos:
        raise RuntimeError("calendario NBA sin juegos terminados")
    return [{"liga": "NBA", "deporte": "NBA", "temporada": str(ls.get("seasonYear", "")), "empates": False,
             "unidad": "puntos", "equipos": tabla(juegos)}]


def lvbp():
    hoy = datetime.now(CARACAS).date()
    ini = hoy.replace(month=10, day=1) if hoy.month >= 9 else hoy.replace(year=hoy.year - 1, month=10, day=1)
    url = ("https://statsapi.mlb.com/api/v1/schedule?sportId=17&leagueId=135&gameType=R"
           f"&startDate={ini}&endDate={hoy}")
    js = json.loads(bajar(url))
    juegos = []
    for d in js.get("dates", []):
        for g in d.get("games", []):
            if g.get("status", {}).get("codedGameState") != "F":
                continue
            h, a = g["teams"]["home"], g["teams"]["away"]
            if h.get("score") is None or a.get("score") is None:
                continue
            juegos.append((g["gameDate"], h["team"]["name"], a["team"]["name"], int(h["score"]), int(a["score"])))
    if not juegos:
        raise RuntimeError("calendario LVBP sin juegos terminados")
    return [{"liga": "LVBP", "deporte": "LVBP", "temporada": f"{ini.year}-{str(ini.year + 1)[2:]}", "empates": False,
             "unidad": "carreras", "equipos": tabla(juegos)}]


FUTBOL = {"Premier": "E0", "LaLiga": "SP1", "Bundesliga": "D1", "Serie A": "I1", "Ligue 1": "F1"}


def futbol():
    hoy = datetime.now(CARACAS).date()
    a = hoy.year if hoy.month >= 7 else hoy.year - 1
    temp = f"{str(a)[2:]}{str(a + 1)[2:]}"
    ligas = []
    for liga, cod in FUTBOL.items():
        try:
            txt = bajar(f"https://www.football-data.co.uk/mmz4281/{temp}/{cod}.csv").decode("utf-8-sig", "replace")
            juegos = []
            for r in csv.DictReader(io.StringIO(txt)):
                if not r.get("HomeTeam") or r.get("FTHG") in (None, "") or r.get("FTAG") in (None, ""):
                    continue
                f = datetime.strptime(r["Date"], "%d/%m/%Y" if len(r["Date"]) == 10 else "%d/%m/%y").strftime("%Y-%m-%d")
                juegos.append((f, r["HomeTeam"], r["AwayTeam"], int(r["FTHG"]), int(r["FTAG"])))
            if not juegos:
                raise RuntimeError("sin partidos")
            ligas.append({"liga": liga, "deporte": "Fútbol", "temporada": f"{a}-{str(a + 1)[2:]}", "empates": True,
                          "unidad": "goles", "equipos": tabla(juegos, empates=True)})
        except Exception as e:  # noqa: BLE001
            AVISOS.append(f"{liga}: {type(e).__name__}: {e}")
    return ligas


def main():
    os.makedirs(DATOS, exist_ok=True)
    ok = True
    if "--sin-drive" not in sys.argv:
        try:
            print("vitrina.json del hub:", bajar_vitrina())
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"ERROR vitrina: {type(e).__name__}: {e}")
    ruta = os.path.join(DATOS, "posiciones.json")
    previo = {l["liga"]: l for l in json.load(open(ruta, encoding="utf-8")).get("ligas", [])} if os.path.exists(ruta) else {}
    nuevas = {}
    for nombre, fn in (("NBA", nba), ("LVBP", lvbp), ("Fútbol", futbol)):
        try:
            for l in fn():
                ant = previo.get(l["liga"])
                igual = ant and {k: v for k, v in ant.items() if k != "actualizado"} == l
                l["actualizado"] = ant["actualizado"] if igual else datetime.now(CARACAS).strftime("%Y-%m-%d %H:%M")
                nuevas[l["liga"]] = l
        except Exception as e:  # noqa: BLE001
            AVISOS.append(f"{nombre}: {type(e).__name__}: {e}")
    ligas = {**previo, **nuevas}
    orden = ["NBA", "LVBP", *FUTBOL]
    doc = {"ligas": [ligas[k] for k in orden if k in ligas]}
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("posiciones:", ", ".join(f"{l['liga']} ({len(l['equipos'])} equipos)" for l in doc["ligas"]) or "ninguna")
    for a in AVISOS:
        print("AVISO:", a)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
