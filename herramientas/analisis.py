"""Análisis por partido: estadísticas reales de cada equipo para la página (datos/analisis.json).

Fútbol (football-data.co.uk, temporada en curso): goles, tiros, tiros al arco, córners, faltas, tarjetas,
  más de 2.5 y ambos anotan, en casa y fuera, y los últimos 5 resultados. Une los nombres de The Odds API
  (vigilante de precios) con los de football-data.
NBA (boxscores oficiales de cdn.nba.com): puntos, rebotes, asistencias, triples, pérdidas, faltas, robos y tapones
  a favor y en contra por partido; los últimos 5; y los promedios de los jugadores que más minutos juegan.
LVBP (statsapi.mlb.com): carreras, hits, jonrones, ponches y boletos por juego, a favor y en contra.

Las cajas de NBA y LVBP se guardan en datos/cache/ para bajar solo los juegos nuevos.
Uso: python herramientas/analisis.py   (lo llama también actualizar.py)
"""
import csv
import difflib
import io
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from actualizar import bajar, CARACAS, DATOS  # noqa: E402

SALIDA = os.path.join(DATOS, "analisis.json")
CACHE = os.path.join(DATOS, "cache")
NBA_H = {"Referer": "https://www.nba.com/", "Origin": "https://www.nba.com"}
MAX_NUEVOS = 150  # cajas nuevas por corrida (la primera vez se pone al día en dos o tres corridas)

# ---------------------------------------------------------------- fútbol
LIGAS_FD = {"E0": "Premier", "E1": "Championship", "SP1": "LaLiga", "SP2": "LaLiga 2", "D1": "Bundesliga",
            "D2": "2. Bundesliga", "I1": "Serie A", "I2": "Serie B", "F1": "Ligue 1", "F2": "Ligue 2",
            "N1": "Eredivisie", "P1": "Portugal", "T1": "Turquia", "B1": "Belgica", "G1": "Grecia", "SC0": "Escocia",
            "E3": "League Two",
            # ligas «extra» de football-data (archivo new/<país>.csv: solo goles, sin tiros ni tarjetas)
            "ARG": "Argentina", "BRA": "Brasil", "AUT": "Austria", "DNK": "Dinamarca", "MEX": "Mexico", "JPN": "Japon"}
# liga principal dentro del archivo extra (el de Argentina trae también la Copa de la Liga)
EXTRA_FD = {"ARG": "Liga Profesional", "BRA": "Serie A", "AUT": "Bundesliga", "DNK": "Superliga", "MEX": "Liga MX",
            "JPN": "J1 League"}
# deporte de The Odds API -> liga de football-data (para buscar el nombre solo dentro de esa liga)
API_FD = {"soccer_epl": "E0", "soccer_spain_la_liga": "SP1", "soccer_germany_bundesliga": "D1",
          "soccer_italy_serie_a": "I1", "soccer_france_ligue_one": "F1", "soccer_netherlands_eredivisie": "N1",
          "soccer_greece_super_league": "G1", "soccer_spain_segunda_division": "SP2", "soccer_germany_bundesliga2": "D2",
          "soccer_efl_champ": "E1", "soccer_england_league2": "E3", "soccer_belgium_first_div": "B1",
          "soccer_italy_serie_b": "I2", "soccer_argentina_primera_division": "ARG", "soccer_brazil_campeonato": "BRA",
          "soccer_austria_bundesliga": "AUT", "soccer_denmark_superliga": "DNK", "soccer_mexico_ligamx": "MEX",
          "soccer_japan_j_league": "JPN"}
