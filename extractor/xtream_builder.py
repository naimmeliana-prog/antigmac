"""
xtream_builder.py
-----------------
Transforma datos extraídos de portales Stalker Middleware
al formato Xtream Codes API estándar.

Genera los JSON que luego sirve el Cloudflare Worker.
"""

import logging
import hashlib
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _stable_id(source_id: Any, prefix: str = "") -> int:
    """
    Genera un ID numérico estable basado en el ID de origen.
    Usa hash para garantizar consistencia entre ejecuciones.
    """
    key = f"{prefix}_{source_id}"
    return int(hashlib.md5(key.encode()).hexdigest()[:8], 16) % 2_000_000_000


def _clean_name(name: str) -> str:
    """Limpia el nombre de un canal/película/serie."""
    if not name:
        return "Sin nombre"
    # Eliminar tags de idioma redundantes al inicio
    import re
    name = re.sub(r"^\s*\|?\s*", "", name)
    name = re.sub(r"\s*\|\s*$", "", name)
    return name.strip()


def _lang_to_flag(lang: str) -> str:
    """Convierte código de idioma a emoji de bandera."""
    flags = {
        "es_spain": "🇪🇸",
        "fr_france": "🇫🇷",
        "en_uk": "🇬🇧",
    }
    return flags.get(lang, "")


def _clean_cmd(cmd: str) -> str:
    """
    Limpia el prefijo Stalker del cmd para obtener una URL directamente reproducible.
    Stalker almacena los streams como: 'ffrt http://...' o 'ffrt1 http://...'
    Este prefijo debe eliminarse para obtener la URL real del stream.
    """
    import re
    if not cmd:
        return ""
    # Eliminar prefijos: ffrt, ffrt1, ffrt2, ffrt3, auto, etc.
    return re.sub(r'^(ffrt\d*|auto)\s+', '', cmd.strip())


# ═══════════════════════════════════════════════════════════════════════════════
# BUILDER PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

