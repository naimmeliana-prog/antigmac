Cloudflare Worker

Este Worker sirve archivos generados desde la rama `generated-playlists` del repositorio.

Pasos rápidos:
1. Ajusta `OWNER`, `REPO` y `BRANCH` en `index.js` si no coinciden.
2. Pulsa deploy en Cloudflare Workers o usa `wrangler`.
3. El Worker expondrá rutas como `/xtream/playlist.m3u` o `/xtream/manifest.json`.