# nombre en The Odds API -> nombre en football-data, cuando la búsqueda aproximada no basta
ALIAS = {
    "Manchester City": "Man City", "Manchester United": "Man United", "Wolverhampton Wanderers": "Wolves",
    "Nottingham Forest": "Nott'm Forest", "Brighton and Hove Albion": "Brighton", "Tottenham Hotspur": "Tottenham",
    "Newcastle United": "Newcastle", "West Ham United": "West Ham", "Leeds United": "Leeds",
    "Sheffield United": "Sheffield United", "Paris Saint Germain": "Paris SG", "Paris Saint-Germain": "Paris SG",
    "Bayern Munich": "Bayern Munich", "Borussia Dortmund": "Dortmund", "Bayer Leverkusen": "Leverkusen",
    "Borussia Monchengladbach": "M'gladbach", "Eintracht Frankfurt": "Ein Frankfurt", "1. FC Köln": "FC Koln",
    "FC Koln": "FC Koln", "1. FC Heidenheim": "Heidenheim", "FSV Mainz 05": "Mainz", "TSG Hoffenheim": "Hoffenheim",
    "VfB Stuttgart": "Stuttgart", "VfL Wolfsburg": "Wolfsburg", "VfL Bochum": "Bochum", "SC Freiburg": "Freiburg",
    "FC St. Pauli": "St Pauli", "Union Berlin": "Union Berlin", "Hamburger SV": "Hamburg", "Werder Bremen": "Werder Bremen",
    "Atlético Madrid": "Ath Madrid", "Atletico Madrid": "Ath Madrid", "Athletic Bilbao": "Ath Bilbao",
    "Celta Vigo": "Celta", "Real Sociedad": "Sociedad", "Rayo Vallecano": "Vallecano", "Espanyol": "Espanol",
    "Real Betis": "Betis", "Deportivo Alavés": "Alaves", "Alavés": "Alaves", "CA Osasuna": "Osasuna",
    "Inter Milan": "Inter", "AC Milan": "Milan", "AS Roma": "Roma", "SSC Napoli": "Napoli", "Hellas Verona": "Verona",
    "Paris FC": "Paris FC", "Stade Rennais": "Rennes", "Olympique Lyonnais": "Lyon", "Olympique Marseille": "Marseille",
    "AS Monaco": "Monaco", "RC Lens": "Lens", "Stade Brestois 29": "Brest", "RC Strasbourg": "Strasbourg",
    "Sporting Lisbon": "Sp Lisbon", "Sporting CP": "Sp Lisbon", "FC Porto": "Porto", "SL Benfica": "Benfica",
    "PSV Eindhoven": "PSV Eindhoven", "AZ Alkmaar": "AZ Alkmaar", "Feyenoord": "Feyenoord", "Ajax": "Ajax",
    "Olympiakos Piraeus": "Olympiakos", "Olympiacos": "Olympiakos", "PAOK Thessaloniki": "PAOK",
    "Panathinaikos": "Panathinaikos", "AEK Athens": "AEK", "Celtic": "Celtic", "Rangers": "Rangers",
    "Club Brugge": "Club Brugge", "Galatasaray": "Galatasaray", "Fenerbahce": "Fenerbahce",
}
QUITAR = {"fc", "cf", "afc", "ac", "sc", "ssc", "as", "ud", "cd", "rc", "sv", "vfb", "vfl", "tsg", "bsc", "fsv",
          "club", "de", "the", "1", "calcio", "sk", "fk", "cp", "sad", "and", "hotspur"}


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\[.*?\]", " ", s)
    s = s.replace("manchester", "man").replace("united", "utd").replace("athletic", "ath").replace("atletico", "ath")
    return " ".join(t for t in re.findall(r"[a-z0-9]+", s) if t not in QUITAR)


def _fecha(d):
    return datetime.strptime(d, "%d/%m/%Y" if len(d) == 10 else "%d/%m/%y").strftime("%Y-%m-%d")


def _num(r, k):
    v = r.get(k)
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


STATS_FD = [("goles", "FTHG", "FTAG"), ("tiros", "HS", "AS"), ("arco", "HST", "AST"), ("corners", "HC", "AC"),
            ("faltas", "HF", "AF"), ("amarillas", "HY", "AY"), ("rojas", "HR", "AR")]


