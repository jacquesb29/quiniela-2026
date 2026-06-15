# Evaluación de proveedores de cuotas — Mundial 2026

Objetivo: eliminar la dependencia manual de `data/market_odds_input.csv` alimentando el
pipeline F1/F7 con cuotas **pre-match 1X2** desde una **API oficial documentada** (sin scraping).

> Alcance honesto: los precios/límites reflejan los planes públicos vigentes al cierre de
> conocimiento (ene-2026) y pueden cambiar. Confirmar en la web del proveedor antes de contratar.

## Comparación

| Proveedor | Costo | Límites | Cobertura Mundial FIFA | 1X2 (h2h) | Pre-match | Live | Docs | Integración Python | Estabilidad | Multi-sportsbook |
|---|---|---|---|---|---|---|---|---|---|---|
| **The Odds API** | Freemium: 500 créditos/mes gratis; pago ~US$30 (20k), ~US$59, ~US$119+/mes | 1 crédito por región×mercado por llamada | Sí (`soccer_fifa_world_cup`) | **Sí** | **Sí** | Parcial | Muy buenas (REST/JSON) | **Muy fácil** (REST, `urllib`) | Alta | **Sí** (regiones us/uk/eu, decenas de casas) |
| **API-Football (api-sports.io)** | Freemium: 100 req/día gratis; pago ~US$19–US$39/mes | req/día por plan | Sí (fixtures WC + `/odds`) | Sí | Sí | Limitado | Buenas | Fácil (REST/JSON) | Alta | Sí (varias casas, pre-match) |
| **OddsJam** | Enterprise, custom (cientos US$/mes) | Altos / websockets | Excelente | Sí | Sí | **Sí (tiempo real)** | Buenas | Media (REST + WS) | Muy alta | Sí (100+ casas) |
| **Pinnacle API** | Sin API pública general (solo partners/afiliados) | n/d | Sí | Sí | Sí | Sí | Restringida | Media (acceso cerrado) | Alta | No (solo Pinnacle) |
| **Betfair Exchange API** | Gratis con App Key + cuenta fondeada | Throttling por peso | Sí | Back/Lay (no 1X2 fijo) | Sí | Sí | Extensas pero complejas | **Compleja** (login con certificado SSL, betting API) | Alta | No (es exchange, no casas) |
| **Sportradar Odds** | Enterprise, contrato (premium) | Por contrato | Excelente (oficial) | Sí | Sí | Sí | Excelentes | Media | Muy alta | Sí |
| **OddsAPI.io** | Bajo costo (~US$10–US$30/mes) | Por plan | Parcial/variable | Sí | Sí | Parcial | Aceptables | Fácil | Media (menos probada) | Sí |

## Análisis

- **Pinnacle / Sportradar / OddsJam**: técnicamente excelentes pero **caros o de acceso cerrado** (contrato enterprise o partner). Sobredimensionados para operar una quiniela.
- **Betfair**: potente pero es un **exchange** (back/lay), no entrega 1X2 fijo de casas; el login con certificado SSL añade complejidad alta. No ideal como fuente primaria de 1X2.
- **OddsAPI.io**: barato pero menos probado y con cobertura variable del Mundial.
- **The Odds API**: el mejor equilibrio costo/cobertura/facilidad. 1X2 (`h2h`) pre-match, sport key dedicado al Mundial, multi-casa por regiones, REST/JSON trivial en Python con `urllib`. **Ya viene cableado en el repo** (`THE_ODDS_API_KEY`, `soccer_fifa_world_cup`, `us,uk,eu`).
- **API-Football**: respaldo natural — también ya cableado (`API_FOOTBALL_KEY`), freemium generoso, cubre fixtures y `/odds` del Mundial.

## Recomendación final

- **Fuente principal: The Odds API** (`soccer_fifa_world_cup`, mercado `h2h`, formato decimal).
- **Fuente de respaldo: API-Football** (`/odds` de los fixtures del Mundial).

### Resumen ejecutivo
- **API recomendada:** The Odds API (respaldo API-Football).
- **Costo mensual estimado:** US$0 con el plan gratuito si se sondea con criterio (1 región `eu` = 1 crédito/llamada, T-90/T-60 por partido); **~US$30/mes** si se quiere multi-región (us/uk/eu) y sondeo frecuente cómodo.
- **Cobertura Mundial 2026:** completa para 1X2 pre-match vía `soccer_fifa_world_cup`; respaldo en API-Football si un partido falta.
- **Complejidad de integración:** **baja** — REST/JSON con `urllib` (sin dependencias nuevas), parser inyectable, caché en disco, reintentos y manejo de rate-limit ya implementados aquí.

### Reglas de uso (codificadas en el módulo)
- **Nunca** usar odds **live** para reemplazar pre-match (se descarta todo evento ya comenzado).
- **Nunca** etiquetar/usar **closing** para decisiones previas (solo se generan snapshots `open`/`t60`).
- Registrar **bookmaker** y **timestamp** (`source`, `captured_at_utc`).
- **Cachear** respuestas (TTL configurable), **reintentar** con backoff, **respetar rate limits** (429), y **fallback** al CSV existente si la API falla.

### Plan de implementación paso a paso
1. **Obtener API key** de The Odds API y exportarla: `export THE_ODDS_API_KEY=...` (opcional `API_FOOTBALL_KEY` para respaldo).
2. **Probar conectividad**: `python3 sync_market_odds.py --dry-run` (no escribe; muestra cuántos partidos/casas trae).
3. **Generar el CSV**: `python3 sync_market_odds.py` → regenera `data/market_odds_input.csv` (con backup `.bak`). Si la API falla o no hay key, **conserva** el CSV actual y deja warning.
4. **Encadenar en la operación diaria**: `run_daily_quiniela_ops.py` ya consume `data/market_odds_input.csv`; correr `sync_market_odds.py` antes del runner (o añadirlo como primer paso).
5. **Programar**: en días de partido, `sync_market_odds.py` cada 30–60 min vía el cron opcional ya existente.
6. **Validar**: revisar que `snapshot_type ∈ {open,t60}`, que cada fila tenga bookmaker+timestamp, y que el overround sea sano (el módulo rechaza cuotas inválidas).

El modelo, pesos, lambdas, metodología y selector Penca **no se tocan**: esto solo automatiza la **entrada de odds** del overlay operativo F1/F7.