class XtreamBuilder:
    """
    Construye datos en formato Xtream Codes API a partir de datos Stalker.
    """

    def __init__(
        self,
        portal_url: str,
        worker_url: str,
        users: List[Dict],
        portal_id: str = "portal1",
    ):
        """
        Args:
            portal_url: URL base del portal Stalker (para proxy de streams)
            worker_url: URL del Cloudflare Worker (base URL del Xtream)
            users: Lista de usuarios Xtream [{username, password}]
            portal_id: ID del portal para namespacing de IDs
        """
        self.portal_url = portal_url.rstrip("/")
        self.worker_url = worker_url.rstrip("/")
        self.users = users
        self.portal_id = portal_id

    # ──────────────────────────────────────────────────────────────────────────
    # SERVER INFO
    # ──────────────────────────────────────────────────────────────────────────

    def build_server_info(self) -> Dict:
        """Genera la respuesta del endpoint principal (server info)."""
        now = int(time.time())
        return {
            "server_info": {
                "url": self.worker_url,
                "port": "80",
                "https_port": "443",
                "server_protocol": "http",
                "rtmp_port": "1935",
                "timezone": "Europe/Madrid",
                "timestamp_now": now,
                "time_now": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            },
            "user_info": {
                "username": self.users[0]["username"] if self.users else "user",
                "password": self.users[0]["password"] if self.users else "pass",
                "message": "MacToXtream - Listas IPTV España/Francia/UK",
                "auth": 1,
                "status": "Active",
                "exp_date": "9999999999",
                "is_trial": "0",
                "active_cons": "0",
                "created_at": str(now),
                "max_connections": "3",
                "allowed_output_formats": ["ts", "m3u8", "rtmp"],
            },
        }

    # ──────────────────────────────────────────────────────────────────────────
    # LIVE TV
    # ──────────────────────────────────────────────────────────────────────────

    def build_live_categories(self, stalker_categories: List[Dict]) -> List[Dict]:
        """
        Convierte categorías Stalker Live → formato Xtream.
        Agrupa por idioma con icono de bandera.
        """
        # Ordenar por idioma: ES → FR → UK
        lang_order = {"es_spain": 0, "fr_france": 1, "en_uk": 2, "": 3}
        sorted_cats = sorted(
            stalker_categories,
            key=lambda c: (lang_order.get(c.get("_lang", ""), 9), c.get("title", "")),
        )

        categories = []
        for cat in sorted_cats:
            cat_id = _stable_id(cat.get("id", cat.get("title", "")), f"{self.portal_id}_live_cat")
            lang = cat.get("_lang", "")
            flag = _lang_to_flag(lang)
            name = _clean_name(cat.get("title", cat.get("name", "Sin categoría")))

            categories.append({
                "category_id": str(cat_id),
                "category_name": f"{flag} {name}".strip(),
                "parent_id": 0,
                "_lang": lang,
                "_stalker_id": str(cat.get("id", "")),
            })

        return categories

    def build_live_streams(
        self,
        stalker_channels: List[Dict],
        xtream_categories: List[Dict],
    ) -> List[Dict]:
        """
        Convierte canales Stalker → formato Xtream Live Streams.
        """
        # Mapa de Stalker cat ID → Xtream cat ID
        cat_map = {
            c.get("_stalker_id", ""): c["category_id"]
            for c in xtream_categories
        }

        streams = []
        for ch in stalker_channels:
            stream_id = _stable_id(ch.get("id", ch.get("cmd", "")), f"{self.portal_id}_live")
            stalker_cat_id = str(ch.get("_category_id", ch.get("genre", "")))
            xtream_cat_id = cat_map.get(stalker_cat_id, "1")

            # URL del stream: el Worker redirigirá al portal original
            cmd = ch.get("cmd", "")

            name = _clean_name(ch.get("name", ch.get("title", "")))
            logo = ch.get("logo", ch.get("icon", ""))
            epg_id = ch.get("xmltv_id", ch.get("epg_channel_id", ""))

            streams.append({
                "num": len(streams) + 1,
                "name": name,
                "stream_type": "live",
                "stream_id": stream_id,
                "stream_icon": logo,
                "epg_channel_id": epg_id,
                "added": str(int(time.time())),
                "category_id": xtream_cat_id,
                "category_ids": [int(xtream_cat_id)],
                "custom_sid": "",
                "tv_archive": 0,
                "direct_source": "",
                "tv_archive_duration": 0,
                "_stalker_cmd": _clean_cmd(cmd),
                "_stalker_id": str(ch.get("id", "")),
                "_lang": ch.get("_lang", ""),
            })

        return streams

    # ──────────────────────────────────────────────────────────────────────────
    # VOD / PELÍCULAS
    # ──────────────────────────────────────────────────────────────────────────

    def build_vod_categories(self, stalker_categories: List[Dict]) -> List[Dict]:
        """Convierte categorías Stalker VOD → formato Xtream."""
        lang_order = {"es_spain": 0, "fr_france": 1, "": 2}
        sorted_cats = sorted(
            stalker_categories,
            key=lambda c: (lang_order.get(c.get("_lang", ""), 9), c.get("title", "")),
        )

        categories = []
        for cat in sorted_cats:
            cat_id = _stable_id(cat.get("id", cat.get("title", "")), f"{self.portal_id}_vod_cat")
            lang = cat.get("_lang", "")
            flag = _lang_to_flag(lang)
            name = _clean_name(cat.get("title", cat.get("name", "Sin categoría")))

            categories.append({
                "category_id": str(cat_id),
                "category_name": f"{flag} {name}".strip(),
                "parent_id": 0,
                "_lang": lang,
                "_stalker_id": str(cat.get("id", "")),
            })

        return categories

    def build_vod_streams(
        self,
        stalker_movies: List[Dict],
        xtream_categories: List[Dict],
    ) -> List[Dict]:
        """Convierte películas Stalker → formato Xtream VOD."""
        cat_map = {
            c.get("_stalker_id", ""): c["category_id"]
            for c in xtream_categories
        }

        streams = []
        for movie in stalker_movies:
            stream_id = _stable_id(movie.get("id", movie.get("cmd", "")), f"{self.portal_id}_vod")
            stalker_cat_id = str(movie.get("_category_id", ""))
            xtream_cat_id = cat_map.get(stalker_cat_id, "1")

            name = _clean_name(movie.get("name", movie.get("title", "")))
            cmd = movie.get("cmd", "")
            # Extensión del archivo (mkv, mp4, avi...)
            ext = movie.get("container_extension", "mkv")
            if not ext and cmd:
                import re
                m = re.search(r"\.(\w{2,4})$", cmd)
                ext = m.group(1) if m else "mkv"

            streams.append({
                "num": len(streams) + 1,
                "name": name,
                "stream_type": "movie",
                "stream_id": stream_id,
                "stream_icon": movie.get("screenshot_uri", movie.get("logo", "")),
                "rating": movie.get("rating", "0"),
                "rating_5based": float(movie.get("rating", 0)) / 2,
                "added": str(int(time.time())),
                "category_id": xtream_cat_id,
                "category_ids": [int(xtream_cat_id)],
                "container_extension": ext,
                "custom_sid": "",
                "direct_source": "",
                "_stalker_cmd": _clean_cmd(cmd),
                "_stalker_id": str(movie.get("id", "")),
                "_lang": movie.get("_lang", ""),
            })

        return streams

    # ──────────────────────────────────────────────────────────────────────────
    # SERIES
    # ──────────────────────────────────────────────────────────────────────────

    def build_series_categories(self, stalker_categories: List[Dict]) -> List[Dict]:
        """Convierte categorías Stalker Series → formato Xtream."""
        categories = []
        for cat in stalker_categories:
            cat_id = _stable_id(cat.get("id", cat.get("title", "")), f"{self.portal_id}_series_cat")
            name = _clean_name(cat.get("title", cat.get("name", "Sin categoría")))

            categories.append({
                "category_id": str(cat_id),
                "category_name": f"🇪🇸 {name}".strip(),
                "parent_id": 0,
                "_lang": "es_spain",
                "_stalker_id": str(cat.get("id", "")),
            })

        return categories

    def build_series_list(
        self,
        stalker_series: List[Dict],
        xtream_categories: List[Dict],
    ) -> List[Dict]:
        """Convierte lista de series Stalker → formato Xtream."""
        cat_map = {
            c.get("_stalker_id", ""): c["category_id"]
            for c in xtream_categories
        }

        series_list = []
        for serie in stalker_series:
            series_id = _stable_id(serie.get("id", serie.get("name", "")), f"{self.portal_id}_series")
            stalker_cat_id = str(serie.get("_category_id", ""))
            xtream_cat_id = cat_map.get(stalker_cat_id, "1")

            name = _clean_name(serie.get("name", serie.get("title", "")))
            cover = serie.get("screenshot_uri", serie.get("logo", serie.get("cover", "")))

            series_list.append({
                "num": len(series_list) + 1,
                "name": name,
                "series_id": series_id,
                "cover": cover,
                "plot": serie.get("description", serie.get("plot", "")),
                "cast": serie.get("actors", serie.get("cast", "")),
                "director": serie.get("director", ""),
                "genre": serie.get("genre_title", serie.get("genre", "")),
                "releaseDate": serie.get("year", ""),
                "last_modified": str(int(time.time())),
                "rating": serie.get("rating", "0"),
                "rating_5based": float(serie.get("rating", 0)) / 2,
                "backdrop_path": [],
                "youtube_trailer": "",
                "episode_run_time": serie.get("time", "0"),
                "category_id": xtream_cat_id,
                "category_ids": [int(xtream_cat_id)],
                "_stalker_id": str(serie.get("id", "")),
                "_lang": serie.get("_lang", ""),
            })

        return series_list

    def build_series_info(
        self,
        series_id: int,
        serie: Dict,
        stalker_info: Optional[Dict],
    ) -> Dict:
        """
        Construye el objeto completo de info de una serie:
        seasons + episodes por temporada.
        """
        name = _clean_name(serie.get("name", serie.get("title", "")))
        cover = serie.get("screenshot_uri", serie.get("logo", serie.get("cover", "")))

        seasons = {}
        episodes = {}

        if stalker_info and isinstance(stalker_info, dict):
            data = stalker_info.get("data", [])
            if not isinstance(data, list):
                # Algunos portales devuelven directamente la lista
                data = [stalker_info] if stalker_info else []

            for item in data:
                # ── Detectar número de temporada ──────────────────────────────
                # Stalker puede usar: season_number, season, s, serie_season...
                season_num = (
                    item.get("season_number")
                    or item.get("season")
                    or item.get("serie_season")
                    or item.get("s")
                    or 1
                )
                try:
                    season_num = int(season_num) or 1
                except (ValueError, TypeError):
                    season_num = 1

                # ── Detectar número de episodio ───────────────────────────────
                # Stalker puede usar: series_number, episode, episode_num, e, num...
                episode_num = (
                    item.get("series_number")
                    or item.get("episode_num")
                    or item.get("episode")
                    or item.get("num")
                    or item.get("e")
                    or item.get("order")
                    or 1
                )
                try:
                    episode_num = int(episode_num) or 1
                except (ValueError, TypeError):
                    episode_num = 1

                # Crear temporada si no existe
                if str(season_num) not in seasons:
                    seasons[str(season_num)] = {
                        "air_date": item.get("year", ""),
                        "episode_count": 0,
                        "id": _stable_id(f"{series_id}_s{season_num}", self.portal_id),
                        "name": f"Temporada {season_num}",
                        "overview": "",
                        "season_number": season_num,
                        "cover": cover,
                    }
                    episodes[str(season_num)] = []

                seasons[str(season_num)]["episode_count"] += 1

                ep_id = _stable_id(
                    item.get("id", f"{series_id}_s{season_num}_e{episode_num}"),
                    f"{self.portal_id}_ep",
                )
                cmd = item.get("cmd", "")
                ext = (
                    item.get("container_extension")
                    or item.get("ext")
                    or (cmd.rsplit(".", 1)[-1].split("?")[0] if "." in str(cmd) else "mkv")
                )

                episodes[str(season_num)].append({
                    "id": str(ep_id),
                    "episode_num": episode_num,
                    "title": _clean_name(item.get("name", f"Episodio {episode_num}")),
                    "container_extension": ext,
                    "info": {
                        "tmdb_id": "",
                        "releasedate": item.get("year", ""),
                        "plot": item.get("description", item.get("desc", "")),
                        "duration_secs": 0,
                        "duration": "00:00:00",
                        "video": {},
                        "audio": {},
                        "rating": item.get("rating", "0"),
                    },
                    "subtitles": [],
                    "custom_sid": "",
                    "added": str(int(time.time())),
                    "season": season_num,
                    "_stalker_cmd": _clean_cmd(cmd),
                    "_stalker_id": str(item.get("id", "")),
                })

        return {
            "seasons": list(seasons.values()),
            "info": {
                "name": name,
                "cover": cover,
                "plot": serie.get("description", ""),
                "cast": serie.get("actors", ""),
                "director": serie.get("director", ""),
                "genre": serie.get("genre_title", ""),
                "releaseDate": serie.get("year", ""),
                "last_modified": str(int(time.time())),
                "rating": serie.get("rating", "0"),
                "rating_5based": float(serie.get("rating", 0)) / 2,
                "backdrop_path": [],
                "youtube_trailer": "",
                "episode_run_time": serie.get("time", "0"),
                "category_id": serie.get("category_id", ""),
            },
            "episodes": episodes,
        }

    # ──────────────────────────────────────────────────────────────────────────
    # USERS
    # ──────────────────────────────────────────────────────────────────────────

    def build_users_data(self) -> List[Dict]:
        """Genera datos de usuarios Xtream para el Worker."""
        now = int(time.time())
        users_data = []
        for u in self.users:
            users_data.append({
                "username": u["username"],
                "password": u["password"],
                "status": "Active",
                "exp_date": "9999999999",
                "is_trial": "0",
                "active_cons": "0",
                "created_at": str(now),
                "max_connections": "3",
                "allowed_output_formats": ["ts", "m3u8", "rtmp"],
                "message": "MacToXtream",
                "auth": 1,
            })
        return users_data
