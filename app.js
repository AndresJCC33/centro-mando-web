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
  const hoy = () => new Date().toLocaleDateString('en-CA', { timeZone: 'America/Caracas' });
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
    const dia = hoy();   // solo la jornada de hoy: lo de días anteriores vive en Resultados
    const delDia = previa.filter((r) => r.fecha === dia);
    const conf = delDia.filter((r) => r.confiable).length;
    const cuando = dia === hoy() ? 'Hoy' : dia ? `El ${F.dia(dia)}` : 'Hoy';
    const nombre = dep === 'Todos' ? '' : ` de ${dep}`;
    $('#titular').textContent = !delDia.length ? `Todavía no hay juegos${nombre} de hoy cargados` : conf ? `${cuando}: ${conf} pick${conf === 1 ? '' : 's'} confiable${conf === 1 ? '' : 's'}${nombre}` : `${cuando} no hay pick confiable${nombre}`;
    const liq = deDep(T.picks).filter((p) => p.tipo === 'PICK' && LIQ.has(p.resultado));
    const u = liq.reduce((s, p) => s + (p.unidades || 0), 0);
    $('#bajada').textContent = `${delDia.length} juego${delDia.length === 1 ? '' : 's'} evaluado${delDia.length === 1 ? '' : 's'} por el motor.` + (liq.length ? ` En la temporada, los picks reales${nombre} llevan ${F.u(u)} unidades en ${liq.length} apuestas.` : ` Todavía no hay picks reales${nombre} liquidados.`);
    if (dep === 'MLB') {
      $('#titular').textContent = 'MLB en stand-by hasta 2027';
      $('#bajada').textContent = 'No hay juegos hasta la próxima temporada. El historial de 2026 está en la pestaña Historial.';
    } else if (SOLO_PRECIO.has(dep)) {
      const vp = (PR && PR.picks ? PR.picks : []).filter((x) => x.deporte === dep && String(x.inicio || '').slice(0, 10) === dia);
      const c = vp.filter((x) => APOSTABLE.has(x.tipo)).length;
      const jj = ligasPrecio().reduce((s, l) => s + l.partidos.filter((p) => String(p.inicio || '').slice(0, 10) === dia).length, 0);
      $('#titular').textContent = c ? `Hoy: ${c} pick${c === 1 ? '' : 's'} confiable${c === 1 ? '' : 's'} de ${dep}` : jj ? `Hoy no hay pick confiable de ${dep}` : `Hoy no hay juegos de ${dep} con cuotas`;
      $('#bajada').textContent = `${jj} juego${jj === 1 ? '' : 's'} vigilado${jj === 1 ? '' : 's'} hoy contra el precio justo de Pinnacle. Detalle en la pestaña Precios.`;
    }
    return dia;
  };
  const SOLO_PRECIO = new Set(['NCAAB', 'NHL', 'NFL']);

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
    if (SOLO_PRECIO.has(dep)) {
      const n = pintarMotorEEUU(caja, dia);
      if (!n) caja.append(el('p', 'vacio', `Hoy no hay juegos de ${dep} con cuotas.`));
    }
    if (!delDia.length && !SOLO_PRECIO.has(dep)) caja.append(el('p', 'vacio', 'Todavía no hay juegos de hoy. Aparecen cuando se cargan las cuotas del día.'));
    for (const r of delDia) {
      const a = el('article', 'juego');
      a.dataset.estado = r.confiable ? 'pick' : r.fav_ok === 1 ? 'acerto' : r.fav_ok === 0 ? 'fallo' : '';
      a.append(el('span', 'liga', r.competicion && r.competicion !== r.deporte ? `${r.deporte} · ${r.competicion}` : r.deporte));
      a.append(el('span', 'partido', r.partido));
      a.append(el('span', 'gana', r.favorito === 'Empate' ? `Empate ${F.pct(r.p_fav)}` : `${corto(r, r.favorito)} ${F.pct(r.p_fav)}`));
      const det = [];
      if (r.cuota_fav_am != null) a.append(el('span', 'cuota', `Cuota ${F.am(r.cuota_fav_am)}`));
      if (r.p_mer_fav != null) det.push(`la casa le da ${F.pct(r.p_mer_fav)}`);
      if (r.total_pred != null) det.push(`total ${nf(1).format(r.total_pred)}${r.linea_total != null ? `, línea ${nf(1).format(r.linea_total)}` : ''}`);
      if (det.length) a.append(el('span', 'detalle', det.join('; ')));
      a.append(el('span', 'decision', decision(r) + (r.confiable && r.senal ? `: ${r.senal}` : '')));
      if (!r.confiable && r.senal) a.append(el('span', 'detalle', `Mejor señal: ${r.senal}${r.senal_ev != null ? ` (EV ${F.pcts(r.senal_ev)})` : ''}`));
      if (r.marcador) a.append(el('span', 'detalle', `Final: ${final(r)}`));
      const an = analisisDe(r.deporte, r.local, r.visitante);
      if (an) a.append(an);
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


  let FUT = null;
  const RES = { L: 'Local', E: 'Empate', V: 'Visita' };
  const PROB_MIN = 0.45;
  const estadoFut = (p) => {
    if (!p.tipo_pick) return null;
    if (/NO CONFIABLE/.test(p.tipo_pick)) return { ok: false, txt: 'No confiable (no apostar)' };
    if (p.pick_prob != null && p.pick_prob < PROB_MIN) return { ok: false, txt: `Valor sin confianza: prob. ${F.pct(p.pick_prob, 1)}, bajo el 45 % que exige un pick confiable (no apostar)` };
    return { ok: true, txt: 'Pick confiable' };
  };
  const decAm = (d) => (d >= 2 ? Math.round((d - 1) * 100) : Math.round(-100 / (d - 1)));
  const pintarFutbol = () => {
    const sec = $('#futbol');
    const ps = FUT && Array.isArray(FUT.partidos) ? FUT.partidos : [];
    sec.hidden = !ps.length || !(dep === 'Todos' || dep === 'Fútbol');
    if (sec.hidden) return;
    const conRef = ps.filter((p) => p.referencia).length;
    $('#fut-nota').textContent = `${FUT.fecha === hoy() ? 'Jornada de hoy' : 'Última jornada analizada'}: ${F.dia(FUT.fecha)}, ${ps.length} partidos. ` +
      (conRef ? `${conRef} con cuotas de otras casas como referencia.` : 'Sin cuotas de otras casas como referencia: ningún partido puede dar pick confiable.');
    const picks = $('#fut-picks');
    picks.replaceChildren();
    const buenos = ps.filter((p) => estadoFut(p) && estadoFut(p).ok);
    const valor = ps.filter((p) => estadoFut(p) && !estadoFut(p).ok && !/NO CONFIABLE/.test(p.tipo_pick));
    picks.append(el('p', 'resumen', buenos.length ? `Picks confiables: ${buenos.map((p) => `${p.pick_txt} (prob. ${F.pct(p.pick_prob)}, ventaja ${F.pcts(p.pick_ev)})`).join('; ')}.` : 'Picks confiables de fútbol: ninguno en esta jornada.'));
    if (valor.length) picks.append(el('p', 'nota', `Con valor pero sin confianza (no se apuestan, quedan simulados): ${valor.map((p) => `${p.pick_txt}, prob. ${F.pct(p.pick_prob)}`).join('; ')}.`));
    const caja = $('#fut-juegos');
    caja.replaceChildren();
    for (const p of ps) {
      const c = el('article', 'juego');
      const est = estadoFut(p);
      if (est && est.ok) c.dataset.estado = 'pick';
      c.append(el('div', 'liga', `${p.competicion} · confianza ${String(p.confianza || '—').toLowerCase()}${p.referencia ? ' · ref. ' + p.referencia : ''}`));
      c.append(el('div', 'partido', p.partido));
      const t = el('table', 'mini');
      const th = el('tr');
      for (const h of ['', 'Cuota', 'Prob.', 'Justa', 'Ventaja']) th.append(el('th', h ? 'n' : '', h));
      const thd = el('thead');
      thd.append(th);
      t.append(thd);
      const tb = el('tbody');
      for (const k of ['L', 'E', 'V']) {
        const pr = p['p' + k];
        const ev = p['EV_' + k];
        const tr = el('tr');
        tr.append(el('td', '', k === 'L' ? p.local : k === 'V' ? p.visita : 'Empate'));
        tr.append(el('td', 'n cuota', pr && ev != null ? F.am(decAm((1 + ev) / pr)) : '—'));
        tr.append(el('td', 'n', F.pct(pr)));
        tr.append(el('td', 'n', F.am(p['justa_' + k])));
        tr.append(el('td', 'n ' + signo(ev), F.pcts(ev)));
        tb.append(tr);
      }
      t.append(tb);
      c.append(t);
      c.append(el('div', 'detalle', `Goles esperados ${nf(1).format(p.xG_L)} – ${nf(1).format(p.xG_V)}. Más de 2.5: ${F.pct(p.O25)} (justa ${F.am(p.O25_justa)}); menos de 2.5: ${F.pct(p.U25)}. Más de 1.5: ${F.pct(p.O15)}; más de 3.5: ${F.pct(p.O35)}. Ambos anotan: ${F.pct(p.BTTS)}.`));
      if (p.marcadores_top5) c.append(el('div', 'detalle', 'Marcadores más repetidos: ' + p.marcadores_top5.split(', ').slice(0, 3).join(', ') + '.'));
      if (est) c.append(el('div', 'detalle ' + (est.ok ? 'pos' : 'neg'), `${est.txt}: ${p.pick_txt}, ventaja ${F.pcts(p.pick_ev)}${p.razon ? '. ' + p.razon.charAt(0).toUpperCase() + p.razon.slice(1) : ''}.`));
      const an = analisisFutbol(p.local, p.visita);
      if (an) c.append(an);
      caja.append(c);
    }
  };


  // ---------------------------------------------------------------- Análisis por partido (estadísticas reales)
  let AN = null;
  const n1 = (v) => (v == null || !isFinite(v) ? '—' : nf(1).format(v));
  const forma = (u) => (u || []).map((x) => x.r).join(' ');
  const tablaAn = (cab, filas) => {
    const t = el('table', 'mini an');
    const thd = el('thead');
    const tr = el('tr');
    cab.forEach((h, i) => tr.append(el('th', i ? 'n' : '', h)));
    thd.append(tr);
    t.append(thd);
    const tb = el('tbody');
    for (const f of filas) {
      const r = el('tr');
      f.forEach((v, i) => r.append(el('td', i ? 'n' : '', v)));
      tb.append(r);
    }
    t.append(tb);
    return t;
  };
  const plegable = (titulo, ...hijos) => {
    const d = el('details', 'analisis');
    d.append(el('summary', '', titulo), ...hijos);
    return d;
  };
  // proyección: promedio entre lo que hace cada equipo y lo que concede su rival
  const proy = (a, b) => (a == null || b == null ? null : (a + b) / 2);
  const ladoFut = (e, casa) => {
    const l = e[casa ? 'casa' : 'fuera'];
    const o = e[casa ? 'fuera' : 'casa'];
    if (l && l.pj >= 3) return l;
    const m = {};   // con menos de 3 partidos de ese lado, uso el promedio de los dos lados
    for (const k of Object.keys({ ...l, ...o })) if (k !== 'pj') m[k] = l && l[k] != null && o && o[k] != null ? (l[k] + o[k]) / 2 : (l && l[k]) ?? (o && o[k]);
    return m;
  };
  const STATS_FUT = [['goles', 'Goles'], ['tiros', 'Tiros'], ['arco', 'Tiros al arco'], ['corners', 'Córners'], ['faltas', 'Faltas'], ['amarillas', 'Amarillas'], ['rojas', 'Rojas']];
  const analisisFutbol = (local, visita) => {
    if (!AN || !AN.futbol) return null;
    const nom = (n) => AN.futbol.nombres[n] || (AN.futbol.equipos[n] ? n : null);
    const L = AN.futbol.equipos[nom(local)];
    const V = AN.futbol.equipos[nom(visita)];
    if (!L || !V) return null;
    const a = ladoFut(L, true);
    const b = ladoFut(V, false);
    const filas = [];
    for (const [k, t] of STATS_FUT) {
      const pl = proy(a[k], b[k + '_c']);
      const pv = proy(b[k], a[k + '_c']);
      if (pl == null && pv == null) continue;
      filas.push([t, n1(pl), n1(pv), n1(pl != null && pv != null ? pl + pv : null)]);
    }
    const hijos = [tablaAn(['Proyección', local, visita, 'Partido'], filas)];
    hijos.push(el('p', 'detalle', `En casa ${local} promedia ${n1(L.casa.goles)} goles a favor y ${n1(L.casa.goles_c)} en contra (${L.casa.pj} PJ); fuera ${visita} promedia ${n1(V.fuera.goles)} y ${n1(V.fuera.goles_c)} (${V.fuera.pj} PJ).`));
    hijos.push(el('p', 'detalle', `Más de 2.5 goles en sus partidos: ${local} ${F.pct(L.mas25)}, ${visita} ${F.pct(V.mas25)}. Ambos anotan: ${F.pct(L.ambos)} y ${F.pct(V.ambos)}.`));
    hijos.push(el('p', 'detalle', `Últimos 5 (más reciente primero): ${local} ${forma(L.ultimos)}; ${visita} ${forma(V.ultimos)}.`));
    hijos.push(el('p', 'nota', `Temporada en curso de su liga (${L.liga}${V.liga !== L.liga ? ' / ' + V.liga : ''}), datos de football-data. La proyección es el promedio entre lo que cada equipo hace (local en casa, visita fuera) y lo que concede su rival; no es la simulación del motor.`));
    return plegable('Análisis: goles, tiros, córners, faltas y tarjetas', ...hijos);
  };
  const NBA_ST = [['pts', 'Puntos'], ['reb', 'Rebotes'], ['ast', 'Asistencias'], ['tri', 'Triples'], ['perd', 'Pérdidas'], ['robos', 'Robos'], ['tapones', 'Tapones'], ['faltas', 'Faltas']];
  const analisisNBA = (local, visita) => {
    const L = AN && AN.nba && AN.nba[local];
    const V = AN && AN.nba && AN.nba[visita];
    if (!L || !V) return null;
    const filas = NBA_ST.map(([k, t]) => {
      const pl = proy(L[k], V[k + '_c']);
      const pv = proy(V[k], L[k + '_c']);
      return [t, n1(pl), n1(pv), n1(pl != null && pv != null ? pl + pv : null)];
    });
    const hijos = [tablaAn(['Proyección', local, visita, 'Partido'], filas)];
    hijos.push(el('p', 'detalle', `${local} en casa: ${n1(L.casa.pts)} a favor y ${n1(L.casa.pts_c)} en contra (${L.casa.pj} PJ). ${visita} fuera: ${n1(V.fuera.pts)} y ${n1(V.fuera.pts_c)} (${V.fuera.pj} PJ).`));
    hijos.push(el('p', 'detalle', `Últimos 5: ${local} ${forma(L.ultimos)}; ${visita} ${forma(V.ultimos)}.`));
    for (const [eq, E] of [[local, L], [visita, V]]) {
      if (!E.jugadores || !E.jugadores.length) continue;
      hijos.push(tablaAn([`${eq} (promedios)`, 'Min', 'Pts', 'Reb', 'Ast', '3P'], E.jugadores.map((j) => [j.n, n1(j.min), n1(j.pts), n1(j.reb), n1(j.ast), n1(j.tri)])));
    }
    hijos.push(el('p', 'nota', 'Promedios de la temporada con las cajas oficiales de la NBA. La proyección es el promedio entre lo que hace cada equipo y lo que permite su rival; el total y el margen del motor están arriba.'));
    return plegable('Análisis: puntos, rebotes, asistencias, triples y jugadores', ...hijos);
  };
  const LV_ST = [['carreras', 'Carreras'], ['hits', 'Hits'], ['hr', 'Jonrones'], ['ponches', 'Ponches (bateando)'], ['boletos', 'Boletos (bateando)']];
  const analisisLVBP = (local, visita) => {
    const L = AN && AN.lvbp && AN.lvbp[local];
    const V = AN && AN.lvbp && AN.lvbp[visita];
    if (!L || !V) return null;
    const filas = LV_ST.map(([k, t]) => {
      const pl = proy(L[k], V[k + '_c']);
      const pv = proy(V[k], L[k + '_c']);
      return [t, n1(pl), n1(pv), n1(pl != null && pv != null ? pl + pv : null)];
    });
    return plegable('Análisis: carreras, hits, jonrones, ponches y boletos',
      tablaAn(['Proyección', corto({ deporte: 'LVBP' }, local), corto({ deporte: 'LVBP' }, visita), 'Juego'], filas),
      el('p', 'detalle', `Total de carreras promedio en sus juegos: ${corto({ deporte: 'LVBP' }, local)} ${n1(L.total_prom)}, ${corto({ deporte: 'LVBP' }, visita)} ${n1(V.total_prom)}. Últimos 5: ${forma(L.ultimos)}; ${forma(V.ultimos)}.`),
      el('p', 'nota', 'Temporada en curso, cajas oficiales de la LVBP. La proyección es el promedio entre lo que hace cada equipo y lo que permite su rival.'));
  };
  const analisisDe = (deporte, local, visita) => (deporte === 'Fútbol' ? analisisFutbol(local, visita) : deporte === 'NBA' ? analisisNBA(local, visita) : deporte === 'LVBP' ? analisisLVBP(local, visita) : null);


  // ---------------------------------------------------------------- Historial
  let hisTopeP = 50;
  let hisTopeJ = 50;
  const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'];
  const nomMes = (m) => `${MESES[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}`;
  const pintarHistorial = () => {
    const soloPrecio = SOLO_PRECIO.has(dep);
    $('#his-titulo').textContent = dep === 'Todos' ? 'Historial de todos los deportes' : `Historial de ${dep}`;
    // picks del hub y, para los deportes solo de precio, los del vigilante
    let todos = deDep(T.picks).map((p) => ({ fecha: String(p.fecha).slice(0, 10), partido: p.partido, sel: `${p.mercado === 'Moneyline' ? '' : p.mercado + ' '}${p.seleccion}`, cuota: p.cuota_am, resultado: p.resultado, u: p.unidades, real: p.tipo === 'PICK', motor: p.motor }));
    const vig = (PR && PR.picks ? PR.picks : []).filter((x) => dep === 'Todos' || x.deporte === dep)
      .map((x) => ({ fecha: String(x.inicio || x.fecha).slice(0, 10), partido: x.partido, sel: x.seleccion, cuota: x.cuota, resultado: x.resultado, u: x.unidades, real: APOSTABLE.has(x.tipo), motor: `${TIPO_PRE[x.tipo] || 'Vigilante'} · ${x.liga}` }));
    todos = todos.concat(vig).sort((a, b) => b.fecha.localeCompare(a.fecha));
    const sel = $('#his-mes');
    const meses = [...new Set(todos.map((p) => p.fecha.slice(0, 7)))].sort().reverse();
    const previo = sel.value;
    sel.replaceChildren(el('option', '', 'Todos'));
    sel.firstChild.value = 'todos';
    for (const m of meses) { const o = el('option', '', nomMes(m)); o.value = m; sel.append(o); }
    sel.value = meses.includes(previo) ? previo : 'todos';
    const tipo = $('#his-tipo').value;
    const xs = todos.filter((p) => (tipo === 'todos' || (tipo === 'real') === p.real) && (sel.value === 'todos' || p.fecha.startsWith(sel.value)));
    const liq = (ys) => ys.filter((p) => LIQ.has(p.resultado));
    const rec = (ys) => { const l = liq(ys); const u = l.reduce((s, p) => s + (p.u || 0), 0); return { n: l.length, g: l.filter((p) => p.resultado === 'GANADO').length, p: l.filter((p) => p.resultado === 'PERDIDO').length, pu: l.filter((p) => p.resultado === 'PUSH').length, u }; };
    const k = $('#his-kpis');
    k.replaceChildren();
    for (const [nom, ys] of [['reales', xs.filter((p) => p.real)], ['simulados', xs.filter((p) => !p.real)]]) {
      const r = rec(ys);
      const d = el('div');
      d.append(el('b', signo(r.u), r.n ? F.u(r.u) : '—'), el('span', '', `u en ${r.n} ${nom} (${r.g}-${r.p}-${r.pu})`));
      k.append(d);
    }
    const pend = xs.filter((p) => p.resultado === 'PENDIENTE').length;
    const d = el('div'); d.append(el('b', '', String(pend)), el('span', '', 'pendientes')); k.append(d);
    const por = new Map();
    for (const p of xs) { const a = por.get(p.motor) || []; a.push(p); por.set(p.motor, a); }
    llenar('#his-motores', [...por.entries()].map(([m, ys]) => { const r = rec(ys); return { celdas: [m, { t: String(ys.length), c: 'n' }, { t: `${r.g}-${r.p}-${r.pu}`, c: 'n' }, { t: r.n ? F.u(r.u) : '—', c: 'n ' + signo(r.u) }, { t: r.n ? F.pcts(r.u / r.n) : '—', c: 'n ' + signo(r.u) }] }; }), 'Sin picks guardados para este deporte.');
    llenar('#his-picks', xs.slice(0, hisTopeP).map((p) => ({ celdas: [F.dia(p.fecha), p.partido, p.sel, { t: F.am(p.cuota), c: 'n' }, { t: p.resultado.charAt(0) + p.resultado.slice(1).toLowerCase(), c: p.resultado === 'GANADO' ? 'pos' : p.resultado === 'PERDIDO' ? 'neg' : 'tenue' }, { t: F.u(p.u), c: 'n ' + signo(p.u) }, p.real ? 'Real' : 'Simulado'] })), 'Sin picks con ese filtro.');
    $('#his-mas-p').hidden = xs.length <= hisTopeP;
    const deME = (ME && ME.historial ? ME.historial : []).filter((x) => x.marcador && (dep === 'Todos' || x.deporte === dep))
      .map((x) => ({ fecha: x.fecha, partido: x.partido, marcador: x.marcador, p_mod: x.gano_local ? x.p_motor : 1 - x.p_motor, fav_ok: (x.p_motor >= 0.5) === x.gano_local ? 1 : 0 }));
    const js = deDep(T.juegos).filter((j) => j.origen === 'real').concat(deME).filter((j) => sel.value === 'todos' || String(j.fecha).startsWith(sel.value)).sort((a, b) => String(b.fecha).localeCompare(a.fecha));
    const ok = js.filter((j) => j.fav_ok === 1).length;
    $('#his-jres').textContent = js.length ? `${js.length} juegos terminados; el favorito del motor acertó ${ok} (${F.pct(ok / js.length)}).` : '';
    llenar('#his-juegos', js.slice(0, hisTopeJ).map((j) => ({ celdas: [F.dia(j.fecha), j.partido, j.marcador || '—', { t: F.pct(j.p_mod), c: 'n' }, { t: j.fav_ok === 1 ? 'Acertó' : 'Falló', c: j.fav_ok === 1 ? 'pos' : 'neg' }] })), soloPrecio ? 'El motor empezó el 25-nov-2026: aquí aparecen sus juegos a medida que terminan.' : 'Sin juegos terminados con ese filtro.');
    $('#his-mas-j').hidden = js.length <= hisTopeJ;
  };

  // ---------------------------------------------------------------- Motores NCAAB, NHL y NFL
  let ME = null;
  const UNIDAD = { NCAAB: 'puntos', NHL: 'goles', NFL: 'puntos' };
  const juegosME = (d) => (ME && ME.deportes && ME.deportes[d] ? ME.deportes[d].juegos : []);
  const tarjetaME = (d, j) => {
    const a = el('article', 'juego');
    const conValor = j.lados.filter((l) => APOSTABLE.has(l.tipo_precio));
    if (conValor.length) a.dataset.estado = 'pick';
    a.append(el('span', 'liga', `${d} · ${hora(j.inicio)}${j.neutral ? ' · cancha neutral' : ''}`));
    a.append(el('span', 'partido', `${j.visita} @ ${j.local}`));
    const fav = j.p_final >= 0.5 ? j.local : j.visita;
    a.append(el('span', 'gana', `${fav} ${F.pct(Math.max(j.p_final, 1 - j.p_final))}`));
    const dig = d === 'NHL' ? 1 : 0;
    a.append(el('span', 'detalle', `Marcador proyectado: ${j.local} ${nf(dig).format(j.pts_local)} – ${nf(dig).format(j.pts_visita)} ${j.visita} (${UNIDAD[d]}).`));
    a.append(el('span', 'detalle', `${j.local}: motor ${F.pct(j.p_motor)}, mercado ${j.p_mercado == null ? '—' : F.pct(j.p_mercado)}${ME.mezcla[d] ? `, combinado ${F.pct(j.p_final)}` : ''}.`));
    if (d === 'NHL' && j.portero_local) a.append(el('span', 'detalle', `Porteros probables: ${j.portero_local} (${nf(3).format(j.sv_local)} de atajadas) y ${j.portero_visita} (${nf(3).format(j.sv_visita)}). Tiros esperados: ${nf(1).format(j.tiros_local)} – ${nf(1).format(j.tiros_visita)}.`));
    if (d === 'NFL' && j.qb_local) a.append(el('span', 'detalle', `Mariscales: ${j.qb_local}${j.ajuste_qb_local ? ` (${j.ajuste_qb_local > 0 ? '+' : ''}${nf(1).format(j.ajuste_qb_local)} pts frente a su promedio reciente)` : ''} y ${j.qb_visita}${j.ajuste_qb_visita ? ` (${j.ajuste_qb_visita > 0 ? '+' : ''}${nf(1).format(j.ajuste_qb_visita)} pts)` : ''}.`));
    if (d === 'NHL') a.append(el('span', 'detalle', `Prórroga ${F.pct(j.p_prorroga)}. Gana por 2 o más (−1.5): ${j.local} ${F.pct(j.p_local_m15)}, ${j.visita} ${F.pct(j.p_visita_m15)}. Marcadores más repetidos: ${j.marcadores}.`));
    if (j.pj_local != null && (j.pj_local < 5 || j.pj_visita < 5)) a.append(el('span', 'detalle neg', 'Pocos juegos esta temporada: el motor todavía se apoya mucho en la temporada pasada.'));
    for (const l of conValor) {
      const ok = l.ventaja_final >= 0.02;
      a.append(el('span', 'decision', `${TIPO_PRE[l.tipo_precio]}: ${l.nombre}` + (ME.mezcla[d] ? (ok ? ` (con el motor sigue habiendo valor: ${F.pcts(l.ventaja_final)})` : ' (el motor no acompaña: mejor no)') : '')));
    }
    if (!conValor.length) {
      const mejor = j.lados.reduce((m, l) => (m == null || l.ventaja_final > m.ventaja_final ? l : m), null);
      if (ME.mezcla[d] && mejor && mejor.ventaja_final >= 0.03) a.append(el('span', 'decision', `Señal del motor: ${mejor.nombre}, ventaja ${F.pcts(mejor.ventaja_final)} con la probabilidad combinada (en prueba, sin dinero).`));
      else a.append(el('span', 'decision', 'Sin pick'));
    }
    return a;
  };
  const pintarMotorEEUU = (caja, dia) => {
    const ds = dep === 'Todos' ? [...SOLO_PRECIO] : [dep];
    let n = 0;
    for (const d of ds) {
      for (const j of juegosME(d).filter((x) => String(x.inicio).slice(0, 10) === dia)) { caja.append(tarjetaME(d, j)); n += 1; }
    }
    return n;
  };

  // ---------------------------------------------------------------- Análisis a fondo por juego
  let JA = null;
  let anDia = null;
  const C_LOC = '#3b74d6', C_VIS = '#e0485a', C_EMP = '#6f7689';
  const NS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, at) => { const e = document.createElementNS(NS, tag); for (const k in at) e.setAttribute(k, at[k]); return e; };
  const pct0 = (p) => `${Math.round(p * 100)} %`;
  const barraApilada = (partes, alto = 34) => {
    const b = el('div', 'an-apilada');
    b.style.height = alto + 'px';
    for (const [p, color, txt] of partes) {
      if (p <= 0) continue;
      const s = el('span', '', p >= 0.3 ? (txt || pct0(p)) : p >= 0.1 ? pct0(p) : '');
      s.style.width = (p * 100) + '%';
      s.style.background = color;
      b.append(s);
    }
    return b;
  };
  const histograma = (hist, linea, unidad) => {
    const W = 320, H = 120, M = 18;
    const paso0 = hist.length > 1 ? hist[1][0] - hist[0][0] : 1;
    if (paso0 === 1) hist = hist.map(([x, p]) => [x - 0.5, p]);   // valores enteros: la barra queda centrada en su número
    const xs = hist.map((h) => h[0]);
    const min = Math.min(...xs), max = Math.max(...xs) + (xs[1] - xs[0] || 1);
    const pmax = Math.max(...hist.map((h) => h[1]));
    const ancho = (W - 8) / ((max - min) / (xs[1] - xs[0] || 1));
    const sx = (x) => 4 + ((x - min) / (max - min)) * (W - 8);
    const s = svgEl('svg', { viewBox: `0 0 ${W} ${H + M}`, class: 'an-hist', role: 'img', 'aria-label': `Distribución del total de ${unidad}` });
    for (const [x, p] of hist) {
      const h = (p / pmax) * (H - 6);
      s.append(svgEl('rect', { x: sx(x) + 0.5, y: H - h, width: Math.max(1, ancho - 1), height: h, fill: linea != null && x + (xs[1] - xs[0] || 1) / 2 > linea ? C_LOC : C_VIS, opacity: 0.88 }));
    }
    if (linea != null) s.append(svgEl('line', { x1: sx(linea), x2: sx(linea), y1: 0, y2: H, stroke: '#f2f4f8', 'stroke-dasharray': '4 3', 'stroke-width': 1.5 }));
    const marcas = paso0 === 1 && hist.length <= 31 ? hist.map((h) => h[0] + 0.5) : [0, 1, 2, 3, 4].map((k) => min + ((max - min) * k) / 4);
    for (const x of marcas) {
      const t = svgEl('text', { x: sx(x), y: H + 14, 'text-anchor': 'middle', class: 'an-eje' });
      t.textContent = Math.round(x);
      s.append(t);
    }
    return s;
  };
  const tablaDatos = (d) => {
    const t = el('table', 'mini an');
    const th = el('thead'); const tr = el('tr');
    d.cab.forEach((h, i) => tr.append(el('th', i ? 'n' : '', h)));
    th.append(tr); t.append(th);
    const tb = el('tbody');
    for (const f of d.filas) { const r = el('tr'); f.forEach((v, i) => r.append(el('td', i ? 'n' : '', v == null ? '—' : String(v)))); tb.append(r); }
    t.append(tb);
    const caja = el('div', 'caja'); caja.append(t);
    return [el('h5', '', d.t), caja];
  };
  const tarjetaAnalisis = (g) => {
    const a = el('article', 'an-card');
    const hora = g.sin_hora ? 'hora por confirmar' : hora_(g.inicio);
    const sub = g.tres ? `Favorito: ${g.favorito} ${pct0(g.p_fav)} · ${g.sub}` : `Favorito: ${g.favorito} ${pct0(g.p_fav)} · Marcador medio ${g.cod[0]} ${Math.round(g.marcador[0])} – ${Math.round(g.marcador[1])} ${g.cod[1]} · Total esperado ${nf(1).format(g.total_esp)}`;
    a.append(el('p', 'an-sub', sub));
    const m = g.mejor;
    if (m) {
      const v = el('p', 'an-veredicto ' + (g.apostar ? 'si' : 'no'), g.apostar
        ? `Apuesta con valor: ${m.apuesta} en ${m.casa} a ${m.cuota.toFixed(2)} (valor ${F.pcts(m.ev)})`
        : `Mejor valor esperado: ${m.apuesta} en ${m.casa} a ${m.cuota.toFixed(2)} (${F.pcts(m.ev)})${g.razon ? ` · ${g.razon}` : ''}`);
      a.append(v);
    }
    if (!m && g.aviso) a.append(el('p', 'an-veredicto no', g.aviso));
    const grid = el('div', 'an-grid');
    // 1. quién gana
    const q = el('section', 'an-bloque');
    q.append(el('h4', '', '¿Quién gana?'));
    for (const f of g.fuentes) {
      const fila = el('div', 'an-fila' + (f.n === 'FINAL' ? ' final' : ''));
      fila.append(el('span', 'an-et', f.n));
      const partes = f.p.length === 3
        ? [[f.p[0], C_LOC, `${pct0(f.p[0])}`], [f.p[1], C_EMP, `E ${pct0(f.p[1])}`], [f.p[2], C_VIS, `${pct0(f.p[2])}`]]
        : [[f.p[0], C_LOC, `${g.cod ? g.cod[0] : ''} ${pct0(f.p[0])}`], [1 - f.p[0], C_VIS, `${g.cod ? g.cod[1] : ''} ${pct0(1 - f.p[0])}`]];
      fila.append(barraApilada(partes, f.n === 'FINAL' ? 30 : 24));
      q.append(fila);
    }
    if (g.tres) q.append(el('p', 'an-ley', `Azul ${g.local} · gris empate · rojo ${g.visita}`));
    grid.append(q);
    // 2. hándicap (NBA/NFL) o goles (fútbol)
    const h = el('section', 'an-bloque');
    if (g.hcp) {
      h.append(el('h4', '', `Hándicap ${g.cod[0]} ${g.hcp.linea > 0 ? '+' : ''}${g.hcp.linea}: cómo termina el margen`));
      const col = { v: C_VIS, l: C_LOC, lc: '#8fb0e8', vc: '#f0a0aa', push: C_EMP };
      h.append(barraApilada(g.hcp.tramos.map((t) => [t.p, col[t.c]]), 40));
      const ul = el('ul', 'an-leyenda');
      for (const t of g.hcp.tramos) { const li = el('li', '', `${t.n}: ${pct0(t.p)}`); li.style.setProperty('--c', col[t.c]); ul.append(li); }
      h.append(ul);
    } else if (g.tres && g.extras && g.extras.o25 != null) {
      const x = g.extras;
      h.append(el('h4', '', 'Goles'));
      for (const [t, p] of [['Más de 1.5', x.o15], ['Más de 2.5', x.o25], ['Más de 3.5', x.o35], ['Ambos anotan', x.ambos]]) {
        const fila = el('div', 'an-fila');
        fila.append(el('span', 'an-et', t));
        fila.append(barraApilada([[p, C_LOC, `sí ${pct0(p)}`], [1 - p, C_VIS, `no ${pct0(1 - p)}`]], 22));
        h.append(fila);
      }
      h.append(el('p', 'an-ley', 'Marcadores más probables: ' + x.marcadores.map((m2) => `${m2[0]} (${pct0(m2[1])})`).join(' · ')));
    } else {
      h.append(el('h4', '', 'Hándicap'));
      h.append(el('p', 'nota', 'Sin línea de hándicap cargada para este juego.'));
    }
    grid.append(h);
    // 3. total
    const t = el('section', 'an-bloque');
    if (g.tres && g.goles) {
      t.append(el('h4', '', 'Goles totales del partido (motor)'));
      t.append(histograma(g.goles, 2.5, 'goles'));
      t.append(el('p', 'an-ley', `Rojo: 2 goles o menos (${pct0(1 - g.extras.o25)}) · azul: 3 o más (${pct0(g.extras.o25)})`));
    } else if (g.total && g.total.hist) {
      t.append(el('h4', '', g.total.linea ? `Total de puntos: línea ${g.total.linea}` : 'Total de puntos'));
      t.append(histograma(g.total.hist, g.total.linea, 'puntos'));
      if (g.total.linea) {
        const r = el('p', 'an-ou');
        r.append(el('b', 'u', `UNDER ${pct0(g.total.under)}`), el('b', 'o', `OVER ${pct0(g.total.over)}`));
        t.append(r);
      }
    }
    grid.append(t);
    // 4. valor esperado
    const ve = el('section', 'an-bloque');
    ve.append(el('h4', '', 'Valor esperado (línea verde = mínimo 3 % para apostar)'));
    const lim = Math.max(0.08, ...g.valor.map((x) => Math.abs(x.ev)));
    for (const x of g.valor) {
      const fila = el('div', 'an-ev');
      fila.append(el('span', 'an-et', `${x.apuesta} · ${x.casa} ${x.cuota.toFixed(2)}`));
      const pista = el('div', 'an-pista');
      const barra = el('span', x.ev >= 0.03 ? 'si' : x.ev > 0 ? 'casi' : 'no');
      const w = (Math.abs(x.ev) / lim) * 50;
      barra.style.width = w + '%';
      barra.style.left = x.ev >= 0 ? '50%' : (50 - w) + '%';
      const meta = el('i', 'meta'); meta.style.left = (50 + (0.03 / lim) * 50) + '%';
      pista.append(barra, meta);
      fila.append(pista, el('b', x.ev >= 0.03 ? 'pos' : x.ev > 0 ? 'casi' : 'neg', F.pcts(x.ev)));
      ve.append(fila);
    }
    if (!g.valor.length) ve.append(el('p', 'nota', 'Sin cuotas cargadas todavía.'));
    grid.append(ve);
    a.append(grid);
    const ul = el('ul', 'an-pocas');
    for (const l of g.pocas) ul.append(el('li', '', l));
    const pocas = el('div', 'an-resumen');
    pocas.append(el('h4', '', 'En pocas palabras'), ul);
    a.append(pocas);
    if (g.datos && g.datos.length) {
      const d = el('details', 'analisis');
      d.append(el('summary', '', 'Datos de los equipos'));
      for (const x of g.datos) d.append(...tablaDatos(x));
      a.append(d);
    }
    return a;
  };
  const hora_ = (iso) => new Date(iso).toLocaleString('es-VE', { weekday: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Caracas' });
  const BANDERA = { 'Inglaterra': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'España': '🇪🇸', 'Alemania': '🇩🇪', 'Italia': '🇮🇹', 'Francia': '🇫🇷', 'Países Bajos': '🇳🇱',
    'Champions League': '🇪🇺', NFL: '🇺🇸', NBA: '🇺🇸', NCAAB: '🇺🇸', NCAAF: '🇺🇸', LVBP: '🇻🇪' };
  const bandera = (liga) => BANDERA[liga.split(' · ')[0]] || BANDERA[liga] || '';
  const filaJuego = (g) => {
    const d = el('details', 'an-juego' + (g.apostar ? ' verde' : ''));
    d.dataset.id = g.id;
    const s = el('summary', 'an-row');
    s.append(el('span', 'an-hora', g.sin_hora ? '—' : new Date(g.inicio).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/Caracas' })));
    const eq = el('span', 'an-equipos');
    eq.append(el('span', g.favorito === g.local ? 'fav' : '', g.local), el('span', g.favorito === g.visita ? 'fav' : '', g.visita));
    s.append(eq);
    s.append(el('span', 'an-pfav', `${g.favorito === 'Empate' ? 'E ' : ''}${pct0(g.p_fav)}`));
    s.append(el('span', 'an-chip ' + (g.apostar ? 'si' : g.mejor ? '' : 'nada'), g.apostar ? `Apostar · ${F.pcts(g.mejor.ev)}` : g.mejor ? `Valor ${F.pcts(g.mejor.ev)}` : 'Sin cuotas'));
    d.append(s);
    d.addEventListener('toggle', () => {
      if (d.open && d.childElementCount === 1) d.append(tarjetaAnalisis(g));
    });
    return d;
  };
  const pintarAnalisis = () => {
    const caja = $('#an-juegos');
    caja.replaceChildren();
    $('#an-dias').replaceChildren();
    if (!JA || !JA.juegos) { caja.append(el('p', 'vacio', 'Todavía no hay análisis cargados.')); return; }
    const xs = JA.juegos.filter((g) => dep === 'Todos' || g.deporte === dep);
    $('#an-nota').textContent = `Actualizado ${JA.generado.slice(11, 16)}. Toca un juego para ver su análisis. «Apostar» solo cuando el valor esperado llega a 3 % y el motor respalda ese lado.`;
    if (!xs.length) {
      caja.append(el('p', 'vacio', ['NBA', 'NFL', 'Fútbol', 'LVBP', 'NCAAB', 'Todos'].includes(dep)
        ? 'No hay juegos analizados de este deporte para hoy ni mañana. Los de NBA y LVBP aparecen cuando corren sus motores con la cartelera (desde las 10:30 am).'
        : 'El análisis por juego está disponible para NBA, NFL, NCAAB, LVBP y fútbol de las ligas principales.'));
      $('#titular').textContent = 'Sin juegos analizados';
      $('#bajada').textContent = '';
      return;
    }
    // todos los días, uno debajo del otro (hoy primero), y dentro de cada día por liga
    const dias = [...new Set(xs.map((g) => String(g.inicio).slice(0, 10)))].sort();
    const manana = new Date(Date.parse(hoy() + 'T12:00:00Z') + 864e5).toISOString().slice(0, 10);
    for (const dia of dias) {
      const delDia = xs.filter((g) => String(g.inicio).slice(0, 10) === dia);
      const cabDia = el('h2', 'an-dia');
      cabDia.append(el('span', '', dia === hoy() ? 'Hoy' : dia === manana ? 'Mañana' : F.dia(dia)),
        el('span', 'an-dia-n', `${delDia.length} juego${delDia.length === 1 ? '' : 's'}${delDia.some((g) => g.apostar) ? ` · ${delDia.filter((g) => g.apostar).length} para apostar` : ''}`));
      caja.append(cabDia);
      const ligas = new Map();
      for (const g of delDia) { if (!ligas.has(g.liga)) ligas.set(g.liga, []); ligas.get(g.liga).push(g); }
      const orden = [...ligas.keys()].sort((a, b) => (ligas.get(b).some((g) => g.apostar) - ligas.get(a).some((g) => g.apostar)) || a.localeCompare(b, 'es'));
      for (const liga of orden) {
        const grupo = el('section', 'an-grupo');
        const cab = el('h3', 'an-grupo-cab');
        cab.append(el('span', 'an-bandera', bandera(liga)), el('span', '', liga), el('span', 'an-n', String(ligas.get(liga).length)));
        grupo.append(cab);
        for (const g of ligas.get(liga)) grupo.append(filaJuego(g));
        caja.append(grupo);
      }
    }
    const verdes = xs.filter((g) => g.apostar);
    $('#titular').textContent = `${xs.length} juego${xs.length === 1 ? '' : 's'} analizado${xs.length === 1 ? '' : 's'} hoy y mañana`;
    $('#bajada').textContent = verdes.length ? `${verdes.length} con valor para apostar: ${verdes.map((g) => g.mejor.apuesta).join(', ')}. Están juntos en la pestaña Picks.` : 'Ninguno llega todavía a 3 % de valor con el respaldo del motor.';
  };
  const abrirJuego = (id) => {
    mostrar('analisis');
    const d = [...document.querySelectorAll('#an-juegos .an-juego')].find((x) => x.dataset.id === id);
    if (!d) return;
    d.open = true;
    d.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // ---------------------------------------------------------------- Picks
  const cuotaTxt = (d) => `${d.toFixed(2)} (${F.am(decAm(d))})`;
  const pintarPicks = () => {
    const ahora = new Date();
    const delDep = (x) => dep === 'Todos' || x.deporte === dep;
    const yaEmpezo = (g) => (g.sin_hora ? new Date(String(g.inicio).slice(0, 10) + 'T23:59:00-04:00') : new Date(g.inicio)) < ahora;
    // 1. picks del análisis (motor + mercado), los que todavía no empiezan
    const caja = $('#pk-ahora');
    caja.replaceChildren();
    const verdes = (JA && JA.juegos ? JA.juegos : []).filter((g) => g.apostar && g.mejor && delDep(g) && !yaEmpezo(g));
    caja.append(el('h2', 'pk-tit', verdes.length ? `Para apostar · ${verdes.length}` : 'Para apostar'));
    if (!verdes.length) caja.append(el('p', 'vacio', 'Ningún juego llega ahora a 3 % de valor con el respaldo del motor. Se revisa cada hora.'));
    for (const g of verdes) {
      const m = g.mejor;
      const c = el('article', 'pk');
      const cab = el('div', 'pk-cab');
      cab.append(el('span', '', `${bandera(g.liga)} ${g.liga}`), el('span', '', g.sin_hora ? F.dia(String(g.inicio).slice(0, 10)) : hora_(g.inicio)));
      c.append(cab);
      c.append(el('div', 'pk-partido', `${g.visita} @ ${g.local}`));
      c.append(el('div', 'pk-sel', m.apuesta));
      const cifras = el('dl', 'pk-cifras');
      const par = (k, v, cl = '') => { const w = el('div', cl); w.append(el('dt', '', k), el('dd', '', v)); cifras.append(w); };
      par('Cuota', `${cuotaTxt(m.cuota)} · ${m.casa}`);
      par('Tómala hasta', cuotaTxt(1.03 / m.p));
      par('Probabilidad', F.pct(m.p));
      par('Valor', F.pcts(m.ev), 'pos');
      c.append(cifras);
      if (g.razon) c.append(el('p', 'pk-razon', g.razon));
      const b = el('button', 'pk-ver', 'Ver el análisis del juego');
      b.type = 'button';
      b.addEventListener('click', () => abrirJuego(g.id));
      c.append(b);
      caja.append(c);
    }
    // 2. picks solo por precio (vigilante) que no estén ya arriba
    const cp = $('#pk-precio');
    cp.replaceChildren();
    const tomados = new Set(verdes.map((g) => `${g.local}|${g.visita}`));
    const porPrecio = ligasPrecio().flatMap((l) => l.partidos.filter((p) => new Date(p.inicio) > ahora && !tomados.has(`${p.local}|${p.visita}`))
      .flatMap((p) => p.lados.filter((x) => APOSTABLE.has(x.tipo)).map((x) => ({ ...x, p_: p, liga: l.nombre }))));
    if (porPrecio.length) {
      cp.append(el('h3', 'pk-tit', `Solo por precio · ${porPrecio.length}`));
      cp.append(el('p', 'nota', 'Aquí el motor no respalda ese lado (o no tiene modelo para esa liga): la ventaja sale solo de comparar la mejor cuota con el precio justo de Pinnacle. Más cautela con estos.'));
      const lista = el('div', 'pk-lista');
      for (const l of porPrecio.sort((a, b) => a.p_.inicio.localeCompare(b.p_.inicio))) {
        const f = el('div', 'pk-fila');
        const iz = el('div', '');
        iz.append(el('div', 'pk-f1', `${l.nombre} · ${F.am(l.mejor)} en ${l.casa}`), el('div', 'pk-f2', `${l.p_.local} vs ${l.p_.visita} · ${l.liga} · ${hora(l.p_.inicio)}`));
        const de = el('div', 'pk-de');
        de.append(el('div', 'pos', F.pcts(l.ventaja)), el('div', 'pk-f2', `hasta ${F.am(minimaDe(l))} · ${F.pct(l.p)}`));
        f.append(iz, de);
        lista.append(f);
      }
      cp.append(lista);
    }
    // 3. resultados
    const H = (JA && JA.picks ? JA.picks : []).filter(delDep);
    const liq = H.filter((x) => ['GANADO', 'PERDIDO', 'PUSH'].includes(x.resultado));
    const g_ = liq.filter((x) => x.resultado === 'GANADO').length;
    const p_ = liq.filter((x) => x.resultado === 'PERDIDO').length;
    const e_ = liq.filter((x) => x.resultado === 'PUSH').length;
    const u = liq.reduce((s, x) => s + (x.unidades || 0), 0);
    $('#pk-record').textContent = liq.length
      ? `${g_} ganado${g_ === 1 ? '' : 's'}, ${p_} perdido${p_ === 1 ? '' : 's'}${e_ ? `, ${e_} nulos` : ''} · ${F.u(u)} unidades apostando 1 por pick · rendimiento ${F.pcts(u / liq.length)}. ${H.length - liq.length} esperando resultado.`
      : H.length ? `${H.length} pick${H.length === 1 ? '' : 's'} guardado${H.length === 1 ? '' : 's'}, esperando resultado. El registro empezó el 26 de noviembre.` : 'Todavía no hay picks guardados. El registro empezó el 26 de noviembre.';
    const RES_TXT = { GANADO: 'Ganado', PERDIDO: 'Perdido', PUSH: 'Nulo', PENDIENTE: 'Pendiente' };
    const lh = $('#pk-hist');
    lh.replaceChildren();
    if (!H.length) lh.append(el('p', 'vacio', 'Sin picks guardados todavía.'));
    for (const x of H.slice(0, 100)) {
      const f = el('div', 'pk-fila');
      const iz = el('div', '');
      iz.append(el('div', 'pk-f1', `${x.apuesta} · ${x.cuota.toFixed(2)} en ${x.casa}`),
        el('div', 'pk-f2', `${F.dia(String(x.inicio).slice(0, 10))} · ${x.partido}${x.marcador ? ' · ' + x.marcador.split('-').reverse().join('-') : ''}`));
      const de = el('div', 'pk-de');
      const cl = x.resultado === 'GANADO' ? 'pos' : x.resultado === 'PERDIDO' ? 'neg' : '';
      de.append(el('div', cl, RES_TXT[x.resultado] || x.resultado), el('div', 'pk-f2 ' + signo(x.unidades), x.unidades == null ? `valor ${F.pcts(x.ev)}` : `${F.u(x.unidades)} u`));
      f.append(iz, de);
      lh.append(f);
    }
    $('#pk-nota').textContent = JA ? `Actualizado ${JA.generado.slice(11, 16)}. Cada pick se guarda antes de que empiece el juego, con la cuota de ese momento, y se califica solo cuando hay marcador.` : '';
  };

  // ---------------------------------------------------------------- Precios (vigilante)
  let PR = null;
  let preLiga = 'Todas';
  let preTope = 20;
  const DEP_LIGA = (l) => l.deporte;
  const ligasPrecio = () => (PR && Array.isArray(PR.ligas) ? PR.ligas : []).filter((l) => dep === 'Todos' || DEP_LIGA(l) === dep);
  const hora = (iso) => {
    const d = new Date(iso);
    return Number.isNaN(+d) ? iso : d.toLocaleString('es-VE', { weekday: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', timeZone: 'America/Caracas' });
  };
  const TIPO_PRE = { 'PICK CONFIABLE': 'Pick confiable', 'VALOR PROBADO': 'Valor probado', 'VALOR SIN CONFIANZA': 'Valor sin confianza' };
  const APOSTABLE = new Set(['PICK CONFIABLE', 'VALOR PROBADO']);
  const minimaDe = (l) => (l.tipo === 'VALOR PROBADO' && l.minima_vp != null ? l.minima_vp : l.minima ?? l.minima_jel);
  const pintarPrecios = () => {
    const ls = ligasPrecio();
    const chips = $('#pre-ligas');
    chips.replaceChildren();
    if (!ls.some((l) => l.nombre === preLiga)) preLiga = 'Todas';
    for (const nom of ['Todas', ...ls.map((l) => l.nombre)]) {
      const b = el('button', '', nom);
      b.type = 'button';
      b.setAttribute('aria-pressed', String(nom === preLiga));
      b.addEventListener('click', () => { preLiga = nom; preTope = 20; pintarPrecios(); });
      chips.append(b);
    }
    const vis = ls.filter((l) => preLiga === 'Todas' || l.nombre === preLiga);
    const ahora = new Date();
    const partidos = vis.flatMap((l) => l.partidos.map((p) => ({ ...p, liga: l.nombre, dep_: l.deporte }))).filter((p) => new Date(p.inicio) > ahora);
    partidos.sort((a, b) => a.inicio.localeCompare(b.inicio));
    $('#pre-nota').textContent = !PR ? 'El vigilante todavía no ha corrido.' : !ls.length ? 'El vigilante no sigue ligas de este deporte.' :
      `Cuotas tomadas el ${hora(PR.generado)} (se actualizan una vez al día, 9:40 am). ${partidos.length} partidos en los próximos días.`;
    const picks = $('#pre-picks');
    picks.replaceChildren();
    const lados = partidos.flatMap((p) => p.lados.filter((l) => l.tipo).map((l) => ({ ...l, p_: p })));
    const conf = lados.filter((l) => l.tipo === 'PICK CONFIABLE');
    const vpr = lados.filter((l) => l.tipo === 'VALOR PROBADO');
    const val = lados.filter((l) => l.tipo === 'VALOR SIN CONFIANZA');
    const txt = (l) => `${l.nombre} ${F.am(l.mejor)} en ${l.casa} (${l.p_.local} vs ${l.p_.visita}, prob. ${F.pct(l.p)}, ventaja ${F.pcts(l.ventaja)})`;
    picks.append(el('p', 'resumen', conf.length ? `Picks confiables: ${conf.map(txt).join('; ')}.` : 'Picks confiables por precio: ninguno ahora mismo.'));
    if (vpr.length) picks.append(el('p', 'resumen', `Valor probado (25–45 % de probabilidad y 3 % o más de ventaja): ${vpr.map(txt).join('; ')}.`));
    if (val.length) picks.append(el('p', 'nota', `Con valor pero sin confianza (menos de 45 %, no se apuestan): ${val.map((l) => `${l.nombre} ${F.am(l.mejor)}, prob. ${F.pct(l.p)}`).join('; ')}.`));
    const caja = $('#pre-juegos');
    caja.replaceChildren();
    for (const p of partidos.slice(0, preTope)) {
      const c = el('article', 'juego');
      if (p.lados.some((l) => APOSTABLE.has(l.tipo))) c.dataset.estado = 'pick';
      c.append(el('div', 'liga', `${p.liga} · ${hora(p.inicio)}`));
      c.append(el('div', 'partido', `${p.local} vs ${p.visita}`));
      const t = el('table', 'mini');
      const thd = el('thead');
      const th = el('tr');
      for (const h of ['', 'Prob.', 'Justa', 'Cuota mín.', 'Casa']) th.append(el('th', h ? 'n' : '', h));
      thd.append(th);
      t.append(thd);
      const tb = el('tbody');
      for (const l of p.lados) {
        const tr = el('tr');
        tr.append(el('td', '', l.nombre));
        tr.append(el('td', 'n', F.pct(l.p)));
        tr.append(el('td', 'n', F.am(l.justa)));
        tr.append(el('td', 'n cuota', F.am(l.minima ?? l.minima_jel)));
        tr.append(el('td', 'n ' + (l.tipo ? 'pos' : ''), l.mejor == null ? '—' : F.am(l.mejor)));
        tb.append(tr);
      }
      t.append(tb);
      c.append(t);
      const fav = [...p.lados].sort((a, b) => b.p - a.p)[0];
      if (fav) c.append(el('div', 'detalle', `Pronóstico: ${fav.nombre === 'Empate' ? 'empate' : 'gana ' + fav.nombre} (${F.pct(fav.p)}).`));
      for (const l of p.lados.filter((x) => x.tipo)) c.append(el('div', 'detalle ' + (APOSTABLE.has(l.tipo) ? 'pos' : 'neg'), `${TIPO_PRE[l.tipo]}: ${l.nombre} ${F.am(l.mejor)} en ${l.casa}, ventaja ${F.pcts(l.ventaja)}${APOSTABLE.has(l.tipo) ? `; tómalo a ${F.am(minimaDe(l))} o mejor` : ' (batacazo: no se apuesta)'}.`));
      const an = p.dep_ === 'Fútbol' ? analisisFutbol(p.local, p.visita) : null;
      if (an) c.append(an);
      caja.append(c);
    }
    const mas = $('#pre-mas');
    mas.hidden = partidos.length <= preTope;
    // historial
    const hist = (PR && PR.picks ? PR.picks : []).filter((x) => dep === 'Todos' || x.deporte === dep).filter((x) => preLiga === 'Todas' || x.liga === preLiga);
    const reales = hist.filter((x) => x.tipo === 'PICK CONFIABLE');
    const probados = hist.filter((x) => x.tipo === 'VALOR PROBADO');
    const resumen = (xs) => {
      const liq = xs.filter((x) => x.resultado === 'GANADO' || x.resultado === 'PERDIDO');
      const u = liq.reduce((s, x) => s + (x.unidades || 0), 0);
      const clv = xs.filter((x) => x.clv != null);
      const cm = clv.length ? clv.reduce((s, x) => s + x.clv, 0) / clv.length : null;
      return `${xs.length} picks, ${liq.filter((x) => x.resultado === 'GANADO').length}-${liq.filter((x) => x.resultado === 'PERDIDO').length}, ${F.u(u)} u, CLV medio ${F.pcts(cm)}`;
    };
    $('#pre-resumen').textContent = hist.length ? `Confiables: ${resumen(reales)}. Valor probado: ${resumen(probados)}. Todos (incluye valor sin confianza, simulados): ${resumen(hist)}.` : 'Todavía no hay picks guardados.';
    llenar('#pre-hist', hist.slice(0, 60).map((x) => ({ celdas: [
      F.dia(x.fecha), `${x.partido}${x.marcador ? ' (' + x.marcador + ')' : ''}`, `${x.seleccion} · ${x.casa}`, F.am(x.cuota),
      { t: F.pcts(x.ventaja), c: 'n pos' }, { t: F.pcts(x.clv), c: 'n ' + signo(x.clv) },
      { t: x.resultado === 'PENDIENTE' ? 'Pendiente' : x.resultado === 'GANADO' ? 'Ganado' : 'Perdido', c: x.resultado === 'GANADO' ? 'pos' : x.resultado === 'PERDIDO' ? 'neg' : '' },
      TIPO_PRE[x.tipo] || x.tipo] })), 'Sin picks guardados todavía.');
  };
  const pintarVigilanteHoy = () => {
    const caja = $('#hoy-vigilante');
    caja.replaceChildren();
    const ls = ligasPrecio();
    const conf = ls.flatMap((l) => l.partidos.filter((p) => new Date(p.inicio) > new Date()).flatMap((p) => p.lados.filter((x) => APOSTABLE.has(x.tipo)).map((x) => ({ ...x, p_: p, liga: l.nombre }))));
    if (!conf.length) {
      if (SOLO_PRECIO.has(dep)) caja.append(el('p', 'sin-pick', `Ahora mismo no hay pick confiable ni de valor probado en ${dep}. Todos los juegos y cuotas están en la pestaña Precios.`));
      return;
    }
    caja.append(el('h3', '', 'Picks por precio (vigilante)'));
    for (const l of conf) {
      const c = el('article', 'pick');
      c.append(el('div', 'liga', `${l.liga} · ${hora(l.p_.inicio)}`));
      c.append(el('div', 'partido', `${l.p_.local} vs ${l.p_.visita}`));
      c.append(el('div', 'detalle pos', `${TIPO_PRE[l.tipo]} · ${l.nombre}: tómalo solo a ${F.am(minimaDe(l))} o mejor (prob. ${F.pct(l.p)}; ${l.casa} paga ${F.am(l.mejor)}).`));
      caja.append(c);
    }
  };

  // ---------------------------------------------------------------- Pestañas
  const PESTANAS = ['picks', 'analisis', 'precios', 'historial', 'mas'];
  const tabVisible = (tab) => (tab === 'precios' ? !['MLB', 'LVBP'].includes(dep) : true);
  let tabActual = 'picks';
  const ajustarTabs = () => {
    document.querySelectorAll('.pestanas button').forEach((b) => { b.hidden = !tabVisible(b.dataset.tab); });
    if (!tabVisible(tabActual)) mostrar('analisis');
  };
  const mostrar = (tab) => {
    if (!PESTANAS.includes(tab) || !tabVisible(tab)) tab = 'picks';
    tabActual = tab;
    document.querySelectorAll('main > section[data-tab]').forEach((s) => s.classList.toggle('fuera', s.dataset.tab !== tab));
    document.querySelectorAll('.pestanas button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    if (location.hash.slice(1) !== tab) history.replaceState(null, '', '#' + tab);
  };
  document.querySelectorAll('.pestanas button').forEach((b) => b.addEventListener('click', () => { mostrar(b.dataset.tab); window.scrollTo({ top: document.querySelector('.indice').offsetTop, behavior: 'smooth' }); }));
  mostrar(location.hash.slice(1));


  // ---------------------------------------------------------------- Cómo trabaja el motor (por deporte)
  const MOTOR = {
    Todos: { t: 'Cómo trabaja el motor', p: [
      ['Historia', 'Baja los resultados y las estadísticas de cada temporada de cada liga.'],
      ['Plantillas del día', 'Revisa quién juega: alineaciones, abridores y reporte de lesiones.'],
      ['Simulación', 'Juega cada partido miles de veces y de ahí saca la probabilidad de cada resultado, de los totales y de los marcadores.'],
      ['Precio', 'Compara esa probabilidad con la cuota y con el precio justo de Pinnacle. Solo marca pick confiable cuando la cuota paga más de lo que vale y pasa todos los filtros.']],
      n: 'Toca un deporte arriba para ver cómo trabaja su motor.' },
    NBA: { t: 'Cómo trabaja el motor de la NBA', p: [
      ['Jugada por jugada', 'Baja el play-by-play oficial de nba.com de toda la temporada y arma, posesión por posesión, el ritmo y la eficiencia de cada equipo y de cada quinteto.'],
      ['Plantillas y lesiones', 'Usa las plantillas oficiales del día y el reporte de lesiones de la NBA: si falta un jugador clave, el equipo se recalcula sin él.'],
      ['Simulación', 'Juega el partido miles de veces y saca la probabilidad de ganar, de cubrir el hándicap y del total de puntos.'],
      ['Precio contra Pinnacle', 'Pick confiable solo si la cuota paga al menos 4 % más que el precio justo de Pinnacle, el motor está de acuerdo y la línea no pasa de +250.']] },
    LVBP: { t: 'Cómo trabaja el motor de la LVBP', p: [
      ['Turno por turno', 'Baja del calendario oficial cada juego de la temporada y arma el perfil de cada bateador y lanzador: ponches, boletos, sencillos, dobles, jonrones y outs.'],
      ['Abridores', 'Toma los abridores anunciados. Sin abridor anunciado usa uno promedio y no da pick.'],
      ['Simulación', 'Juega el partido turno al bate por turno al bate miles de veces y saca la probabilidad de ganar, del total de carreras y del run line.'],
      ['Filtros', 'Confianza de 56 % o más y valor esperado de 2 % o más. Como la LVBP no tiene casa de referencia, hoy sus señales van como simuladas.']] },
    'Fútbol': { t: 'Cómo trabaja el motor de fútbol', p: [
      ['Historia', 'Baja los resultados de las ligas europeas (football-data) y de la Champions, y mide la fuerza de ataque y de defensa de cada equipo.'],
      ['Goles esperados', 'Calcula cuántos goles debería marcar cada equipo en ese partido, según su fuerza y si juega en casa.'],
      ['Simulación', 'Juega cada partido 200 000 veces: probabilidad de local, empate y visita, de más o menos goles, de que anoten los dos y los marcadores más repetidos.'],
      ['Precio', 'Mezcla su probabilidad con el mercado y la compara con Pinnacle. Pick confiable: valor de 2 % o más y probabilidad de 45 % o más.']] },
    NCAAB: { t: 'Cómo trabaja el motor de la NCAAB', p: [
      ['Posesiones', 'Con las cajas de ESPN de cada juego cuenta las posesiones y mide los puntos por cada 100 posesiones que anota y que permite cada equipo, ajustados por rival, y su ritmo.'],
      ['Temporada anterior', 'Al inicio del año parte del rating de la temporada pasada y lo va soltando a medida que hay juegos; las palizas se recortan para que no inflen a nadie.'],
      ['Simulación', 'Juega el partido 20 000 veces con el ritmo y la eficiencia de los dos (con prórroga si empatan) y saca la probabilidad de ganar y el marcador proyectado.'],
      ['Mezcla con el mercado', 'En el backtest 2016-2021 el motor quedó muy cerca del cierre (error medio del margen 8,7 contra 8,6 con 15 juegos o más) y mezclado al 10 % lo iguala o lo mejora apenas. Por eso la probabilidad final es 90 % Pinnacle y 10 % motor, y solo cuando los dos equipos llevan 4 juegos o más.']],
      n: 'Con pocos juegos el motor se equivoca más que el mercado: diferencias grandes al inicio de la temporada no son valor.' },
    NHL: { t: 'Cómo trabaja el motor de la NHL', p: [
      ['Tiros y goles', 'Con esta temporada y la anterior mide cuántos tiros a puerta genera y permite cada equipo, y cuántos goles, ajustado por rival (los juegos recientes pesan más).'],
      ['Porteros', 'Toma el portero probable de cada equipo (el que más juegos empezó últimamente; en el segundo de dos días seguidos, el suplente) y su % de atajadas, ajustado a la media de la liga. Goles esperados = tiros esperados x (1 − atajadas del portero rival).'],
      ['Simulación', 'Juega el partido 20 000 veces: tiempo regular y, si empatan, prórroga 3 contra 3 y shootout. De ahí salen la probabilidad de ganar, de la prórroga, de ganar por 2 o más (−1.5) y los marcadores más repetidos.'],
      ['Precio', 'Compara con Pinnacle sin margen y con más de 20 casas: pick confiable con 4 % o más de ventaja y 45 % o más de probabilidad; valor probado con 3 % o más entre 25 % y 45 %.'],
      ['En prueba', 'Con tiros y porteros el motor mejoró en el backtest 2016-2023 (log-loss de 0,671 a 0,667), pero el cierre sigue un poco mejor (0,662): decide el precio y el motor se mide aparte hasta demostrar que suma.']] },
    NFL: { t: 'Cómo trabaja el motor de la NFL', p: [
      ['EPA', 'Con cada jugada de nflverse mide cuántos puntos esperados gana o pierde cada ataque y cada defensa por jugada, ajustado por rival, sin los minutos de la basura.'],
      ['Puntos', 'Suma los puntos a favor y en contra ajustados por rival y la ventaja de local.'],
      ['Mariscal', 'Mide a cada QB por EPA por jugada de pase (los que tienen poco historial parten como suplentes). Si el titular del juego es mejor o peor que quien venía lanzando, ajusta el margen.'],
      ['Simulación', 'El margen y el total salen de miles de juegos reales con un margen esperado parecido, así respeta los números clave (3, 7, 10).'],
      ['En prueba', 'En el backtest 2014-2026 su error medio fue 10,28 puntos (10,33 sin el ajuste del mariscal) contra 9,92 del cierre: decide el precio y el motor se mide aparte.']],
      n: 'El titular sale del calendario de nflverse; lesiones del resto del equipo todavía no entran.' },
    MLB: { t: 'Cómo trabaja el motor de MLB', p: [
      ['Statcast', 'Baja cada lanzamiento de la temporada: velocidad de bate, ángulo y velocidad de salida, giro de la bola. Con eso mide la calidad real del contacto (xwOBA), la tendencia al jonrón y al ponche de cada bateador y lanzador.'],
      ['Duelos', 'Cruza cada bateador con cada lanzador con un Log5 jerárquico (liga, equipo, jugador) y ajusta por estadio y clima.'],
      ['Bullpen y salida del abridor', 'Estima en qué entrada sale el abridor y quién del bullpen entra, relevista por relevista.'],
      ['Simulación', 'Juega cada juego más de 10 000 veces y saca la probabilidad de ganar, del total de carreras y del run line.'],
      ['Filtros', 'Pick confiable solo con valor esperado positivo y confianza suficiente. El V3 quedó como motor principal; el PRO V5 y el V5 base quedan como referencia.']],
      n: 'En stand-by hasta la temporada 2027. Aquí queda el historial de 2026.' },
  };
  const pintarComoMotor = () => {
    const m = MOTOR[dep] || MOTOR.Todos;
    $('#motor-titulo').textContent = m.t;
    const ol = $('#motor-pasos');
    ol.replaceChildren();
    for (const [t, d] of m.p) {
      const li = el('li');
      li.append(el('b', '', t + '. '), document.createTextNode(d));
      ol.append(li);
    }
    $('#motor-nota').textContent = m.n || '';
    $('#motor-nota').hidden = !m.n;
  };

  const pintar = () => {
    document.body.dataset.dep = dep;
    ajustarTabs();
    $('#hoy-bloque-picks').hidden = dep === 'MLB';
    $('#hoy-picks').hidden = SOLO_PRECIO.has(dep);
    $('#hoy-bloque-motor').hidden = dep === 'MLB';
    $('#hoy-pend').closest('.caja').hidden = SOLO_PRECIO.has(dep);
    $('#hoy-pend').closest('.caja').previousElementSibling.hidden = SOLO_PRECIO.has(dep);
    $('#motor').hidden = SOLO_PRECIO.has(dep);
    $('#explorar').hidden = SOLO_PRECIO.has(dep);
    document.querySelectorAll('.deportes button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.dep === dep)));
    pintarComoMotor();
    const dia = pintarCabecera();
    pintarHoy(dia);
    pintarFutbol();
    pintarPrecios();
    pintarVigilanteHoy();
    pintarResultados();
    pintarHistorial();
    pintarAnalisis();
    pintarPicks();
    pintarLigas();
    pintarRendimiento();
    pintarMotor();
    pintarExplorar();
  };

  document.querySelectorAll('.deportes button').forEach((b) => b.addEventListener('click', () => { dep = b.dataset.dep; pintar(); }));
  $('#res-dia').addEventListener('change', () => pintarResultados());
  $('#his-tipo').addEventListener('change', () => { hisTopeP = 50; hisTopeJ = 50; pintarHistorial(); });
  $('#his-mes').addEventListener('change', () => { hisTopeP = 50; hisTopeJ = 50; pintarHistorial(); });
  $('#his-mas-p').addEventListener('click', () => { hisTopeP += 50; pintarHistorial(); });
  $('#his-mas-j').addEventListener('click', () => { hisTopeJ += 50; pintarHistorial(); });
  $('#pre-mas').addEventListener('click', () => { preTope += 20; pintarPrecios(); });
  $('#lig-sel').addEventListener('change', () => pintarLigas());
  let ancho = window.innerWidth;
  window.addEventListener('resize', () => { if (D && window.innerWidth !== ancho) { ancho = window.innerWidth; pintarRendimiento(); } });

  const leer = (u) => fetch(u, { cache: 'no-store' }).then((r) => { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); });
  Promise.all([leer('datos/vitrina.json'), leer('datos/posiciones.json').catch(() => ({ ligas: [] })), leer('datos/futbol_dia.json').catch(() => null), leer('datos/precios.json').catch(() => null), leer('datos/analisis.json').catch(() => null), leer('datos/motores_eeuu.json').catch(() => null), leer('datos/juegos_analisis.json').catch(() => null)])
    .then(([doc, pos, fut, pre, an, me, ja]) => {
      JA = ja;
      AN = an;
      ME = me;
      FUT = fut;
      PR = pre;
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
