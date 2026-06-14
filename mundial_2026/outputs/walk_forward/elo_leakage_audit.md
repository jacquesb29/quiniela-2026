# Auditoría de leakage de Elo prepartido (F0.4b)

## 1. Auditoría de código del constructor original

`tools/build_real_historical_backtest.py` ordena todos los partidos por fecha, registra `elo_a_pre`/`elo_b_pre` con el rating ANTES del partido y ejecuta `update_elo` solo DESPUÉS. Equipos nuevos arrancan en 1500. No usa rankings ni resultados posteriores. Es **walk-forward por construcción**: `ELO_CODE_AUDIT_WALK_FORWARD = True`.

## 2. Re-derivación independiente (réplica fiel walk-forward)

- Partidos comparados: 1930
- Correlación de Pearson Elo A: 1.000000
- Correlación de Pearson Elo B: 1.000000
- Diferencia absoluta media: 0.000251 puntos Elo
- Diferencia absoluta máxima: 0.000500 puntos Elo

Una re-derivación independiente reproduce el Elo almacenado salvo ruido de redondeo (los valores se guardan con 3 decimales). Esto confirma que el Elo prepartido es un cómputo determinista sin información futura.

## 3. Backtest comparativo (Elo original vs Elo re-derivado)

- log-loss modelo (Elo original): 0.994444
- log-loss modelo (Elo re-derivado): 0.994444
- desviación de log-loss: 0.000000
- log-loss Poisson simple (re-derivado): 1.000576
- log-loss Elo puro (re-derivado): 1.003847
- modelo supera Poisson (re-derivado): True
- modelo supera Elo puro (re-derivado): True
- backtest estable: True

## 4. Veredicto de leakage

**leakage_warning = False**. No hay evidencia de fuga: auditoría de código walk-forward, re-derivación reproduce el Elo y el backtest es estable. Se permite apagar la advertencia de leakage.

Esto es auditoría anti-leakage, no optimización del modelo: no se cambiaron pesos, lambdas, metodología ni selector Penca.