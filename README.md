# 📺 MacToXtream

Sistema que extrae listas IPTV de portales MAC Stalker y las sirve como **API Xtream Codes** completa mediante **Cloudflare Workers** y **GitHub Actions**. Sin servidor local necesario.

## ✨ Características

- 🔄 **Actualización automática** cada 6 horas via GitHub Actions
- ☁️ **Sin servidor local** — funciona 100% en la nube (Cloudflare + GitHub)
- 📺 **TV en Vivo** — Canales España 🇪🇸, Francia 🇫🇷 y UK 🇬🇧
- 🎬 **Películas** — España 🇪🇸 y Francia 🇫🇷
- 📦 **Series** — España 🇪🇸 con temporadas y episodios completos
- 🔐 **Multi-usuario** — Hasta 3 usuarios Xtream simultáneos
- 🔌 **Compatible con TiviPlayer** (WebOS) y cualquier app Xtream

## 🏗️ Arquitectura

```
Portal MAC Stalker         GitHub Repository           Cloudflare Worker
(mag.greatott.me)  →→→  /data/*.json (auto-update) →→→  antigmac.workers.dev
                              ↑                               ↓
                    GitHub Actions (cada 6h)          TiviPlayer (WebOS)
```

## 📁 Estructura del proyecto

```
antigmac/
├── .github/workflows/update_lists.yml   # Workflow de actualización automática
├── config/portals.json                  # Configuración de portales y usuarios
├── data/                                # JSONs Xtream (generados automáticamente)
│   ├── live_categories.json
│   ├── live_streams.json
│   ├── vod_categories.json
│   ├── vod_streams.json
│   ├── series_categories.json
│   ├── series.json
│   ├── series_info/{id}.json            # Temporadas + episodios por serie
│   ├── server_info.json
│   └── users.json
├── cloudflare/
│   ├── worker.js                        # Cloudflare Worker (API Xtream)
│   └── wrangler.toml                    # Configuración de despliegue
├── extractor/
│   ├── stalker_client.py               # Cliente Stalker Middleware
│   ├── filters.py                      # Filtros de idioma/región
│   ├── xtream_builder.py               # Conversor Stalker→Xtream
│   └── main.py                         # Script principal
└── requirements.txt
```

---

## 🚀 Guía de Configuración

### Paso 1 — Preparar el repositorio GitHub

1. Crea el repositorio en GitHub: `https://github.com/naimmeliana-prog/antigmac`
2. Sube todo el código a la rama `main`
3. Ve a **Settings → Actions → General** y activa:
   - *Allow all actions and reusable workflows*
   - En "Workflow permissions" selecciona **Read and write permissions**

### Paso 2 — Configurar GitHub Secrets (opcional pero recomendado)

Ve a **Settings → Secrets and variables → Actions** y añade:

| Secret | Valor | Descripción |
|--------|-------|-------------|
| `PORTAL_URL` | `http://mag.greatott.me:80` | URL del portal (opcional, ya está en config) |
| `PORTAL_MAC` | `00:1A:79:74:B1:B9` | MAC del portal (opcional) |
| `WORKER_URL` | `https://antigmac.workers.dev` | URL de tu Cloudflare Worker |

> **Nota:** Si no configuras los Secrets, el script usará los valores de `config/portals.json` directamente.

### Paso 3 — Desplegar el Cloudflare Worker

#### Opción A: Desde el Dashboard de Cloudflare (más fácil)

