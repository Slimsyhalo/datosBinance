# Informe de cobertura conjunta

Generado: 2026-10-09T18:04:34.896482+00:00

Ventana UTC: 2026-05-09 inclusive → 2026-10-09 exclusiva.

Fuentes primarias verificadas: 1206/1210. Faltantes: 4.

OHLCV y trades completos y auditados: Sí.

| Activo | Categoría | Archivos verificados / previstos | Filas observadas | Faltantes de velas 1m |
|---|---|---:|---:|---:|
| BTCUSDT | klines | 35/35 | 220320 | 0 |
| BTCUSDT | markPriceKlines | 35/35 | 220320 | 0 |
| BTCUSDT | indexPriceKlines | 35/35 | 220320 | 0 |
| BTCUSDT | premiumIndexKlines | 35/35 | 220320 | 0 |
| BTCUSDT | metrics | 153/153 | 44064 | — |
| BTCUSDT | bookDepth | 152/153 | 5157768 | — |
| BTCUSDT | fundingRate | 5/6 | 435 | — |
| ETHUSDT | klines | 35/35 | 220320 | 0 |
| ETHUSDT | markPriceKlines | 35/35 | 220320 | 0 |
| ETHUSDT | indexPriceKlines | 35/35 | 220320 | 0 |
| ETHUSDT | premiumIndexKlines | 35/35 | 220320 | 0 |
| ETHUSDT | metrics | 153/153 | 44064 | — |
| ETHUSDT | bookDepth | 152/153 | 5157768 | — |
| ETHUSDT | fundingRate | 5/6 | 435 | — |
| BTCUSDT | trades | 153/153 | 514499311 | — |
| ETHUSDT | trades | 153/153 | 738838491 | — |

Errores semánticos de QA: 0. Particiones de trades inválidas: 0. Errores entre particiones consecutivas: 0.

Los trades se auditaron fila por fila; los totales corresponden a operaciones individuales. Los saltos de ID se conservan en trades_full.json y no se interpretan automáticamente como operaciones perdidas.

El panel data/joint/BTC_ETH_1m.csv.gz alinea ambos activos por minuto UTC. El OI se une en timestamps exactos; no se interpola. Los indicadores se recalcularon sobre toda la ventana.

## Fuentes primarias ausentes

- `data/futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-2026-10-08.zip` — https://data.binance.vision/data/futures/um/daily/bookDepth/BTCUSDT/BTCUSDT-bookDepth-2026-10-08.zip
- `data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-10.zip` — https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-10.zip
- `data/futures/um/daily/bookDepth/ETHUSDT/ETHUSDT-bookDepth-2026-10-08.zip` — https://data.binance.vision/data/futures/um/daily/bookDepth/ETHUSDT/ETHUSDT-bookDepth-2026-10-08.zip
- `data/futures/um/monthly/fundingRate/ETHUSDT/ETHUSDT-fundingRate-2026-10.zip` — https://data.binance.vision/data/futures/um/monthly/fundingRate/ETHUSDT/ETHUSDT-fundingRate-2026-10.zip

## Límites del conjunto

- bookDepth es profundidad agregada por bandas; no contiene el L2 histórico completo por niveles de precio.
- Macro conserva las revisiones actuales y los calendarios adquiridos; no está certificada como información conocida en cada instante histórico.
- Comisiones y slippage son escenarios; no son costos históricos observados de la cuenta.

## Contexto macro

| Fuente | Estado | Observaciones / filas de calendario | Reutilizada tras timeout |
|---|---|---:|---|
| DFF | acquired | 152 | Sí |
| DGS2 | acquired | 108 | Sí |
| DGS10 | acquired | 108 | Sí |
| DTWEXBGS | error | — | No |
| VIXCLS | acquired | 109 | Sí |
| CPIAUCSL | acquired | 3 | Sí |
| UNRATE | acquired | 4 | Sí |
| cpi | acquired | 15 | Sí |
| employment | acquired | 15 | Sí |
| ppi | acquired | 15 | Sí |
| fomc | acquired | 0 | No |

DTWEXBGS no pudo adquirirse por timeout. Los calendarios no contienen consensos ni sorpresas macro certificados. FOMC conserva el HTML oficial; sus anuncios no se inventan ni se presentan como eventos extraídos.

- Funding API BTCUSDT: unavailable; HTTP Error 451: .
- Funding API ETHUSDT: unavailable; HTTP Error 451: .

[Release conjunta](https://github.com/Slimsyhalo/datosBinance/releases/tag/joint-BTC-ETH-37966554294-1).

[Catálogo de todos los archivos, miembros y hashes](JOINT_DELIVERY.json). [Resumen de entrega](JOINT_DELIVERY.md). [QA detallada](quality.json). [Auditoría de trades](trades_full.json).
