# Contrato de investigación

## Tiempo, exactitud y disponibilidad

- Fechas y almacenamiento UTC; se conserva el timestamp original en CSV raw.
- Futuros esperados en milisegundos. La detección explícita de microsegundos evita mezclas con Spot.
- Raw preserva decimales originales; las features calculadas usan float64, no apto para contabilidad exacta de órdenes.
- El flag isBuyerMaker indica comprador maker: `true` implica taker vendedor; no es posición short observada.
- Una vela sólo puede utilizarse a partir de open_time + duración; jamás antes del cierre.
- Download time/Last-Modified son evidencia de recuperación/publicación del objeto, no prueba del instante de disponibilidad de cada evento en vivo.
- No forward-fill de precios, OI, costos o macro sin una política explicitada y límites de antigüedad.
- Macros FRED del último vintage no se incorporan automáticamente a features de trading; requieren ALFRED/vintages y timestamp de publicación verificado.
- Calendario programado no demuestra que el evento se publicara puntualmente ni cuándo se conoció su valor.

## Costos

Por cada lado: `notional * fee_bps / 10000`, más `notional * slippage_bps / 10000`.
Entrada y salida se calculan por separado sobre sus nocionales respectivos.
El precio de mercado debe modelarse con bid/ask y profundidad cuando existan; no sumar un spread dos veces.
Funding sólo se contabiliza si la posición atraviesa el instante de pago, con signo según posición y tasa.
VIP, descuentos, promociones y cambios de tarifa requieren evidencia histórica de la cuenta; no se conocen aquí.
La latencia y el slippage no se pueden medir retroactivamente a partir de velas o bandas bookDepth.

## Alcance de auditoría

- Todos los archivos descargados: SHA256 completo contra `.CHECKSUM` de Binance.
- Velas: columnas, finitud, precios positivos, relaciones OHLC, tiempos, volumen, duplicados y cobertura esperada.
- OI: datos observados y timestamp faltantes frente a rejilla de 5 minutos; no crear puntos ausentes.
- bookDepth: columnas y profundidad no negativa; proxy por bandas porcentuales, sin certificación de libro completo.
- Trades: prechequeo de primeras 1000 filas por ZIP en `audit`; integridad SHA completa. `trades-audit` verifica todas las filas con memoria acotada, registra orden de IDs/tiempos, límites diarios y transición entre particiones. El resultado ejecutado está en `reports/trades_full.json`.
- Pruebas unitarias: límites de ventana, causalidad de features, warmup tras huecos y sincronización L2.

## Condiciones pendientes de certificación integral

1. Completar y verificar todos los archivos previstos de velas y trades.
2. Auditar todas las filas de trades, orden y continuidad de IDs por símbolo; documentar gaps explicables.
3. Obtener L2 histórico por niveles con snapshot+diffs y licencias adecuadas, o excluir hipótesis que dependan de él.
4. Verificar cobertura de OI/funding y no atribuir retrospectivamente disponibilidad no probada.
5. Obtener eventos macro point-in-time, actual/consenso y vintages si se usarán como predictores.
6. Calibrar tarifas, spread, slippage y latencia con datos de ejecución verificables.
7. Separar entrenamiento/validación/test temporal y mantener holdout sin optimización.

No se incluyen rentabilidades, recomendaciones de inversión, estrategia ni operaciones reales.
