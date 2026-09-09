"""
stalker_client.py
-----------------
Cliente para portales Stalker Middleware (MAG set-top box emulation).
Gestiona autenticación, tokens, y extracción de contenidos (Live TV, VOD, Series).
"""

import requests
import logging
import time
import json
import urllib.parse
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# User-Agent que simula un MAG200/STB
MAG_USER_AGENT = (
    "Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) "
    "MAG200 stbapp ver: 4 rev: 2116 Mobile Safari/533.3"
)

# Cabeceras estándar STB
STB_HEADERS = {
    "User-Agent": MAG_USER_AGENT,
    "Accept": "*/*",
    "Accept-Language": "en,*",
    "Accept-Encoding": "gzip, deflate",
    "X-User-Agent": "Model: MAG200; Link: Ethernet",
}


class StalkerAuthError(Exception):
    """Error de autenticación con el portal Stalker."""
    pass


class StalkerClient:
    """
    Cliente para interactuar con portales Stalker Middleware.
    Emula el comportamiento de un MAG200 set-top box.
    """

    def __init__(
        self,
        portal_url: str,
        mac: str,
        serial: str = "FFFFFFFF00000001",
        device_id: str = "00000000000000000000000000000001",
        device_id2: str = "00000000000000000000000000000001",
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 5,
    ):
        """
        Args:
            portal_url: URL base del portal (ej: http://mag.greatott.me:80)
            mac: Dirección MAC del dispositivo (ej: 00:1A:79:74:B1:B9)
            serial: Número de serie del STB
            device_id: Device ID del STB
            device_id2: Device ID2 del STB
            timeout: Timeout de peticiones en segundos
            max_retries: Número máximo de reintentos
            retry_delay: Segundos entre reintentos
        """
        self.portal_url = portal_url.rstrip("/")
        self.mac = mac
        self.serial = serial
        self.device_id = device_id
        self.device_id2 = device_id2
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.token: Optional[str] = None
        self.session = requests.Session()
        self.session.headers.update(STB_HEADERS)

        # Cookie inicial con la MAC
        self.session.cookies.set("mac", mac)
        self.session.cookies.set("stb_lang", "es")
        self.session.cookies.set("timezone", "Europe/Madrid")

    def _portal_endpoint(self, path: str = "/portal.php") -> str:
        """Construye la URL del endpoint del portal."""
        return f"{self.portal_url}{path}"

    def _request(
        self,
        params: Dict[str, Any],
        path: str = "/portal.php",
        extra_headers: Optional[Dict] = None,
    ) -> Optional[Dict]:
        """
        Realiza una petición GET al portal con reintentos automáticos.
        """
        url = self._portal_endpoint(path)
        headers = {}
        if extra_headers:
            headers.update(extra_headers)
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
                resp.raise_for_status()

                # Algunos portales devuelven JSONP o texto plano
                content = resp.text.strip()

                # Intentar decodificar JSON directamente
                try:
                    return resp.json()
                except ValueError:
                    # Puede venir envuelto en "jQuery..." JSONP
                    if content.startswith("{") or content.startswith("["):
                        return json.loads(content)
                    logger.debug(f"Respuesta no-JSON: {content[:200]}")
                    return None

            except requests.RequestException as e:
                logger.warning(f"Intento {attempt}/{self.max_retries} fallido: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
                else:
                    logger.error(f"Fallo definitivo en petición a {url}: {e}")
                    return None

    def authenticate(self) -> bool:
        """
        Realiza el flujo completo de autenticación MAG:
        1. Handshake → obtiene token
        2. get_profile → confirma sesión
        3. do_auth → autenticación completa
        """
        logger.info(f"Autenticando con portal {self.portal_url} (MAC: {self.mac})")

        # ── Paso 1: Handshake ──────────────────────────────────────────────
        handshake_params = {
            "type": "stb",
            "action": "handshake",
            "prehash": "0",
            "token": "",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(handshake_params)
        if not result:
            # Intentar con path /c/
            result = self._request(handshake_params, path="/c/")

        if result and isinstance(result, dict):
            js = result.get("js", {})
            if isinstance(js, dict):
                self.token = js.get("token", "")
            elif isinstance(js, str):
                self.token = js
            logger.debug(f"Token obtenido: {self.token}")

        if not self.token:
            logger.warning("No se pudo obtener token del handshake, continuando sin token...")

        # Actualizar cookie con token
        if self.token:
            self.session.cookies.set("token", self.token)

        # ── Paso 2: Get Profile ────────────────────────────────────────────
        profile_params = {
            "type": "stb",
            "action": "get_profile",
            "hd": "1",
            "ver": "ImageDescription: ; ImageDate: ; PORTAL version: 5.6.4; API Version: JS API version: 341; ",
            "num_banks": "1",
            "sn": self.serial,
            "stb_type": "MAG200",
            "client_type": "STB",
            "image_version": "218",
            "video_out": "hdmi",
            "device_id": self.device_id,
            "device_id2": self.device_id2,
            "signature": self.device_id2,
            "auth_second_step": "1",
            "hw_version": "1.7-BD-00",
            "not_valid_token": "0",
            "JsHttpRequest": "1-xml",
        }
        profile = self._request(profile_params)
        if profile:
            logger.debug("Perfil obtenido correctamente")

        # ── Paso 3: do_auth ────────────────────────────────────────────────
        auth_params = {
            "type": "stb",
            "action": "do_auth",
            "JsHttpRequest": "1-xml",
        }
        auth = self._request(auth_params)
        if auth:
            js = auth.get("js", {})
            if isinstance(js, dict) and js.get("status", "") == "1":
                logger.info("✅ Autenticación completada correctamente")
                return True
            # Algunos portales no implementan do_auth, lo consideramos OK
            logger.info("✅ Portal activo (do_auth no requerido)")
            return True

        # Si llegamos aquí pero tenemos token, asumimos autenticación parcial
        if self.token:
            logger.info("✅ Autenticación parcial (solo handshake)")
            return True

        raise StalkerAuthError(f"No se pudo autenticar con {self.portal_url}")

    # ──────────────────────────────────────────────────────────────────────────
    # LIVE TV
    # ──────────────────────────────────────────────────────────────────────────

    def get_live_categories(self) -> List[Dict]:
        """Obtiene todas las categorías de TV en Vivo."""
        logger.info("Obteniendo categorías de TV en Vivo...")
        params = {
            "type": "itv",
            "action": "get_genres",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(params)
        if result and "js" in result:
            categories = result["js"]
            if isinstance(categories, list):
                logger.info(f"  → {len(categories)} categorías Live encontradas")
                return categories
        return []

    def get_live_channels(self, category_id: str = "*") -> List[Dict]:
        """
        Obtiene todos los canales en Vivo.
        Itera por páginas si hay más de page_size resultados.
        """
        logger.info(f"Obteniendo canales Live (categoría: {category_id})...")
        all_channels = []
        page = 0
        page_size = 14  # Stalker devuelve 14 por defecto

        while True:
            params = {
                "type": "itv",
                "action": "get_ordered_list",
                "genre": category_id,
                "force_ch_link_check": "0",
                "fav": "0",
                "sortby": "name",
                "p": str(page),
                "JsHttpRequest": "1-xml",
            }
            result = self._request(params)
            if not result or "js" not in result:
                break

            js = result["js"]
            data = js.get("data", []) if isinstance(js, dict) else []

            if not data:
                break

            all_channels.extend(data)
            total_items = int(js.get("total_items", len(data)))
            logger.debug(f"  Página {page}: {len(data)} canales (total: {total_items})")

            if len(all_channels) >= total_items:
                break
            page += 1

        logger.info(f"  → {len(all_channels)} canales Live totales")
        return all_channels

    def get_all_live_channels_by_category(self, categories: List[Dict]) -> List[Dict]:
        """Obtiene todos los canales de todas las categorías."""
        all_channels = []
        seen_ids = set()

        for cat in categories:
            cat_id = str(cat.get("id", "*"))
            channels = self.get_live_channels(cat_id)
            for ch in channels:
                ch_id = ch.get("id", "")
                if ch_id and ch_id not in seen_ids:
                    seen_ids.add(ch_id)
                    ch["_category_id"] = cat_id
                    ch["_category_name"] = cat.get("title", "")
                    all_channels.append(ch)

        return all_channels

    # ──────────────────────────────────────────────────────────────────────────
    # VOD / PELÍCULAS
    # ──────────────────────────────────────────────────────────────────────────

    def get_vod_categories(self) -> List[Dict]:
        """Obtiene todas las categorías de VOD (Películas)."""
        logger.info("Obteniendo categorías de Películas...")
        params = {
            "type": "vod",
            "action": "get_categories",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(params)
        if result and "js" in result:
            categories = result["js"]
            if isinstance(categories, list):
                logger.info(f"  → {len(categories)} categorías VOD encontradas")
                return categories
        return []

    def get_vod_movies(self, category_id: str = "*", page: int = 0) -> List[Dict]:
        """Obtiene películas VOD de una categoría, con paginación."""
        params = {
            "type": "vod",
            "action": "get_ordered_list",
            "category": category_id,
            "p": str(page),
            "sortby": "name",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(params)
        if result and "js" in result:
            js = result["js"]
            if isinstance(js, dict):
                return js.get("data", []), int(js.get("total_items", 0))
        return [], 0

    def get_all_vod_by_category(self, categories: List[Dict]) -> List[Dict]:
        """Obtiene todas las películas de todas las categorías VOD."""
        all_movies = []
        seen_ids = set()

        for cat in categories:
            cat_id = str(cat.get("id", "*"))
            cat_name = cat.get("title", "")
            # Omitir categorías comodín "All" / "*" si hay más categorías específicas
            if (cat_id in ("*", "0") or cat_name.lower() in ("all", "todas")) and len(categories) > 1:
                logger.info(f"  → Omitiendo categoría comodín '{cat_name}'")
                continue

            page = 0
            cat_count = 0

            logger.info(f"  → Categoría VOD: '{cat_name}'")
            while True:
                movies, total = self.get_vod_movies(cat_id, page)
                if not movies:
                    break

                new_in_page = 0
                for movie in movies:
                    cat_count += 1
                    movie_id = movie.get("id", "")
                    if movie_id and movie_id not in seen_ids:
                        seen_ids.add(movie_id)
                        movie["_category_id"] = cat_id
                        movie["_category_name"] = cat_name
                        all_movies.append(movie)
                        new_in_page += 1

                page += 1
                if (total > 0 and cat_count >= total) or len(movies) < 14 or new_in_page == 0 or page >= 100:
                    break

        logger.info(f"  → {len(all_movies)} películas VOD totales")
        return all_movies

    # ──────────────────────────────────────────────────────────────────────────
    # SERIES
    # ──────────────────────────────────────────────────────────────────────────

    def get_series_categories(self) -> List[Dict]:
        """Obtiene todas las categorías de Series."""
        logger.info("Obteniendo categorías de Series...")
        params = {
            "type": "series",
            "action": "get_categories",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(params)
        if result and "js" in result:
            categories = result["js"]
            if isinstance(categories, list):
                logger.info(f"  → {len(categories)} categorías de Series encontradas")
                return categories

        # Fallback: algunos portales usan VOD para series también
        logger.info("Intentando categorías de series via vod/series...")
        params["type"] = "vod"
        params["series"] = "1"
        result = self._request(params)
        if result and "js" in result:
            categories = result["js"]
            if isinstance(categories, list):
                return categories
        return []

    def get_series_list(self, category_id: str = "*", page: int = 0) -> tuple:
        """Obtiene la lista de series de una categoría."""
        params = {
            "type": "series",
            "action": "get_ordered_list",
            "category": category_id,
            "p": str(page),
            "sortby": "name",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(params)
        if result and "js" in result:
            js = result["js"]
            if isinstance(js, dict):
                return js.get("data", []), int(js.get("total_items", 0))
        return [], 0

    def get_series_info(self, series_id: str) -> Optional[Dict]:
        """
        Obtiene temporadas y episodios de una serie usando el protocolo Stalker real.
        
        Protocolo:
        1. get_ordered_list(movie_id=X) → lista de temporadas
        2. Cada temporada tiene sus episodios en season['series'] o season['episodes']
        3. Para resolver el stream: create_link(cmd=season_cmd, series=ep_num)
        
        Basado en el proyecto de referencia stalker-m3u.
        """
        # ── Obtener temporadas paginadas ──────────────────────────────────────
        seasons = []
        page = 1
        total = 0
        for _ in range(100):  # max 100 páginas de temporadas
            params = {
                "type": "series",
                "action": "get_ordered_list",
                "movie_id": str(series_id),
                "p": str(page),
                "JsHttpRequest": "1-xml",
            }
            result = self._request(params)
            if not result or "js" not in result:
                break
            js = result["js"]
            if not isinstance(js, dict):
                break
            data = js.get("data", [])
            # Normalizar: puede venir como dict de grupos
            if isinstance(data, dict):
                data = [item for group in data.values() for item in (group if isinstance(group, list) else [group])]
            if not isinstance(data, list) or not data:
                break
            t = int(js.get("total_items") or 0)
            if t:
                total = t
            seasons.extend(data)
            if total and len(seasons) >= total:
                break
            page += 1

        if not seasons:
            return None

        # ── Procesar episodios de cada temporada ──────────────────────────────
        import re as _re
        season_num_re = _re.compile(r"(\d+)")
        all_episodes_flat = []

        for idx, season in enumerate(seasons, 1):
            # Número de temporada: extraer del campo "name" de la temporada
            match = season_num_re.search(str(season.get("name") or ""))
            season_num = int(match.group(1)) if match else idx
            
            # cmd de la temporada (sirve para todas las URLs de la misma temporada)
            season_cmd = season.get("cmd", "")

            # Episodios: pueden venir en season['series'], ['episodes'], ['list']
            raw_eps = season.get("series") or season.get("episodes") or season.get("list") or []
            if isinstance(raw_eps, dict):
                raw_eps = list(raw_eps.values())
            if not isinstance(raw_eps, list):
                raw_eps = [raw_eps] if raw_eps else []

            for ep_idx, ep in enumerate(raw_eps, 1):
                if isinstance(ep, dict):
                    ep_num = ep.get("series_number") or ep.get("num") or ep.get("id") or ep_idx
                    ep_name = ep.get("name", "")
                else:
                    ep_num = ep or ep_idx
                    ep_name = ""
                try:
                    ep_num = int(ep_num)
                except (ValueError, TypeError):
                    ep_num = ep_idx

                all_episodes_flat.append({
                    "season_number": season_num,
                    "episode_num": ep_num,
                    "name": ep_name or f"Episodio {ep_num}",
                    "cmd": season_cmd,   # cmd de la temporada
                    "_ep_series_num": ep_num,  # se pasa como 'series=' en create_link
                    "id": f"{series_id}_{season_num}_{ep_num}",
                })

        if all_episodes_flat:
            return {"data": all_episodes_flat, "total_items": len(all_episodes_flat)}
        return None


    def get_all_series_by_category(self, categories: List[Dict]) -> List[Dict]:
        """Obtiene todas las series de todas las categorías."""
        all_series = []
        seen_ids = set()

        for cat in categories:
            cat_id = str(cat.get("id", "*"))
            cat_name = cat.get("title", "")
            # Omitir categorías comodín "All" / "*" si hay más categorías específicas
            if (cat_id in ("*", "0") or cat_name.lower() in ("all", "todas")) and len(categories) > 1:
                logger.info(f"  → Omitiendo categoría comodín '{cat_name}'")
                continue

            page = 0
            cat_count = 0  # contador de items vistos en esta categoría

            logger.info(f"  → Categoría Series: '{cat_name}'")
            while True:
                series_list, total = self.get_series_list(cat_id, page)
                if not series_list:
                    break

                new_in_page = 0
                for serie in series_list:
                    cat_count += 1
                    serie_id = serie.get("id", "")
                    if serie_id and serie_id not in seen_ids:
                        seen_ids.add(serie_id)
                        serie["_category_id"] = cat_id
                        serie["_category_name"] = cat_name
                        all_series.append(serie)
                        new_in_page += 1

                page += 1
                if (total > 0 and cat_count >= total) or len(series_list) < 14 or new_in_page == 0 or page >= 100:
                    break

        logger.info(f"  → {len(all_series)} series totales")
        return all_series

    def create_stream_link(self, cmd: str, series: int = 0, is_live: bool = False) -> Optional[str]:
        """
        Genera un enlace de stream desde un comando Stalker.
        Usa type=itv para canales en vivo, type=vod para películas/episodios.
        Devuelve la URL directa limpia (sin prefijos ffrt/auto).
        """
        stream_type = "itv" if is_live else "vod"
        params = {
            "type": stream_type,
            "action": "create_link",
            "cmd": urllib.parse.quote(cmd),
            "series": str(series),
            "forced_storage": "undefined",
            "disable_ad": "0",
            "download": "0",
            "force_ch_link_check": "0",
            "JsHttpRequest": "1-xml",
        }
        result = self._request(params)
        if result and "js" in result:
            js = result["js"]
            if isinstance(js, dict):
                raw = js.get("cmd", js.get("url", ""))
            elif isinstance(js, str):
                raw = js
            else:
                return None
            # Limpiar prefijos ffrt/auto y devolver URL directa
            if raw:
                import re
                cleaned = re.sub(r'^(ffrt\d*|auto)\s+', '', raw.strip())
                return cleaned if cleaned else None
        return None

    def resolve_cmd_url(self, cmd: str, is_live: bool = False) -> str:
        """
        Resuelve un cmd Stalker a su URL directa.
        1. Si ya es una URL completa (http/https/rtmp), la devuelve limpia.
        2. Si es una ruta relativa, llama a create_link para obtener la URL real.
        3. Fallback: combina portalUrl + path.
        """
        import re
        if not cmd:
            return ""
        # Quitar prefijos ffrt/auto
        cleaned = re.sub(r'^(ffrt\d*|auto)\s+', '', cmd.strip())
        if cleaned.startswith(("http://", "https://", "rtmp://")):
            return cleaned
        # Es una ruta relativa → pedir create_link al portal
        resolved = self.create_stream_link(cmd, is_live=is_live)
        if resolved and resolved.startswith(("http://", "https://", "rtmp://")):
            return resolved
        # Fallback: combinar con portalUrl
        base = self.portal_url.rstrip("/")
        path = cleaned if cleaned.startswith("/") else f"/{cleaned}"
        return f"{base}{path}"