def filas_fd(cod, temporadas, dias=None):
    """Partidos jugados de una liga de football-data, con las columnas del formato principal
    (Date, HomeTeam, AwayTeam, FTHG, FTAG y, si las hay, tiros, córners, faltas y tarjetas).
    temporadas: códigos «2526» del formato principal. En las ligas extra (un archivo con todas las temporadas)
    se toman la temporada más reciente (dias=None) o los partidos de los últimos «dias» días."""
    if cod not in EXTRA_FD:
        filas = []
        for temp in temporadas:
            txt = bajar(f"https://www.football-data.co.uk/mmz4281/{temp}/{cod}.csv").decode("utf-8-sig", "replace")
            filas += [r for r in csv.DictReader(io.StringIO(txt)) if r.get("HomeTeam") and _num(r, "FTHG") is not None]
        return filas
    crudo = bajar(f"https://www.football-data.co.uk/new/{cod}.csv")
    try:
        txt = crudo.decode("utf-8-sig")
    except UnicodeDecodeError:
        txt = crudo.decode("latin-1")
    filas = []
    for r in csv.DictReader(io.StringIO(txt)):
        r = {(k or "").replace("\ufeff", "").replace("ï»¿", "").strip(): v for k, v in r.items()}
        if (r.get("League") or "").strip() != EXTRA_FD[cod] or not r.get("Home") or _num(r, "HG") is None:
            continue
        filas.append({"Date": r["Date"], "HomeTeam": r["Home"].strip(), "AwayTeam": r["Away"].strip(),
                      "FTHG": r["HG"], "FTAG": r["AG"], "Season": (r.get("Season") or "").strip()})
    if not filas:
        return filas
    if dias is None:
        ult = max(filas, key=lambda r: _fecha(r["Date"]))["Season"]
        return [r for r in filas if r["Season"] == ult]
    desde = (datetime.now(CARACAS).date() - timedelta(days=dias)).isoformat()
    return [r for r in filas if _fecha(r["Date"]) >= desde]


def futbol(avisos):
    hoy = datetime.now(CARACAS).date()
    a = hoy.year if hoy.month >= 7 else hoy.year - 1
    temp = f"{str(a)[2:]}{str(a + 1)[2:]}"
    equipos, por_liga = {}, {}
    for cod, liga in LIGAS_FD.items():
        try:
            filas = filas_fd(cod, [temp])
        except Exception as e:  # noqa: BLE001
            avisos.append(f"football-data {cod}: {type(e).__name__}: {e}")
            continue
        filas.sort(key=lambda r: _fecha(r["Date"]))
        acum = {}
        for r in filas:
            for eq, rival, casa in ((r["HomeTeam"], r["AwayTeam"], True), (r["AwayTeam"], r["HomeTeam"], False)):
                e = acum.setdefault(eq, {"casa": {}, "fuera": {}, "partidos": []})
                lado = e["casa" if casa else "fuera"]
                lado["pj"] = lado.get("pj", 0) + 1
                for nom, kh, ka in STATS_FD:
                    yo, el = (_num(r, kh), _num(r, ka)) if casa else (_num(r, ka), _num(r, kh))
                    if yo is not None and el is not None:
                        lado[nom] = lado.get(nom, 0) + yo
                        lado[nom + "_c"] = lado.get(nom + "_c", 0) + el
                        lado["n_" + nom] = lado.get("n_" + nom, 0) + 1
                gf, gc = (int(_num(r, "FTHG")), int(_num(r, "FTAG"))) if casa else (int(_num(r, "FTAG")), int(_num(r, "FTHG")))
                e["partidos"].append((_fecha(r["Date"]), rival, casa, gf, gc))
        for eq, e in acum.items():
            sal = {"liga": liga, "pj": len(e["partidos"])}
            for lado in ("casa", "fuera"):
                L = e[lado]
                sal[lado] = {"pj": L.get("pj", 0)}
                for nom, _, _ in STATS_FD:
                    n = L.get("n_" + nom, 0)
                    if n:
                        sal[lado][nom] = round(L[nom] / n, 2)
                        sal[lado][nom + "_c"] = round(L[nom + "_c"] / n, 2)
            ps = e["partidos"]
            sal["mas25"] = round(sum(1 for p in ps if p[3] + p[4] > 2.5) / len(ps), 3) if ps else None
            sal["ambos"] = round(sum(1 for p in ps if p[3] > 0 and p[4] > 0) / len(ps), 3) if ps else None
            sal["ultimos"] = [{"f": p[0], "rival": p[1], "casa": p[2], "m": f"{p[3]}-{p[4]}",
                               "r": "G" if p[3] > p[4] else "E" if p[3] == p[4] else "P"} for p in ps[-5:]][::-1]
            equipos[eq] = sal
            por_liga.setdefault(cod, []).append(eq)
    return equipos, por_liga


