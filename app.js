// Centro de Mando, página pública. Lee datos/vitrina.json (lo escribe el hub después de cada corrida).
(() => {
  const $ = (s) => document.querySelector(s);
  const nf = (d) => new Intl.NumberFormat('es-VE', { minimumFractionDigits: d, maximumFractionDigits: d });
  const F = {
    u: (v) => (v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + nf(2).format(Math.abs(v))),
    pct: (v, d = 0) => (v == null ? '—' : nf(d).format(v * 100) + ' %'),
    pcts: (v, d = 1) => (v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + nf(d).format(Math.abs(v) * 100) + ' %'),
    am: (v) => (v == null || v === '' ? '—' : (v > 0 ? '+' : '−') + Math.abs(Math.round(v))),
    ll: (v) => (v == null ? '—' : nf(3).format(v)),
    dia: (f) => {
      const d = new Date(String(f).slice(0, 10) + 'T12:00:00Z');
      return Number.isNaN(+d) ? String(f) : d.toLocaleDateString('es-VE', { day: 'numeric', month: 'short', timeZone: 'UTC' });
    },
  };
  const signo = (v) => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');
  const LIQ = new Set(['GANADO', 'PERDIDO', 'PUSH']);
  const DECISION = { 'PICK CONFIABLE': 'Pick confiable', 'EV SIN CONFIANZA': 'Valor sin confianza', 'CONFIANZA SIN EV': 'Confianza sin valor', 'CONFIABLE BLOQUEADO': 'Frenado por el motor', 'SIN SEÑAL': 'Sin señal', DESCARTADO: 'Sin señal', SEGUIMIENTO: 'Solo seguimiento', 'NO CONFIABLE': 'No confiable', 'SIN PICK': 'Sin pick', VALOR: 'Pick de valor', CONFIABLE: 'Pick confiable' };
  const decision = (r) => {
    if (r.confiable) return 'Pick confiable';
    const base = String(r.filtro || '').split(' · ')[0];
    return DECISION[base] || (base ? base.charAt(0) + base.slice(1).toLowerCase().replace(/_/g, ' ') : 'Sin pick');
  };

  let D = null;
  let dep = 'Todos';
  const tabla = (nombre) => {
    const t = D.tablas[nombre];
    if (!t) return [];
    return t.data.map((fila) => Object.fromEntries(t.cols.map((c, i) => [c, t.dic && t.dic[c] && typeof fila[i] === 'number' ? t.dic[c][fila[i]] : fila[i]])));
  };
  const T = {};
  const deDep = (filas) => (dep === 'Todos' ? filas : filas.filter((r) => r.deporte === dep));
  const hoy = () => D.hoy;
  const menos = (f, n) => new Date(Date.parse(f + 'T12:00:00Z') - n * 86400000).toISOString().slice(0, 10);
  const corto = (r, eq) => (r.deporte === 'LVBP' ? String(eq || '').split(' ')[0] : String(eq || ''));
  const final = (r) => {
    if (!r.marcador) return '—';
    const p = String(r.marcador).split('-');
    if (p.length !== 2 || !(r.deporte === 'NBA' || r.deporte === 'LVBP') || !r.visitante) return String(r.marcador);
    return `${corto(r, r.visitante)} ${p[0]} – ${p[1]} ${corto(r, r.local)}`;
  };

  const fila = (tbody, celdas, clase) => {
    const tr = document.createElement('tr');
    if (clase) tr.className = clase;
    for (const c of celdas) {
      const td = document.createElement('td');
      if (c && typeof c === 'object') { td.textContent = c.t; if (c.c) td.className = c.c; } else td.textContent = c == null ? '—' : c;
      tr.append(td);
    }
    tbody.append(tr);
  };
  const llenar = (sel, filas, vacio) => {
    const tbody = $(sel + ' tbody');
    tbody.replaceChildren();
    if (!filas.length) {
      const tr = document.createElement('tr');
      const td = document.createElement('td');
      td.colSpan = $(sel + ' thead tr').children.length;
      td.className = 'tenue';
      td.textContent = vacio;
      tr.append(td);
      tbody.append(tr);
      return;
    }
    for (const f of filas) fila(tbody, f.celdas, f.clase);
  };
  const el = (tag, clase, texto) => { const e = document.createElement(tag); if (clase) e.className = clase; if (texto != null) e.textContent = texto; return e; };

  // ---------- Cabecera ----------
  const pintarCabecera = () => {
    const previa = deDep(T.previa);
    const fechas = [...new Set(previa.map((r) => r.fecha))].sort();
    const dia = fechas.includes(hoy()) ? hoy() : fechas.filter((f) => f <= hoy()).pop();
    const delDia = previa.filter((r) => r.fecha === dia);
    const conf = delDia.filter((r) => r.confiable).length;
    const cuando = dia === hoy() ? 'Hoy' : dia ? `El ${F.dia(dia)}` : 'Hoy';
    const nombre = dep === 'Todos' ? '' : ` de ${dep}`;
    $('#titular').textContent = !delDia.length ? `Sin juegos${nombre} cargados` : conf ? `${cuando}: ${conf} pick${conf === 1 ? '' : 's'} confiable${conf === 1 ? '' : 's'}${nombre}` : `${cuando} no hay pick confiable${nombre}`;
    const liq = deDep(T.picks).filter((p) => p.tipo === 'PICK' && LIQ.has(p.resultado));
    const u = liq.reduce((s, p) => s + (p.unidades || 0), 0);
    $('#bajada').textContent = `${delDia.length} juego${delDia.length === 1 ? '' : 's'} evaluado${delDia.length === 1 ? '' : 's'} por el motor.` + (liq.length ? ` En la temporada, los picks reales${nombre} llevan ${F.u(u)} unidades en ${liq.length} apuestas.` : ` Todavía no hay picks reales${nombre} liquidados.`);
    return dia;
  };

  // ---------- Hoy ----------
  const pintarHoy = (dia) => {
    const cp = $('#hoy-picks');
    cp.replaceChildren();
    const mios = deDep(T.picks).filter((p) => p.fecha === dia && p.tipo === 'PICK');
    if (mios.length) {
      const g = el('div', 'picks');
      for (const p of mios) {
        const a = el('article', 'pick');
        a.append(el('span', 'liga', p.competicion && p.competicion !== p.deporte ? `${p.deporte} · ${p.competicion}` : p.deporte));
        a.append(el('span', 'partido', p.partido));
        a.append(el('span', 'sel', p.seleccion));
        a.append(el('span', 'cuota', `${p.mercado} a ${F.am(p.cuota_am)}`));
        const det = [];
        if (p.p_modelo != null) det.push(`el motor le da ${F.pct(p.p_modelo)}`);
        if (p.ev != null) det.push(`valor esperado ${F.pcts(p.ev)}`);
        if (p.resultado !== 'PENDIENTE') det.push(p.resultado.toLowerCase() + (p.marcador ? ` (${p.marcador})` : ''));
        if (det.length) a.append(el('span', 'detalle', det.join('; ')));
        g.append(a);
      }
      cp.append(g);
    } else {
      const d = el('div', 'sin-pick');
      d.append(el('b', '', dia === hoy() ? 'Hoy no hay pick confiable.' : 'Sin pick confiable en la última jornada cargada.'));
      d.append(el('span', 'detalle', 'Ningún juego cumplió todas las reglas. Abajo está lo que el motor ve en cada uno y por qué no pasó.'));
      cp.append(d);
    }
    const caja = $('#hoy-juegos');
    caja.replaceChildren();
    const delDia = deDep(T.previa).filter((r) => r.fecha === dia).sort((a, b) => Number(b.confiable) - Number(a.confiable) || String(a.deporte).localeCompare(b.deporte) || (b.p_fav || 0) - (a.p_fav || 0));
    if (!delDia.length) caja.append(el('p', 'vacio', 'Todavía no hay juegos de hoy. Aparecen cuando se cargan las cuotas del día.'));
    for (const r of delDia) {
      const a = el('article', 'juego');
      a.dataset.estado = r.confiable ? 'pick' : r.fav_ok === 1 ? 'acerto' : r.fav_ok === 0 ? 'fallo' : '';
      a.append(el('span', 'liga', r.competicion && r.competicion !== r.deporte ? `${r.deporte} · ${r.competicion}` : r.deporte));
      a.append(el('span', 'partido', r.partido));
      a.append(el('span', 'gana', r.favorito === 'Empate' ? `Empate ${F.pct(r.p_fav)}` : `${corto(r, r.favorito)} ${F.pct(r.p_fav)}`));
      const det = [];
      if (r.cuota_fav_am != null) a.append(el('span', 'cuota', `JEL ${F.am(r.cuota_fav_am)}`));
      if (r.p_mer_fav != null) det.push(`la casa le da ${F.pct(r.p_mer_fav)}`);
      if (r.total_pred != null) det.push(`total ${nf(1).format(r.total_pred)}${r.linea_total != null ? `, línea ${nf(1).format(r.linea_total)}` : ''}`);
      if (det.length) a.append(el('span', 'detalle', det.join('; ')));
      a.append(el('span', 'decision', decision(r) + (r.confiable && r.senal ? `: ${r.senal}` : '')));
      if (!r.confiable && r.senal) a.append(el('span', 'detalle', `Mejor señal: ${r.senal}${r.senal_ev != null ? ` (EV ${F.pcts(r.senal_ev)})` : ''}`));
      if (r.marcador) a.append(el('span', 'detalle', `Final: ${final(r)}`));
      caja.append(a);
    }
    const lados = deDep(T.precio).filter((r) => r.fecha === dia && r.p_ref != null && r.ventaja != null).sort((a, b) => Number(b.confiable) - Number(a.confiable) || b.ventaja - a.ventaja).slice(0, 8);
    llenar('#hoy-precio', lados.map((r) => ({ celdas: [r.partido, `${r.mercado} ${r.seleccion}`, { t: F.am(r.cuota_am), c: 'n' }, { t: F.pcts(r.ventaja), c: 'n ' + signo(r.ventaja) }, r.casa_ref || '—'] })), 'Ningún lado con casa de referencia hoy (la LVBP no tiene).');
    const pend = deDep(T.picks).filter((p) => p.resultado === 'PENDIENTE').sort((a, b) => String(a.fecha).localeCompare(b.fecha));
    llenar('#hoy-pend', pend.map((p) => ({ celdas: [F.dia(p.fecha), p.partido, p.seleccion, { t: F.am(p.cuota_am), c: 'n' }, p.tipo === 'PICK' ? 'Real' : 'Simulado'] })), 'No hay picks esperando resultado.');
  };

  // ---------- Resultados ----------
  const enDia = (f) => {
    const v = $('#res-dia').value;
    const h = hoy();
    f = String(f).slice(0, 10);
    if (v === 'todos') return true;
    if (v === 'hoy') return f === h;
    if (v === 'ayer') return f === menos(h, 1);
    return f >= menos(h, 6) && f <= h;
  };
  const pintarResultados = () => {
    const juegos = deDep(T.previa).filter((r) => enDia(r.fecha)).sort((a, b) => String(b.fecha).localeCompare(a.fecha) || String(a.deporte).localeCompare(b.deporte));
    const term = juegos.filter((r) => r.fav_ok != null);
    const ok = term.filter((r) => r.fav_ok === 1).length;
    $('#res-resumen').textContent = !juegos.length ? '' : `${juegos.length} juegos. El favorito del motor acertó ${ok} de ${term.length} terminados${term.length ? ` (${F.pct(ok / term.length)})` : ''}.`;
    llenar('#res-juegos', juegos.map((r) => ({ celdas: [F.dia(r.fecha), r.partido, r.favorito ? `${corto(r, r.favorito)} ${F.pct(r.p_fav)}` : '—', { t: F.am(r.cuota_fav_am), c: 'n' }, final(r), { t: r.fav_ok === 1 ? 'Acertó' : r.fav_ok === 0 ? 'Falló' : 'Pendiente', c: r.fav_ok === 1 ? 'pos' : r.fav_ok === 0 ? 'neg' : 'tenue' }, decision(r)] })), 'Sin juegos evaluados en esos días.');
    const picks = deDep(T.picks).filter((p) => enDia(p.fecha)).sort((a, b) => String(b.fecha).localeCompare(a.fecha));
    llenar('#res-picks', picks.map((p) => ({ celdas: [F.dia(p.fecha), p.partido, p.seleccion, { t: F.am(p.cuota_am), c: 'n' }, { t: p.resultado.charAt(0) + p.resultado.slice(1).toLowerCase(), c: p.resultado === 'GANADO' ? 'pos' : p.resultado === 'PERDIDO' ? 'neg' : 'tenue' }, { t: F.u(p.unidades), c: 'n ' + signo(p.unidades) }, p.tipo === 'PICK' ? 'Real' : 'Simulado'] })), 'Sin picks en esos días.');
  };

  // ---------- Rendimiento ----------
  const pintarRendimiento = () => {
    const picks = deDep(T.picks);
    const reales = picks.filter((p) => p.tipo === 'PICK' && LIQ.has(p.resultado));
    const u = reales.reduce((s, p) => s + (p.unidades || 0), 0);
    const g = reales.filter((p) => p.resultado === 'GANADO').length;
    const pe = reales.filter((p) => p.resultado === 'PERDIDO').length;
    const pu = reales.filter((p) => p.resultado === 'PUSH').length;
    const k = $('#ren-kpis');
    k.replaceChildren();
    const kpi = (valor, etiqueta, clase) => { const d = el('div'); d.append(el('b', clase, valor), el('span', '', etiqueta)); k.append(d); };
    kpi(reales.length ? F.u(u) : '—', 'unidades', signo(u));
    kpi(reales.length ? F.pcts(u / reales.length) : '—', 'ROI', signo(u));
    kpi(`${g}-${pe}-${pu}`, 'ganados, perdidos, push');
    kpi(String(reales.length), 'apuestas liquidadas');

    const motores = deDep(T.motores);
    llenar('#ren-motores', motores.map((m) => {
      const suyos = picks.filter((p) => p.motor === m.motor);
      const r = suyos.filter((p) => p.tipo === 'PICK' && LIQ.has(p.resultado));
      const s = suyos.filter((p) => p.tipo === 'SIMULADO' && LIQ.has(p.resultado));
      const ur = r.reduce((x, p) => x + (p.unidades || 0), 0);
      const us = s.reduce((x, p) => x + (p.unidades || 0), 0);
      const c = (res) => r.filter((p) => p.resultado === res).length;
      return { celdas: [m.motor, m.estado, { t: `${c('GANADO')}-${c('PERDIDO')}-${c('PUSH')}`, c: 'n' }, { t: r.length ? F.u(ur) : '—', c: 'n ' + signo(ur) }, { t: r.length ? F.pcts(ur / r.length) : '—', c: 'n ' + signo(ur) }, { t: String(suyos.filter((p) => p.resultado === 'PENDIENTE').length), c: 'n' }, { t: s.length ? F.u(us) : '—', c: 'n ' + signo(us) }] };
    }), 'Sin motores para este deporte.');
    grafico(reales);
  };
  const grafico = (reales) => {
    const caja = $('#ren-grafico');
    caja.replaceChildren();
    if (!reales.length) { caja.append(el('p', 'vacio', 'Todavía no hay picks reales liquidados para graficar.')); return; }
    const porDia = new Map();
    for (const p of reales) porDia.set(p.fecha, (porDia.get(p.fecha) || 0) + (p.unidades || 0));
    let ac = 0;
    const pts = [...porDia].sort((a, b) => a[0].localeCompare(b[0])).map(([f, v]) => { ac += v; return { f, t: Date.parse(f + 'T12:00:00Z'), v: ac }; });
    const W = Math.max(320, caja.clientWidth - 24);
    const H = 220;
    const m = { l: 44, r: 16, t: 14, b: 26 };
    const xs = pts.map((p) => p.t);
    const ys = [0, ...pts.map((p) => p.v)];
    const x0 = Math.min(...xs);
    const x1 = Math.max(...xs) === x0 ? x0 + 86400000 : Math.max(...xs);
    const y0 = Math.min(...ys);
    const y1 = Math.max(...ys) === y0 ? y0 + 1 : Math.max(...ys);
    const x = (t) => m.l + ((t - x0) / (x1 - x0)) * (W - m.l - m.r);
    const y = (v) => H - m.b - ((v - y0) / (y1 - y0)) * (H - m.t - m.b);
    const NS = 'http://www.w3.org/2000/svg';
    const s = (tag, attrs, texto) => { const e = document.createElementNS(NS, tag); for (const [a, v] of Object.entries(attrs)) e.setAttribute(a, v); if (texto != null) e.textContent = texto; return e; };
    const svg = s('svg', { viewBox: `0 0 ${W} ${H}` });
    for (const v of [y0, 0, y1].filter((v, i, a) => a.indexOf(v) === i)) {
      svg.append(s('line', { x1: m.l, x2: W - m.r, y1: y(v), y2: y(v), stroke: v === 0 ? '#a3abbf' : '#3d445b', 'stroke-width': 1 }));
      svg.append(s('text', { x: m.l - 6, y: y(v) + 4, 'text-anchor': 'end' }, v === 0 ? '0' : F.u(v)));
    }
    const color = getComputedStyle(document.body).getPropertyValue('--acento').trim() || '#f1592a';
    svg.append(s('polyline', { points: pts.map((p) => `${x(p.t)},${y(p.v)}`).join(' '), fill: 'none', stroke: color, 'stroke-width': 2.5, 'stroke-linejoin': 'round' }));
    for (const p of pts) { const c = s('circle', { cx: x(p.t), cy: y(p.v), r: 3.5, fill: color }); c.append(s('title', {}, `${F.dia(p.f)}: ${F.u(p.v)} u acumuladas`)); svg.append(c); }
    svg.append(s('text', { x: m.l, y: H - 6 }, F.dia(pts[0].f)));
    if (pts.length > 1) svg.append(s('text', { x: W - m.r, y: H - 6, 'text-anchor': 'end' }, F.dia(pts[pts.length - 1].f)));
    const ult = pts[pts.length - 1];
    svg.append(s('text', { x: Math.min(x(ult.t), W - m.r) - 6, y: y(ult.v) - 8, 'text-anchor': 'end', style: `fill:${color};font-weight:600` }, `${F.u(ult.v)} u`));
    caja.append(svg);
  };

  // ---------- Motor ----------
  const pintarMotor = () => {
    const por = new Map();
    for (const r of deDep(T.modelo)) {
      const a = por.get(r.motor) || { motor: r.motor, n: 0, ok: 0, nm: 0, lm: 0, lk: 0 };
      a.n += r.n || 0; a.ok += r.aciertos || 0; a.nm += r.n_mer || 0; a.lm += r.ll_mod_m || 0; a.lk += r.ll_mer || 0;
      por.set(r.motor, a);
    }
    llenar('#mot-calidad', [...por.values()].map((a) => {
      const lm = a.nm ? a.lm / a.nm : null;
      const lk = a.nm ? a.lk / a.nm : null;
      const mejor = lm == null ? '—' : lm < lk ? 'El motor' : 'El mercado';
      return { celdas: [a.motor, { t: String(a.n), c: 'n' }, { t: a.n ? F.pct(a.ok / a.n, 1) : '—', c: 'n' }, { t: F.ll(lm), c: 'n' }, { t: F.ll(lk), c: 'n' }, { t: mejor, c: mejor === 'El motor' ? 'pos' : '' }] };
    }), 'Aún no hay juegos terminados con cuota.');
    const juegos = deDep(T.juegos).filter((j) => j.origen === 'real').sort((a, b) => String(b.fecha).localeCompare(a.fecha)).slice(0, 150);
    llenar('#mot-juegos', juegos.map((j) => ({ celdas: [F.dia(j.fecha), j.partido, j.marcador || '—', { t: F.pct(j.p_mod), c: 'n' }, { t: F.pct(j.p_mer), c: 'n' }, { t: j.fav_ok === 1 ? 'Acertó' : 'Falló', c: j.fav_ok === 1 ? 'pos' : 'neg' }] })), 'Sin juegos terminados todavía.');
  };

  // ---------- Explorar ----------
  const ORDEN = ['PICK CONFIABLE', 'CONFIABLE BLOQUEADO', 'EV SIN CONFIANZA', 'CONFIANZA SIN EV', 'SIN SEÑAL'];
  const pintarExplorar = () => {
    const g = new Map();
    for (const r of deDep(T.filtros)) {
      const k = r.motor + '|' + r.filtro;
      const a = g.get(k) || { motor: r.motor, filtro: r.filtro, n: 0, ga: 0, pe: 0, pu: 0, u: 0 };
      if (LIQ.has(r.resultado)) { a.n += 1; a.u += r.unidades || 0; if (r.resultado === 'GANADO') a.ga += 1; else if (r.resultado === 'PERDIDO') a.pe += 1; else a.pu += 1; }
      g.set(k, a);
    }
    const filas = [...g.values()].sort((a, b) => a.motor.localeCompare(b.motor) || ORDEN.indexOf(a.filtro) - ORDEN.indexOf(b.filtro));
    llenar('#exp-filtros', filas.map((a) => ({ celdas: [a.motor, DECISION[a.filtro] || a.filtro, { t: a.n + (a.n && a.n < 100 ? ' *' : ''), c: 'n' }, { t: `${a.ga}-${a.pe}-${a.pu}`, c: 'n' }, { t: a.n ? F.u(a.u) : '—', c: 'n ' + (a.n >= 100 ? signo(a.u) : 'tenue') }, { t: a.n ? F.pcts(a.u / a.n) : '—', c: 'n ' + (a.n >= 100 ? signo(a.u) : 'tenue') }] })), dep === 'Fútbol' ? 'El motor de fútbol no clasifica por estos filtros.' : 'Sin lados clasificados todavía.');
  };

  // ---------- Ligas ----------
  let P = { ligas: [] };
  const ligasDisponibles = () => {
    const pos = P.ligas.filter((l) => dep === 'Todos' || l.deporte === dep).map((l) => l.liga);
    const hist = [...new Set(deDep(T.previa).map((r) => r.competicion || r.deporte))];
    return [...new Set([...pos, ...hist])];
  };
  const ult5 = (txt) => {
    const s = el('span', 'ult');
    for (const r of String(txt || '')) { const i = el('i', '', r); i.dataset.r = r; s.append(i); }
    return s;
  };
  const pintarLigas = () => {
    const sel = $('#lig-sel');
    const ligas = ligasDisponibles();
    const antes = sel.value;
    sel.replaceChildren(...ligas.map((l) => new Option(l, l)));
    sel.value = ligas.includes(antes) ? antes : (ligas[0] || '');
    const liga = sel.value;
    const L = P.ligas.find((l) => l.liga === liga);
    const cab = $('#lig-tabla thead tr');
    const tb = $('#lig-tabla tbody');
    cab.replaceChildren();
    tb.replaceChildren();
    if (!L) {
      $('#lig-nota').textContent = liga ? 'Todavía no hay tabla de posiciones para esta liga.' : 'Sin ligas para este deporte.';
    } else {
      $('#lig-nota').textContent = `Temporada ${L.temporada}. A favor y en contra: promedio de ${L.unidad} por juego. Actualizado el ${L.actualizado}.`;
      const cols = L.empates ? ['#', 'Equipo', 'PJ', 'G', 'E', 'P', 'Pts', 'Últimos 5', 'Racha', 'Casa', 'Visita', 'A favor', 'En contra']
        : ['#', 'Equipo', 'PJ', 'G', 'P', '% G', 'Últimos 5', 'Racha', 'Casa', 'Visita', 'A favor', 'En contra'];
      for (const c of cols) { const th = el('th', ['#', 'Equipo', 'Últimos 5'].includes(c) ? '' : 'n', c); cab.append(th); }
      L.equipos.forEach((e, i) => {
        const tr = document.createElement('tr');
        const td = (t, c) => { const d = el('td', c || 'n', t); tr.append(d); return d; };
        td(String(i + 1), 'pos-n');
        td(e.equipo, ' ');
        td(String(e.pj)); td(String(e.g));
        if (L.empates) td(String(e.e));
        td(String(e.p));
        td(L.empates ? String(e.pts) : nf(3).format(e.pct));
        td('', ' ').append(ult5(e.ult5));
        td(e.racha, 'n ' + (e.racha[0] === 'G' ? 'pos' : e.racha[0] === 'P' ? 'neg' : ''));
        td(e.casa); td(e.visita);
        td(nf(1).format(e.pf)); td(nf(1).format(e.pc));
        tb.append(tr);
      });
    }
    const hist = T.previa.filter((r) => (r.competicion || r.deporte) === liga).sort((a, b) => String(b.fecha).localeCompare(a.fecha));
    const term = hist.filter((r) => r.fav_ok != null);
    const ok = term.filter((r) => r.fav_ok === 1).length;
    const pk = T.picks.filter((p) => (p.competicion || p.deporte) === liga && p.tipo === 'PICK' && LIQ.has(p.resultado));
    const u = pk.reduce((x, p) => x + (p.unidades || 0), 0);
    $('#lig-resumen').textContent = !hist.length ? '' : `El favorito del motor acertó ${ok} de ${term.length} juegos terminados${term.length ? ` (${F.pct(ok / term.length)})` : ''}.` + (pk.length ? ` Picks reales: ${pk.filter((p) => p.resultado === 'GANADO').length} ganados de ${pk.length}, ${F.u(u)} unidades.` : ' Sin picks reales liquidados.');
    llenar('#lig-hist', hist.slice(0, 120).map((r) => ({ celdas: [F.dia(r.fecha), r.partido, r.favorito ? `${corto(r, r.favorito)} ${F.pct(r.p_fav)}` : '—', { t: F.am(r.cuota_fav_am), c: 'n' }, final(r), { t: r.fav_ok === 1 ? 'Acertó' : r.fav_ok === 0 ? 'Falló' : 'Pendiente', c: r.fav_ok === 1 ? 'pos' : r.fav_ok === 0 ? 'neg' : 'tenue' }, decision(r)] })), 'El motor todavía no ha evaluado juegos de esta liga.');
  };

  const pintar = () => {
    document.body.dataset.dep = dep;
    document.querySelectorAll('.deportes button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.dep === dep)));
    const dia = pintarCabecera();
    pintarHoy(dia);
    pintarResultados();
    pintarLigas();
    pintarRendimiento();
    pintarMotor();
    pintarExplorar();
  };

  document.querySelectorAll('.deportes button').forEach((b) => b.addEventListener('click', () => { dep = b.dataset.dep; pintar(); }));
  $('#res-dia').addEventListener('change', () => pintarResultados());
  $('#lig-sel').addEventListener('change', () => pintarLigas());
  let ancho = window.innerWidth;
  window.addEventListener('resize', () => { if (D && window.innerWidth !== ancho) { ancho = window.innerWidth; pintarRendimiento(); } });

  const leer = (u) => fetch(u, { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  Promise.all([leer('datos/vitrina.json'), leer('datos/posiciones.json').catch(() => ({ ligas: [] }))])
    .then(([doc, pos]) => {
      D = doc;
      P = pos && Array.isArray(pos.ligas) ? pos : { ligas: [] };
      for (const n of ['picks', 'modelo', 'motores', 'previa', 'precio', 'juegos', 'filtros']) T[n] = tabla(n);
      $('#pie-fecha').textContent = `Datos del ${doc.generado} (hora de Caracas). Se actualizan solos después de cada corrida de los motores.`;
      pintar();
    })
    .catch((e) => {
      $('#titular').textContent = 'No se pudieron cargar los datos';
      const a = $('#error');
      a.hidden = false;
      a.textContent = `No se pudo leer el archivo de datos (${e.message}). Recarga la página en unos minutos.`;
    });
})();
