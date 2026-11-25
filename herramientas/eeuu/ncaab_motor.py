"""Motor NCAAB: eficiencia por posesión ajustada por rival + ritmo, y simulación de cada juego.

Ratings (al estilo de los modelos de eficiencia): para cada juego y equipo,
    puntos por 100 posesiones = media + ataque(equipo) - defensa(rival) ± ventaja de local
    posesiones del juego       = media + ritmo(local) + ritmo(visita)
Se ajustan con mínimos cuadrados ponderados (los juegos recientes pesan más) y con un ancla hacia el rating de la
temporada anterior (se va soltando a medida que hay juegos). Todo con juegos ANTERIORES a la fecha que se predice.

Simulación: posesiones ~ Normal, puntos de cada equipo ~ Normal correlacionada alrededor de su eficiencia x posesiones;
empate al final = prórroga de 5 minutos. Las varianzas se calibran con los residuos del backtest.
"""
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, vstack, identity
from scipy.sparse.linalg import lsqr

VIDA_MEDIA = 365.0      # días: un juego de hace un año pesa la mitad (ajustado en el backtest 2016-2021)
ANCLA = 3.0             # fuerza del ancla a la temporada anterior
REGRESO = 0.95          # cuánto del rating del año anterior se conserva de base
TOPE = 40              # recorte de palizas en pts/100 posesiones
NUEVO_PCT = 5          # percentil del rating inicial para equipos nuevos
LOCAL_EF = 1.6          # valor inicial; se estima con los datos (pts/100 pos a favor del local)


def ajustar(g, fecha, previo=None, vida=VIDA_MEDIA, ancla=ANCLA):
    """g: juegos terminados (columnas de ncaab_datos.juegos) ANTES de fecha. previo: dict equipo->(O, D, T) base.
    Devuelve dict con media, local, media_ritmo y ratings {equipo: (O, D, T)}."""
    g = g[g.fecha < fecha]
    if len(g) == 0:
        return None
    dias = (fecha - g.fecha).dt.days.values
    w = 0.5 ** (dias / vida)
    eq = pd.Index(sorted(set(g.local) | set(g.visita)))
    n = len(eq)
    il = eq.get_indexer(g.local)
    iv = eq.get_indexer(g.visita)
    m = len(g)
    loc = np.where(g.neutral.values, 0.0, 1.0)
    # --- eficiencia: 2 filas por juego. Variables: [media, local, O_0..O_n-1, D_0..D_n-1]
    filas = np.arange(2 * m)
    efl = 100 * g.pl.values / g.pos.values
    efv = 100 * g.pv.values / g.pos.values
    if TOPE:  # palizas: la diferencia de eficiencia se recorta a ±TOPE (los minutos de la basura no dicen nada)
        dif = efl - efv
        exceso = np.clip(np.abs(dif) - TOPE, 0, None) * np.sign(dif) / 2
        efl, efv = efl - exceso, efv + exceso
    y = np.concatenate([efl, efv])
    ww = np.sqrt(np.concatenate([w, w]))
    cols_o = np.concatenate([il, iv]) + 2
    cols_d = np.concatenate([iv, il]) + 2 + n
    signo_l = np.concatenate([loc, -loc])
    data = np.concatenate([np.ones(2 * m), signo_l, np.ones(2 * m), -np.ones(2 * m)])
    rr = np.concatenate([filas, filas, filas, filas])
    cc = np.concatenate([np.zeros(2 * m, int), np.ones(2 * m, int), cols_o, cols_d])
    X = csr_matrix((data * np.repeat(ww, 1)[rr], (rr, cc)), shape=(2 * m, 2 + 2 * n))
    yw = y * ww
    # ancla: O_i = O0_i y D_i = D0_i con peso sqrt(ancla)
    o0 = np.zeros(n)
    d0 = np.zeros(n)
    t0 = np.zeros(n)
    if previo:
        vals = np.array(list(previo.values()))
        # equipo sin rating del año anterior (casi siempre de fuera de la División I): parte como uno de los más débiles
        bajo = (np.percentile(vals[:, 0], NUEVO_PCT), np.percentile(vals[:, 1], NUEVO_PCT), 0.0)
        for k, e in enumerate(eq):
            o0[k], d0[k], t0[k] = (REGRESO * v for v in previo.get(e, bajo))
    A = identity(2 + 2 * n, format="csr")[2:] * np.sqrt(ancla)
    Xa = vstack([X, A])
    ya = np.concatenate([yw, np.sqrt(ancla) * np.concatenate([o0, d0])])
    sol = lsqr(Xa, ya, atol=1e-8, btol=1e-8, iter_lim=5000)[0]
    media, local = sol[0], sol[1]
    O, D = sol[2:2 + n], sol[2 + n:]
    # --- ritmo: una fila por juego. Variables: [media_ritmo, T_0..T_n-1]
    rr = np.concatenate([np.arange(m)] * 3)
    cc = np.concatenate([np.zeros(m, int), il + 1, iv + 1])
    sw = np.sqrt(w)
    Xt = csr_matrix((np.concatenate([sw, sw, sw]), (rr, cc)), shape=(m, 1 + n))
    At = identity(1 + n, format="csr")[1:] * np.sqrt(ancla)
    sol_t = lsqr(vstack([Xt, At]), np.concatenate([g.pos.values * sw, np.sqrt(ancla) * t0]), atol=1e-8, btol=1e-8)[0]
    # juegos por equipo (para saber cuánto confiar)
    pj = pd.Series(np.concatenate([g.local.values, g.visita.values])).value_counts()
    return {"media": media, "local": local, "media_ritmo": sol_t[0],
            "r": {e: (O[k], D[k], sol_t[1 + k]) for k, e in enumerate(eq)}, "pj": pj.to_dict()}