1. Ve a [dash.cloudflare.com](https://dash.cloudflare.com)
2. Inicia sesión (o crea cuenta gratuita)
3. Ir a **Workers & Pages → Create application → Create Worker**
4. Nombra el Worker: `antigmac`
5. Haz clic en **Edit code**
6. Pega el contenido de `cloudflare/worker.js`
7. Haz clic en **Save and Deploy**
8. Tu Worker estará en: `https://antigmac.TU_SUBDOMINIO.workers.dev`

#### Opción B: Con Wrangler CLI

```bash
# Instalar Wrangler
npm install -g wrangler

# Login en Cloudflare
wrangler login

# Entrar al directorio cloudflare
cd cloudflare

# Desplegar
wrangler deploy
```

#### Configurar variable de entorno en Cloudflare

En el Dashboard, ve a tu Worker → **Settings → Variables** y añade:

| Variable | Valor |
|----------|-------|
| `PORTAL_URL` | `http://mag.greatott.me:80` |

### Paso 4 — Actualizar la URL del Worker en la config

Edita `config/portals.json` y actualiza la URL del worker si es diferente a `https://antigmac.workers.dev`.

### Paso 5 — Ejecutar la primera extracción

**Opción A: Manualmente desde GitHub Actions**
1. Ve a tu repositorio → **Actions** → **🔄 Actualizar listas IPTV**
2. Haz clic en **Run workflow**
3. Espera 5-15 minutos a que termine

**Opción B: Localmente (para probar)**
```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar el extractor
python extractor/main.py --worker-url https://antigmac.TU_SUBDOMINIO.workers.dev
```

### Paso 6 — Configurar TiviPlayer en WebOS

1. Abre **TiviPlayer** en tu WebOS TV
2. Ve a **Configuración → Añadir lista**
3. Selecciona **Xtream Codes**
4. Introduce:
   - **Servidor:** `https://antigmac.TU_SUBDOMINIO.workers.dev`
   - **Usuario:** `antigmac1`
   - **Contraseña:** `antigpass1`
5. ¡Listo!

---

## 👥 Usuarios disponibles

| Usuario | Contraseña | Dispositivos simultáneos |
|---------|-----------|--------------------------|
| `antigmac1` | `antigpass1` | Hasta 3 |
| `antigmac2` | `antigpass2` | Hasta 3 |
| `antigmac3` | `antigpass3` | Hasta 3 |

> Para cambiar usuarios, edita `config/portals.json` → `xtream_users`

---

## 🔍 Filtros de contenido

### TV en Vivo
| Idioma | País | Excluye |
|--------|------|---------|
| 🇪🇸 Español | Solo España | Latino, México, Argentina, etc. |
| 🇫🇷 Francés | Solo Francia | Canadá, Bélgica, Suiza, África, Caribe |
| 🇬🇧 Inglés | Solo UK | USA, Irlanda, Australia, etc. |

### Películas
| Idioma | País | Excluye |
|--------|------|---------|
| 🇪🇸 Español | Solo España | Latino |
| 🇫🇷 Francés | Solo Francia | Canadá, Bélgica, etc. |

### Series
| Idioma | País |
|--------|------|
| 🇪🇸 Español | Solo España |

Para personalizar los filtros, edita `config/portals.json` → `filters` o los patrones en `extractor/filters.py`.

---

## 🔌 Endpoints API Xtream

| Endpoint | Descripción |
|----------|-------------|
| `GET /player_api.php?username=X&password=X` | Info del servidor y usuario |
| `GET /player_api.php?...&action=get_live_categories` | Categorías TV en Vivo |
| `GET /player_api.php?...&action=get_live_streams` | Canales en Vivo |
| `GET /player_api.php?...&action=get_vod_categories` | Categorías Películas |
| `GET /player_api.php?...&action=get_vod_streams` | Lista Películas |
| `GET /player_api.php?...&action=get_series_categories` | Categorías Series |
| `GET /player_api.php?...&action=get_series` | Lista Series |
| `GET /player_api.php?...&action=get_series_info&series_id=X` | Temporadas + Episodios |
| `GET /live/{user}/{pass}/{id}.ts` | Stream en Vivo |
| `GET /movie/{user}/{pass}/{id}.mkv` | Stream Película |
| `GET /get.php?username=X&password=X&type=m3u_plus` | Exportar M3U |

---

## 🔄 Actualización automática

El workflow de GitHub Actions se ejecuta automáticamente:
- **Cada 6 horas** (00:00, 06:00, 12:00, 18:00 UTC)
- **Manualmente** desde GitHub → Actions → Run workflow

Para cambiar la frecuencia, edita `.github/workflows/update_lists.yml`:
```yaml
- cron: "0 */6 * * *"  # Cada 6 horas
# - cron: "0 */12 * * *" # Cada 12 horas
# - cron: "0 0 * * *"    # Una vez al día a medianoche
```

---

## 🛠️ Añadir más portales

En el futuro, para añadir más portales edita `config/portals.json`:

```json
{
  "portals": [
    {
      "id": "portal1",
      "name": "GreatOTT",
      "enabled": true,
      "url": "http://mag.greatott.me:80",
      "mac": "00:1A:79:74:B1:B9"
    },
    {
      "id": "portal2",
      "name": "Otro Portal",
      "enabled": true,
      "url": "http://otro-portal.com:8080",
      "mac": "00:1A:79:XX:XX:XX"
    }
  ]
}
```

---

## 🐛 Resolución de problemas

### "Stream no encontrado" en TiviPlayer
- Asegúrate de que el Worker esté desplegado y accesible
- Verifica que los JSONs en `/data/` existen en GitHub
- Comprueba los logs del GitHub Action

### "Credenciales inválidas"
- Verifica usuario/contraseña en `config/portals.json` → `xtream_users`
- El Worker lee los usuarios desde `data/users.json` en GitHub

### El workflow falla
- Ve a Actions → click en el run fallido → revisa los logs
- El error más común es autenticación con el portal MAC
- El portal puede estar caído temporalmente

---

## 📝 Licencia

Uso personal. Asegúrate de usar únicamente portales a los que tienes acceso autorizado.