def _buscar(n, cand):
    pool = {}
    for e in cand:
        pool.setdefault(_norm(e), e)
    k = _norm(n)
    if k in pool:
        return pool[k]
    # todas las palabras del nombre de football-data están en el de la casa ("hertha" en "hertha berlin"), y es el único
    tk = set(k.split())
    dentro = [e for kk, e in pool.items() if kk and set(kk.split()) <= tk]
    if len(dentro) == 1:
        return dentro[0]
    m = difflib.get_close_matches(k, list(pool), n=2, cutoff=0.8)
    if m and (len(m) == 1 or difflib.SequenceMatcher(None, k, m[0]).ratio() - difflib.SequenceMatcher(None, k, m[1]).ratio() > 0.05):
        return pool[m[0]]
    return None


def unir_nombres(nombres, equipos, por_liga):
    """nombres: {(nombre, liga_fd o None)}. Devuelve {nombre: nombre en football-data} solo si hay confianza."""
    sal, sin = {}, []
    for n, cod in sorted(nombres, key=lambda x: (x[0], x[1] or "")):
        if n in sal:
            continue
        if n in equipos:
            sal[n] = n
            continue
        if ALIAS.get(n) in equipos:
            sal[n] = ALIAS[n]
            continue
        hallado = None
        for cand in ([por_liga.get(cod)] if cod and por_liga.get(cod) else []) + [list(equipos)]:
            hallado = _buscar(n, cand)
            if hallado:
                break
        if hallado:
            sal[n] = hallado
        else:
            sin.append(n)
    return sal, sin


def nombres_futbol():
    nombres = set()
    try:
        pr = json.load(open(os.path.join(DATOS, "precios.json"), encoding="utf-8"))
        for l in pr.get("ligas", []):
            if l.get("deporte") != "Fútbol":
                continue
            cod = API_FD.get(l.get("clave"))
            for p in l.get("partidos", []):
                nombres.add((p["local"], cod))
                nombres.add((p["visita"], cod))
    except (OSError, ValueError):
        pass
    try:
        fd = json.load(open(os.path.join(DATOS, "futbol_dia.json"), encoding="utf-8"))
        for p in fd.get("partidos", []):
            nombres.add((p["local"], None))
            nombres.add((p["visita"], None))
    except (OSError, ValueError):
        pass
    return nombres


