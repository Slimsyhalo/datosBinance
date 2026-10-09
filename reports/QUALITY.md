# Informe de cobertura real

Ventana UTC: 2026-05-09 inclusive → 2026-10-09 exclusive. Generado: 2026-10-09T16:38:58.622649+00:00

| Activo | Categoría | Archivos verificados / previstos | Filas observadas | Faltantes de velas 1m |
|---|---|---:|---:|---:|
| BTCUSDT | klines | 35/35 | 220320 | 0 |
| BTCUSDT | markPriceKlines | 35/35 | 218880 | 1440 |
| BTCUSDT | indexPriceKlines | 35/35 | 218880 | 1440 |
| BTCUSDT | premiumIndexKlines | 35/35 | 218880 | 1440 |
| BTCUSDT | trades | 138/153 | 469234948 | — |
| BTCUSDT | metrics | 153/153 | 44064 | — |
| BTCUSDT | bookDepth | 152/153 | 5157768 | — |
| BTCUSDT | fundingRate | 5/6 | 435 | — |
| ETHUSDT | klines | 35/35 | 220320 | 0 |
| ETHUSDT | markPriceKlines | 35/35 | 218880 | 1440 |
| ETHUSDT | indexPriceKlines | 35/35 | 218880 | 1440 |
| ETHUSDT | premiumIndexKlines | 34/35 | 217440 | 2880 |
| ETHUSDT | trades | 0/153 | 0 | — |
| ETHUSDT | metrics | 0/153 | 0 | — |
| ETHUSDT | bookDepth | 0/153 | 0 | — |
| ETHUSDT | fundingRate | 0/6 | 0 | — |

Archivos verificados: 727 / 1210 previstos. Pendientes/no accesibles: 483.

Trades BTC: 469,234,948 filas examinadas completamente en 138 particiones diarias. Precios/cantidades inválidos: 0; IDs no crecientes: 0; tiempos regresivos: 0; filas fuera del día: 0; inconsistencias precio×cantidad vs quote qty dentro de tolerancia: 0.

Transiciones no consecutivas de IDs dentro de particiones: 1,108,607. Son observaciones, no prueba automática de operaciones omitidas; requieren análisis de reglas de IDs y reconciliación de volumen.

OHLCV BTC y ETH: 220.320 velas 1m por activo, sin huecos. Features y velas derivadas incluidas.

Mark/index/premium: falta todo el día 2026-06-29 en fuentes adquiridas. ETH premium tiene además una partición no adquirida. Los huecos permanecen null.

OI BTC: 44.064 timestamps de 5 minutos, sin huecos en la rejilla; no equivale a disponibilidad histórica certificada de cada publicación. OI ETH: no adquirido.

L2 por precio: no adquirido. bookDepth BTC: proxy agregado, 152/153 días; ETH: no adquirido. Captura L2 en vivo no sincronizada por error 451 en snapshot.

Funding BTC: cinco archivos mensuales; datos normalizados hasta septiembre. Octubre y funding ETH pendientes.

Macros: 6 de 7 series FRED, 3 calendarios BLS (15 eventos programados), calendario FOMC en HTML. FRED usa vintage actual; sin consenso/sorpresas ni prueba point-in-time.

Costos: 18 escenarios hipotéticos de comisión y slippage; no costos históricos observados de una cuenta.

GitHub: repositorio Slimsyhalo/datosBinance creado; publicación de código y Release de datos en curso. Los procesos de adquisición finalizaron por cancelación de permisos de red.
