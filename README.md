# Binance BTC / ETH Research

Dataset auditable de BTCUSDT y ETHUSDT, contratos perpetuos Binance USDⓈ-M Futures.
Ventana solicitada: **2026-05-09 00:00:00 UTC → 2026-10-09 00:00:00 UTC, extremo final exclusivo**.
Son cinco meses calendario completos hasta el último día completo al iniciar esta campaña.
Mercado elegido por continuidad con Binance QuantLab; no mezclar con Spot, COIN-M o precios de otro exchange.

Repositorio publicado: https://github.com/Slimsyhalo/datosBinance.

Checkpoint inicial: [Release dataset-2026-10-09](https://github.com/Slimsyhalo/datosBinance/releases/tag/dataset-2026-10-09). Descargar el paquete principal y las diez partes BTC; extraer todos en una misma carpeta. Cobertura parcial: 727/1210 fuentes, 483 pendientes. Velas 1m completas de ambos activos; trades BTC 138/153 días, ETH trades y L2 histórico completo pendientes.

**Estado real de esta entrega:** consultar [reports/QUALITY.md](reports/QUALITY.md) y
[reports/DELIVERY.md](reports/DELIVERY.md). Un script, una URL o un archivo planificado no es un dato adquirido.
No existe aún certificación integral para backtest de scalping con L2 histórico completo.

| Categoría solicitada | Contenido | Limitación que debe conservarse |
|---|---|---|
| Precio y volumen OHLCV | Velas 1m originales; derivación 5m, 15m y 1h | No rellenar huecos ni derivar velas incompletas |
| Trades individuales | ZIP diarios `trades`: ID, precio, cantidad, quote qty, tiempo y maker side | No sustituir por aggTrades; auditoría completa por partición; consultar el catálogo más reciente |
| Order Book L2 | `bookDepth` histórico como proxy agregado; capturador snapshot + diffs L2 | bookDepth **no** es L2 por niveles de precio; no permite reconstruirlo |
| Futures y open interest | Mark, index, premium index, funding, métricas OI/ratios | APIs y archivos tienen coberturas distintas; consultar faltantes |
| Volatilidad y tendencia | ATR14, RSI14, EMA20/50/200, volatilidad 30/60m, z-score y VWAP diario | Calculados al cierre; ventanas reiniciadas tras huecos |
| Contexto macroeconómico | Fuentes FRED, calendarios BLS y FOMC | Última revisión FRED, sin consenso ni sorpresas point-in-time certificados |
| Costos de ejecución | Escenarios de comisión y slippage; funding realizado | Escenarios no equivalen a costos reales históricos de la cuenta |
| Calidad y trazabilidad | URL fuente, SHA256 Binance/local, recuperación, tamaños, QA y faltantes | Integridad de bytes no certifica fidelidad temporal ni exactitud semántica total |

## Ejecutar

Python 3.11+:

```bash
python -m pip install .
quantdata plan
quantdata download --workers 8
quantdata macro
quantdata audit
quantdata trades-audit
python -m unittest discover -s tests -v
```

Para descargar sólo los trades pendientes:

```bash
quantdata download --categories trades --workers 6
quantdata audit
quantdata trades-audit
```

Cada ZIP debe coincidir con el SHA256 oficial. Las ejecuciones repetidas verifican los archivos existentes.
Los `.part` no se consideran adquiridos. Los manifiestos se guardan cada 20 archivos.
No ejecutar dos campañas de descarga simultáneas sobre el mismo directorio: el manifiesto tiene un único escritor.

Captura L2 real, hacia adelante, con límite explícito de duración:

```bash
quantdata l2 --seconds 60
```

Sin API keys. No envía órdenes. Un error de acceso/región se registra; no se elude.
Captura limitada al snapshot inicial de hasta 1000 niveles y sus actualizaciones; no certifica todo el libro fuera de ese alcance.

## Estructura

`data/raw/`: fuentes originales comprimidas y checksums.
`data/normalized/`: velas UTC, métricas, funding y profundidad agregada.
`data/features/`: indicadores causales, warmup con nulls, estado de validez.
`manifests/`: archivos solicitados/adquiridos, fuente y evidencia.
`reports/`: cobertura real, errores, condiciones pendientes.

Los datos grandes quedan fuera del historial Git. Para subirlos a **GitHub Releases**,
el workflow `Acquire and publish research data` descarga en GitHub y publica activos ZIP
de hasta unos 400 MB, con índices y QA. Seleccionar cada activo y cada uno de los seis meses
que intersectan la ventana. No se activa trading ni se requieren credenciales Binance.
El workflow se ejecuta manualmente: no afirmar que ya se ejecutó o que sus datos ya están publicados.

Releases tienen almacenamiento y límites propios de GitHub; revisar las políticas vigentes antes de campañas adicionales.
El repositorio de código es pequeño; el volumen de tick data no debe subirse mediante commits normales.

## Fuentes primarias

- https://github.com/binance/binance-public-data
- https://data.binance.vision/
- https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly
- https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data
- https://fred.stlouisfed.org/
- https://www.bls.gov/schedule/news_release/
- https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

Uso de datos sujeto a los términos de cada fuente, incluidos
https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md.
No se concede una licencia distinta sobre datos de terceros.

## Adquisición conjunta

El workflow manual `Complete BTC ETH five-month dataset` cubre la ventana aprobada mediante doce campañas mensuales, publica sus archivos y construye una Release conjunta. Los indicadores se recalculan sobre la ventana completa. El panel `data/joint/BTC_ETH_1m.csv.gz` alinea BTC y ETH; el catálogo enlaza todos los trades, hashes y faltantes. Cada campaña registra el tiempo de ejecución medido, excluyendo su cola. Publicar datos no implica certificar L2 histórico ni costos reales de cuenta.

## Último catálogo conjunto

https://github.com/Slimsyhalo/datosBinance/releases/tag/joint-BTC-ETH-37966554294-1

Fuentes verificadas: 1206/1210. Pendientes: 4. OHLCV y trades completos y auditados: True. Véase reports/JOINT_DELIVERY.md para cobertura exacta y límites.
