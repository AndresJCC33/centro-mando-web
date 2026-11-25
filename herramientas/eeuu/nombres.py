"""Unir los nombres de The Odds API con los de las fuentes de datos."""
import difflib
import re
import unicodedata

NHL = {"Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Calgary Flames": "CGY", "Carolina Hurricanes": "CAR",
       "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Columbus Blue Jackets": "CBJ", "Dallas Stars": "DAL",
       "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM", "Florida Panthers": "FLA", "Los Angeles Kings": "LAK",
       "Minnesota Wild": "MIN", "Montréal Canadiens": "MTL", "Montreal Canadiens": "MTL", "Nashville Predators": "NSH",
       "New Jersey Devils": "NJD", "New York Islanders": "NYI", "New York Rangers": "NYR", "Ottawa Senators": "OTT",
       "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA",
       "St Louis Blues": "STL", "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR",
       "Utah Mammoth": "UTA", "Utah Hockey Club": "UTA", "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK",
       "Washington Capitals": "WSH", "Winnipeg Jets": "WPG"}
NFL = {"Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF",
       "Carolina Panthers": "CAR", "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE",
       "Dallas Cowboys": "DAL", "Denver Broncos": "DEN", "Detroit Lions": "DET", "Green Bay Packers": "GB",
       "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX", "Kansas City Chiefs": "KC",
       "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
       "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG",
       "New York Jets": "NYJ", "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF",
       "Seattle Seahawks": "SEA", "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS"}


def _n(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    s = s.replace("&", " and ").replace("'", "")
    s = re.sub(r"\bst\b\.?", "state", s)
    s = re.sub(r"\bcsu\b", "cal state", s).replace("intl", "international").replace("appalachian state", "app state")
    s = re.sub(r"\bstate\b(?=.*\bstate\b)", "", s)
    return " ".join(re.findall(r"[a-z0-9]+", s))


# The Odds API -> nombres posibles en ESPN (cuando ni la búsqueda aproximada los une)
ALIAS_NCAAB = {"Florida Int'l Golden Panthers": ["FIU Panthers", "Florida International Panthers"],
               "Appalachian St Mountaineers": ["App State Mountaineers"]}


def ncaab(nombre, espn):
    """espn: dict nombre_mostrado -> id. Devuelve el id o None si no hay un candidato claro."""
    if nombre in espn:
        return espn[nombre]
    for a in ALIAS_NCAAB.get(nombre, []):
        if a in espn:
            return espn[a]
    pool = {}
    for k, v in espn.items():
        pool.setdefault(_n(k), v)
    k = _n(nombre)
    # "Saint" vs "St": probar ambas lecturas
    for cand in (k, k.replace("state ", "saint ", 1)):
        if cand in pool:
            return pool[cand]
    m = difflib.get_close_matches(k, list(pool), n=2, cutoff=0.86)
    if m and (len(m) == 1 or difflib.SequenceMatcher(None, k, m[0]).ratio() - difflib.SequenceMatcher(None, k, m[1]).ratio() > 0.03):
        return pool[m[0]]
    # misma mascota (última palabra) y nombre de la escuela parecido: único candidato
    tk = k.split()
    cand = [(kk, v) for kk, v in pool.items() if kk.split()[-1] == tk[-1]]
    pun = sorted(((difflib.SequenceMatcher(None, " ".join(tk[:-1]), " ".join(kk.split()[:-1])).ratio(), v) for kk, v in cand), reverse=True)
    if pun and pun[0][0] >= 0.6 and (len(pun) == 1 or pun[0][0] - pun[1][0] > 0.1):
        return pun[0][1]
    return None