# ---------------------------------------------------------------- NBA
def _cache(nombre):
    try:
        return json.load(open(os.path.join(CACHE, nombre), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _guardar_cache(nombre, d):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, nombre), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _min(s):
    m = re.match(r"PT(\d+)M([\d.]+)S", str(s or ""))
    return round(int(m.group(1)) + float(m.group(2)) / 60, 1) if m else 0.0


NBA_EQ = [("pts", "points"), ("reb", "reboundsTotal"), ("ast", "assists"), ("tri", "threePointersMade"),
          ("tri_i", "threePointersAttempted"), ("perd", "turnovers"), ("faltas", "foulsPersonal"),
          ("robos", "steals"), ("tapones", "blocks")]


def nba(avisos):
    cache = _cache("nba_cajas.json")
    ls = json.loads(bajar("https://cdn.nba.com/static/json/staticData/scheduleLeagueV2.json", headers=NBA_H, timeout=60))["leagueSchedule"]
    terminados = [(g["gameId"], g["gameDateTimeUTC"][:10]) for d in ls["gameDates"] for g in d["games"]
                  if str(g.get("gameId", "")).startswith("002") and g.get("gameStatus") == 3]
    nuevos = [(gid, f) for gid, f in terminados if gid not in cache][:MAX_NUEVOS]
    for gid, f in nuevos:
        try:
            g = json.loads(bajar(f"https://cdn.nba.com/static/json/liveData/boxscore/boxscore_{gid}.json", headers=NBA_H))["game"]
        except Exception as e:  # noqa: BLE001
            avisos.append(f"caja NBA {gid}: {type(e).__name__}: {e}")
            continue
        caja = {"f": f, "eq": {}}
        for lado in ("homeTeam", "awayTeam"):
            t = g[lado]
            st = t.get("statistics", {})
            caja["eq"][t["teamTricode"]] = {
                "local": lado == "homeTeam", **{k: st.get(c) for k, c in NBA_EQ},
                "jug": [[p.get("name"), _min(p.get("statistics", {}).get("minutes")), p["statistics"].get("points"),
                         p["statistics"].get("reboundsTotal"), p["statistics"].get("assists"),
                         p["statistics"].get("threePointersMade")]
                        for p in t.get("players", []) if str(p.get("played")) == "1"]}
        if len(caja["eq"]) == 2 and all(v.get("pts") is not None for v in caja["eq"].values()):
            cache[gid] = caja
    _guardar_cache("nba_cajas.json", cache)
    faltan = len([1 for gid, _ in terminados if gid not in cache])
    if faltan:
        avisos.append(f"NBA: faltan {faltan} cajas por bajar (siguen en la próxima corrida).")
    eqs = {}
    for gid, c in sorted(cache.items(), key=lambda kv: kv[1]["f"]):
        (a, da), (b, db) = c["eq"].items()
        for yo, d, rival, dr in ((a, da, b, db), (b, db, a, da)):
            e = eqs.setdefault(yo, {"juegos": [], "jug": {}})
            e["juegos"].append((c["f"], rival, d["local"], d, dr))
            for nom, mi, pts, reb, ast, tri in d["jug"]:
                j = e["jug"].setdefault(nom, [0, 0, 0, 0, 0, 0])
                for i, v in enumerate((1, mi, pts, reb, ast, tri)):
                    j[i] += v or 0
    sal = {}
    for eq, e in eqs.items():
        J = e["juegos"]
        n = len(J)
        r = {"pj": n}
        for k, _ in NBA_EQ:
            vals = [x[3].get(k) for x in J if x[3].get(k) is not None]
            con = [x[4].get(k) for x in J if x[4].get(k) is not None]
            r[k] = round(sum(vals) / len(vals), 1) if vals else None
            r[k + "_c"] = round(sum(con) / len(con), 1) if con else None
        for lado, es in (("casa", True), ("fuera", False)):
            L = [x for x in J if x[2] == es]
            r[lado] = {"pj": len(L), "pts": round(sum(x[3]["pts"] for x in L) / len(L), 1) if L else None,
                       "pts_c": round(sum(x[4]["pts"] for x in L) / len(L), 1) if L else None}
        r["ultimos"] = [{"f": x[0], "rival": x[1], "casa": x[2], "m": f"{x[3]['pts']}-{x[4]['pts']}",
                         "r": "G" if x[3]["pts"] > x[4]["pts"] else "P"} for x in J[-5:]][::-1]
        jug = [(nom, v) for nom, v in e["jug"].items() if v[0] >= 3]
        jug.sort(key=lambda x: -x[1][1] / x[1][0])
        r["jugadores"] = [{"n": nom, "pj": v[0], "min": round(v[1] / v[0], 1), "pts": round(v[2] / v[0], 1),
                           "reb": round(v[3] / v[0], 1), "ast": round(v[4] / v[0], 1), "tri": round(v[5] / v[0], 1)}
                          for nom, v in jug[:7]]
        sal[eq] = r
    return sal


# ---------------------------------------------------------------- LVBP
LV_BAT = [("carreras", "runs"), ("hits", "hits"), ("hr", "homeRuns"), ("ponches", "strikeOuts"), ("boletos", "baseOnBalls")]


def lvbp(avisos):
    cache = _cache("lvbp_cajas.json")
    hoy = datetime.now(CARACAS).date()
    ini = hoy.replace(month=10, day=1) if hoy.month >= 9 else hoy.replace(year=hoy.year - 1, month=10, day=1)
    js = json.loads(bajar("https://statsapi.mlb.com/api/v1/schedule?sportId=17&leagueId=135&gameType=R"
                          f"&startDate={ini}&endDate={hoy}"))
    terminados = [(str(g["gamePk"]), d["date"]) for d in js.get("dates", []) for g in d.get("games", [])
                  if g.get("status", {}).get("codedGameState") == "F"]
    for pk, f in [x for x in terminados if x[0] not in cache][:MAX_NUEVOS]:
        try:
            b = json.loads(bajar(f"https://statsapi.mlb.com/api/v1/game/{pk}/boxscore"))
        except Exception as e:  # noqa: BLE001
            avisos.append(f"caja LVBP {pk}: {type(e).__name__}: {e}")
            continue
        caja = {"f": f, "eq": {}}
        for lado in ("home", "away"):
            t = b["teams"][lado]
            bat = t.get("teamStats", {}).get("batting", {})
            caja["eq"][t["team"]["name"]] = {"local": lado == "home", **{k: bat.get(c) for k, c in LV_BAT}}
        if len(caja["eq"]) == 2:
            cache[pk] = caja
    _guardar_cache("lvbp_cajas.json", cache)
    eqs = {}
    for pk, c in sorted(cache.items(), key=lambda kv: kv[1]["f"]):
        (a, da), (b, db) = c["eq"].items()
        for yo, d, rival, dr in ((a, da, b, db), (b, db, a, da)):
            eqs.setdefault(yo, []).append((c["f"], rival, d["local"], d, dr))
    sal = {}
    for eq, J in eqs.items():
        r = {"pj": len(J)}
        for k, _ in LV_BAT:
            v = [x[3][k] for x in J if x[3].get(k) is not None]
            w = [x[4][k] for x in J if x[4].get(k) is not None]
            r[k] = round(sum(v) / len(v), 2) if v else None
            r[k + "_c"] = round(sum(w) / len(w), 2) if w else None
        tot = [x[3]["carreras"] + x[4]["carreras"] for x in J if x[3].get("carreras") is not None and x[4].get("carreras") is not None]
        r["total_prom"] = round(sum(tot) / len(tot), 2) if tot else None
        r["ultimos"] = [{"f": x[0], "rival": x[1], "casa": x[2], "m": f"{x[3]['carreras']}-{x[4]['carreras']}",
                         "r": "G" if x[3]["carreras"] > x[4]["carreras"] else "P"} for x in J[-5:]][::-1]
        sal[eq] = r
    return sal


def correr():
    avisos = []
    previo = _cache_previo()
    doc = {"generado": datetime.now(CARACAS).isoformat(timespec="minutes")}
    try:
        eq, por_liga = futbol(avisos)
        if not eq:
            raise RuntimeError("football-data no devolvió equipos")
        nombres, sin = unir_nombres(nombres_futbol(), eq, por_liga)
        if sin:
            avisos.append("Fútbol sin estadísticas (equipo fuera de las ligas de football-data o nombre dudoso): " + ", ".join(sin))
        doc["futbol"] = {"equipos": eq, "nombres": nombres}
    except Exception as e:  # noqa: BLE001
        avisos.append(f"fútbol: {type(e).__name__}: {e}")
        doc["futbol"] = previo.get("futbol")
    for nom, fn in (("nba", nba), ("lvbp", lvbp)):
        try:
            doc[nom] = fn(avisos)
        except Exception as e:  # noqa: BLE001
            avisos.append(f"{nom}: {type(e).__name__}: {e}")
            doc[nom] = previo.get(nom)
    doc["avisos"] = avisos
    with open(SALIDA, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
    print("análisis:", {k: len(v.get("equipos", v)) if isinstance(v, dict) else None for k, v in doc.items() if k in ("futbol", "nba", "lvbp")})
    for a in avisos:
        print("AVISO análisis:", a)


def _cache_previo():
    try:
        return json.load(open(SALIDA, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


if __name__ == "__main__":
    correr()
