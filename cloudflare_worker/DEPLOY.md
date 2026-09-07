Despliegue del Cloudflare Worker

Requisitos:
- Tener una cuenta en Cloudflare
- `wrangler` instalado: `npm install -g wrangler`

Pasos:

1. Crear un API Token en Cloudflare con permisos para Workers (Worker Scripts: Edit)

2. Configurar `wrangler`:

```bash
wrangler login
# o con token
wrangler config
```

3. Ajusta `index.js` si necesitas cambiar `OWNER`, `REPO` o `BRANCH`.

4. Publicar el worker:

```bash
cd cloudflare_worker
wrangler publish
```

5. Configurar ruta y dominio en Cloudflare Dashboard si quieres un subpath específico.

GitHub Secrets recomendados (para el workflow):
- `PORTAL_URL` — URL base del portal
- `PORTAL_MAC` — MAC del portal
- `CF_API_TOKEN` — token de Cloudflare (si quieres automatizar deploys desde Actions)
