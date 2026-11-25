"""Motor NHL: goles de Poisson con ataque y defensa de cada equipo, y simulación con prórroga y shootout.

Ratings: log(goles esperados) = media + local + ataque(equipo) - defensa(rival), ajustado por máxima verosimilitud
de Poisson con los juegos ANTERIORES (los recientes pesan más) y un ancla al rating de la temporada anterior.
Simulación: tiempo regular con Poisson; si empatan, prórroga 3 contra 3 y shootout (casi una moneda al aire,
inclinada por la fuerza de cada equipo). El gol del ganador en prórroga o shootout cuenta para el total, como en las casas.
"""
import numpy as np
import pandas as pd
from scipy.optimize import minimize

VIDA_MEDIA = 365.0
ANCLA = 40.0
REGRESO = 0.9
REG_FRAC = 0.965      # goles de tiempo regular / goles finales (el gol de la prórroga); se recalibra en el backtest
EMPATE = 1.45        # los empates en tiempo regular son más que en dos Poisson independientes (se calibra)
PESO_OT = 0.35        # cuánto pesa la fuerza en la prórroga/shootout (0 = moneda al aire)


def ajustar(g, fecha, previo=None, vida=VIDA_MEDIA, ancla=ANCLA):
    """g: DataFrame con fecha, local, visita, gl, gv (goles finales). Devuelve ratings o None."""
    g = g[g.fecha < fecha]
    if len(g) < 10:
        return None
    w = 0.5 ** ((fecha - g.fecha).dt.days.values / vida)
    eq = pd.Index(sorted(set(g.local) | set(g.visita)))
    n = len(eq)
    il, iv = eq.get_indexer(g.local), eq.get_indexer(g.visita)
    gl, gv = g.gl.values.astype(float), g.gv.values.astype(float)
    a0 = np.zeros(n)
    d0 = np.zeros(n)
    if previo:
        for k, e in enumerate(eq):
            if e in previo["r"]:
                a0[k], d0[k] = (REGRESO * v for v in previo["r"][e])

    def f(x):
        mu, h, a, d = x[0], x[1], x[2:2 + n], x[2 + n:]
        ll = mu + h + a[il] - d[iv]
        lv = mu + a[iv] - d[il]
        el, ev = np.exp(ll), np.exp(lv)
        nll = np.sum(w * (el - gl * ll)) + np.sum(w * (ev - gv * lv))
        pen = ancla * (np.sum((a - a0) ** 2) + np.sum((d - d0) ** 2))
        rl, rv = w * (el - gl), w * (ev - gv)
        gmu = rl.sum() + rv.sum()
        gh = rl.sum()
        ga = np.bincount(il, rl, n) + np.bincount(iv, rv, n) + 2 * ancla * (a - a0)
        gd = -np.bincount(iv, rl, n) - np.bincount(il, rv, n) + 2 * ancla * (d - d0)
        return nll + pen, np.concatenate([[gmu, gh], ga, gd])

    x0 = np.concatenate([[np.log(3.0), 0.05], a0, d0])
    r = minimize(f, x0, jac=True, method="L-BFGS-B")
    x = r.x
    pj = pd.Series(np.concatenate([g.local.values, g.visita.values])).value_counts().to_dict()
    return {"mu": x[0], "local": x[1], "r": {e: (x[2 + k], x[2 + n + k]) for k, e in enumerate(eq)}, "pj": pj}


def esperados(R, local, visita):
    al, dl = R["r"].get(local, (0.0, 0.0))
    av, dv = R["r"].get(visita, (0.0, 0.0))
    return np.exp(R["mu"] + R["local"] + al - dv), np.exp(R["mu"] + av - dl)


def probabilidades(lh, la, linea_total=None, max_g=12):
    """Exacto (sin azar): reparte el tiempo regular con Poisson y la prórroga con la regla de PESO_OT."""
    from scipy.stats import poisson
    rh, ra = lh * REG_FRAC, la * REG_FRAC
    ph = poisson.pmf(np.arange(max_g + 1), rh)
    pa = poisson.pmf(np.arange(max_g + 1), ra)
    M = np.outer(ph, pa)
    M[np.diag_indices_from(M)] *= EMPATE
    M /= M.sum()
    p_emp = np.trace(M)
    p_ot_local = 0.5 + PESO_OT * (lh - la) / (lh + la)
    p_local = np.tril(M, -1).sum() + p_emp * p_ot_local
    res = {"p_local": float(p_local), "p_prorroga": float(p_emp), "g_local": float(lh), "g_visita": float(la)}
    if linea_total is not None:
        tot = np.add.outer(np.arange(max_g + 1), np.arange(max_g + 1))
        tot = tot + np.eye(max_g + 1)  # empate: +1 gol (el del ganador en prórroga o shootout)
        over = M[tot > linea_total].sum()
        push = M[tot == linea_total].sum()
        res["p_over"] = float(over / max(1e-9, 1 - push))
    # puck line del local -1.5: gana por 2 o más en tiempo regular (en prórroga siempre es por 1)
    dif = np.subtract.outer(np.arange(max_g + 1), np.arange(max_g + 1))
    res["p_local_m15"] = float(M[dif >= 2].sum())
    res["p_visita_m15"] = float(M[dif <= -2].sum())
    return res


def simular(lh, la, n=20000, rng=None):
    """Simulación (para marcadores más repetidos y comprobar las probabilidades exactas)."""
    rng = rng or np.random.default_rng(11)
    L = rng.poisson(lh * REG_FRAC, n)
    V = rng.poisson(la * REG_FRAC, n)
    emp = L == V
    gana_l = rng.random(n) < 0.5 + PESO_OT * (lh - la) / (lh + la)
    L = L + (emp & gana_l)
    V = V + (emp & ~gana_l)
    return L, V