def predecir(R, local, visita, neutral=False):
    """Puntos esperados de cada equipo y posesiones."""
    z = (0.0, 0.0, 0.0)
    oL, dL, tL = R["r"].get(local, z)
    oV, dV, tV = R["r"].get(visita, z)
    h = 0.0 if neutral else R["local"]
    pos = R["media_ritmo"] + tL + tV
    efL = R["media"] + oL - dV + h
    efV = R["media"] + oV - dL - h
    return efL * pos / 100, efV * pos / 100, pos


def simular(pl, pv, pos, sd_margen, sd_total, n=20000, rng=None):
    """Simula n juegos. sd_margen y sd_total: desviaciones de la diferencia y de la suma (calibradas).
    Devuelve arrays de puntos local y visita (enteros, con prórroga si empatan)."""
    rng = rng or np.random.default_rng(7)
    mu_m, mu_t = pl - pv, pl + pv
    m = rng.normal(mu_m, sd_margen, n)
    t = rng.normal(mu_t, sd_total, n)
    L = np.rint((t + m) / 2)
    V = np.rint((t - m) / 2)
    emp = L == V
    while emp.any():  # prórroga: 5 minutos ~ 1/8 del juego, mismo equilibrio
        k = emp.sum()
        mo = rng.normal(mu_m / 8, sd_margen / np.sqrt(8), k)
        to = rng.normal(mu_t / 8, sd_total / np.sqrt(8) * 0.8, k)
        L[emp] += np.rint((to + mo) / 2)
        V[emp] += np.rint((to - mo) / 2)
        emp = L == V
    return L, V


def resumen_sim(L, V, linea_local=None, total=None):
    r = {"p_local": float((L > V).mean()), "pts_local": float(L.mean()), "pts_visita": float(V.mean()),
         "margen": float((L - V).mean()), "total": float((L + V).mean())}
    if linea_local is not None:  # linea_local: hándicap del local (negativo = favorito)
        d = L - V + linea_local
        r["p_cubre_local"] = float((d > 0).mean() / max(1e-9, (d != 0).mean()))
    if total is not None:
        s = L + V
        r["p_over"] = float((s > total).mean() / max(1e-9, (s != total).mean()))
    return r
