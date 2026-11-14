# Centro de Mando · página pública

Página estática (GitHub Pages) con los picks del día, resultados, posiciones por liga y rendimiento de los motores de NBA, LVBP y fútbol.

- `index.html`, `estilos.css`, `app.js`: la página.
- `datos/vitrina.json`: lo que publica el hub después de cada corrida (se copia de Drive).
- `datos/posiciones.json`: tablas de posiciones con últimos 5, racha y promedios (NBA, LVBP y ligas de fútbol, de fuentes públicas).
- `herramientas/actualizar.py` y `.github/workflows/actualizar.yml`: actualizan los datos cada 30 minutos y publican solo si algo cambió.

Registro de modelos estadísticos; no es una recomendación de apuesta.
