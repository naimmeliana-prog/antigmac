MacToXtreamAntig

Herramienta para extraer listas IPTV (Xtream/M3U + JSON VOD manifest) desde portales Stalker/MAC.

Características:
- Extrae playlists desde un portal MAC/Stalker configurable.
- Aplica filtros por idioma/país y por categoría (Live / Movies / Series).
- Genera M3U categorizadas y un JSON con estructura VOD (series, temporadas, episodios).
- Diseñado para ejecutarse en GitHub Actions y ser servido por un Cloudflare Worker.

Archivos principales:
- `generate.py` — entrada principal.
- `mac_to_xtream/extractor.py` — lógica de recuperación y filtrado.
- `config.sample.yaml` — ejemplo de configuración.

Siguientes pasos:
1. Copiar `config.sample.yaml` a `config.yaml` y ajustar `portal_url` y `mac` (o usar secrets en Actions).
2. Añadir secrets en GitHub: `PORTAL_URL`, `PORTAL_MAC`, `GIT_USER_NAME`, `GIT_USER_EMAIL` si se desea commit automático.
3. Configurar Cloudflare Worker con los detalles del repo (ver `cloudflare_worker/README.md`).
