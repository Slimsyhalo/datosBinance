# Estado de entrega

Repositorio creado: https://github.com/Slimsyhalo/datosBinance. Código e informes publicados.

Release publicada: https://github.com/Slimsyhalo/datosBinance/releases/tag/dataset-2026-10-09. Once paquetes de datos (3,82 GB decimales), ASSETS_INDEX.json y ASSETS_SHA256.txt. Los checksums mostrados por GitHub coinciden con los archivos locales.

La adquisición de datos públicos quedó interrumpida por permisos de red. Se conservan 727 fuentes verificadas y se detallan 483 pendientes.

El paquete principal contiene código, velas BTC/ETH, features, datos auxiliares adquiridos, macros, escenarios de costos e informes.
Los 138 días de trades BTC adquiridos están en diez paquetes separados `BTC_Trades_Parte_01.zip` → `BTC_Trades_Parte_10.zip`. ETH trades está pendiente.
Extraer todos en la misma carpeta para reconstruir `binance-btc-eth-research/data/raw`.

El workflow incluido permite reanudar desde GitHub y publicar los datos como Releases cuando el workflow se ejecute.
No se ha ejecutado ese workflow.
