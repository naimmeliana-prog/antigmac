"""
main.py
-------
Script principal de MacToXtream.

Orquesta la extracción de contenidos desde portales MAC Stalker,
aplica los filtros de idioma/región y genera los JSON en formato
Xtream Codes para ser servidos por el Cloudflare Worker.

Uso:
    python extractor/main.py [--config config/portals.json] [--data-dir data]
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

# ── Setup de rutas ────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "extractor"))

from extractor.stalker_client import StalkerClient, StalkerAuthError
from extractor.filters import ContentFilter
from extractor.xtream_builder import XtreamBuilder

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("mactoxtream")


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def load_config(config_path: str) -> Dict:
    """Carga la configuración desde portals.json."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    logger.info(f"Configuración cargada: {config_path}")
    return config


def save_json(data, filepath: Path, indent: int = 2) -> None:
    """Guarda datos como JSON en disco."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
    size_kb = filepath.stat().st_size / 1024
    logger.info(f"  💾 Guardado: {filepath} ({size_kb:.1f} KB)")


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESAMIENTO DE UN PORTAL
# ═══════════════════════════════════════════════════════════════════════════════

def process_portal(
    portal_config: Dict,
    xtream_users: List[Dict],
    worker_url: str,
    data_dir: Path,
    settings: Dict,
) -> bool:
    """
    Procesa un portal MAC Stalker completo:
    1. Autenticación
    2. Extracción de categorías y contenidos
    3. Filtrado por idioma/región
    4. Generación de JSONs Xtream

    Returns: True si el proceso fue exitoso
    """
    portal_id = portal_config["id"]
    portal_name = portal_config["name"]
    portal_url = portal_config["url"]
    mac = portal_config["mac"]

    logger.info(f"\n{'='*60}")
    logger.info(f"🚀 Procesando portal: {portal_name} ({portal_url})")
    logger.info(f"{'='*60}")

    # ── Inicializar cliente Stalker ────────────────────────────────────────────
    client = StalkerClient(
        portal_url=portal_url,
        mac=mac,
        serial=portal_config.get("serial", "FFFFFFFF00000001"),
        device_id=portal_config.get("device_id", "0" * 32),
        device_id2=portal_config.get("device_id2", "0" * 32),
        timeout=settings.get("request_timeout", 30),
        max_retries=settings.get("max_retries", 3),
        retry_delay=settings.get("retry_delay", 5),
    )

    # ── Autenticación ──────────────────────────────────────────────────────────
    try:
        client.authenticate()
    except StalkerAuthError as e:
        logger.error(f"❌ Fallo de autenticación: {e}")
        return False

    # ── Inicializar filtros y builder ─────────────────────────────────────────
    content_filter = ContentFilter()
    builder = XtreamBuilder(
        portal_url=portal_url,
        worker_url=worker_url,
        users=xtream_users,
        portal_id=portal_id,
    )

    # ── Directorio de salida para este portal ─────────────────────────────────
    portal_data_dir = data_dir

    # ── SERVER INFO ───────────────────────────────────────────────────────────
    logger.info("\n📡 Generando server info...")
    server_info = builder.build_server_info()
    save_json(server_info, portal_data_dir / "server_info.json")
    save_json(builder.build_users_data(), portal_data_dir / "users.json")

    # ══════════════════════════════════════════════════════════════════════════
    # LIVE TV
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("\n📺 Procesando TV en Vivo...")

    # Categorías
    raw_live_cats = client.get_live_categories()
    filtered_live_cats_raw = content_filter.filter_live_categories(raw_live_cats)
    xtream_live_cats = builder.build_live_categories(filtered_live_cats_raw)
    save_json(xtream_live_cats, portal_data_dir / "live_categories.json")

    # Canales
    logger.info(f"  Descargando canales de {len(filtered_live_cats_raw)} categorías...")
    raw_channels = client.get_all_live_channels_by_category(filtered_live_cats_raw)
    filtered_channels = content_filter.filter_live_channels(raw_channels, filtered_live_cats_raw)
    xtream_live_streams = builder.build_live_streams(filtered_channels, xtream_live_cats)
    
    # Eliminar categorías Live sin contenido
    used_live_cat_ids = {str(s["category_id"]) for s in xtream_live_streams}
    xtream_live_cats = [c for c in xtream_live_cats if str(c["category_id"]) in used_live_cat_ids]
    
    save_json(xtream_live_cats, portal_data_dir / "live_categories.json")
    save_json(xtream_live_streams, portal_data_dir / "live_streams.json")
    logger.info(f"  ✅ {len(xtream_live_cats)} categorías | {len(xtream_live_streams)} canales Live")

    # ══════════════════════════════════════════════════════════════════════════
    # PELÍCULAS (VOD)
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("\n🎬 Procesando Películas...")

    raw_vod_cats = client.get_vod_categories()
    filtered_vod_cats_raw = content_filter.filter_vod_categories(raw_vod_cats)
    xtream_vod_cats = builder.build_vod_categories(filtered_vod_cats_raw)

    logger.info(f"  Descargando películas de {len(filtered_vod_cats_raw)} categorías...")
    raw_movies = client.get_all_vod_by_category(filtered_vod_cats_raw)
    filtered_movies = content_filter.filter_movies(raw_movies, filtered_vod_cats_raw)
    xtream_vod_streams = builder.build_vod_streams(filtered_movies, xtream_vod_cats)

    # Eliminar categorías VOD sin contenido
    used_vod_cat_ids = {str(s["category_id"]) for s in xtream_vod_streams}
    xtream_vod_cats = [c for c in xtream_vod_cats if str(c["category_id"]) in used_vod_cat_ids]

    save_json(xtream_vod_cats, portal_data_dir / "vod_categories.json")
    save_json(xtream_vod_streams, portal_data_dir / "vod_streams.json")
    logger.info(f"  ✅ {len(xtream_vod_cats)} categorías | {len(xtream_vod_streams)} películas")

    # ══════════════════════════════════════════════════════════════════════════
    # SERIES
    # ══════════════════════════════════════════════════════════════════════════
    logger.info("\n📺 Procesando Series...")

    raw_series_cats = client.get_series_categories()
    filtered_series_cats_raw = content_filter.filter_series_categories(raw_series_cats)
    xtream_series_cats = builder.build_series_categories(filtered_series_cats_raw)

    logger.info(f"  Descargando series de {len(filtered_series_cats_raw)} categorías...")
    raw_series = client.get_all_series_by_category(filtered_series_cats_raw)
    filtered_series = content_filter.filter_series_list(raw_series, filtered_series_cats_raw)
    xtream_series_list = builder.build_series_list(filtered_series, xtream_series_cats)

    # Eliminar categorías de Series sin contenido
    used_series_cat_ids = {str(s["category_id"]) for s in xtream_series_list}
    xtream_series_cats = [c for c in xtream_series_cats if str(c["category_id"]) in used_series_cat_ids]

    save_json(xtream_series_cats, portal_data_dir / "series_categories.json")
    save_json(xtream_series_list, portal_data_dir / "series.json")
    logger.info(f"  ✅ {len(xtream_series_cats)} categorías | {len(xtream_series_list)} series")

    # ── Episodios y temporadas de cada serie ───────────────────────────────────
    logger.info(f"\n  📦 Descargando info de episodios ({len(xtream_series_list)} series)...")
    series_info_dir = portal_data_dir / "series_info"
    series_info_dir.mkdir(parents=True, exist_ok=True)

    # Mapa de xtream series_id → datos de la serie Stalker original
    stalker_series_map = {s.get("_stalker_id", ""): s for s in filtered_series}
    xtream_series_map = {str(xs["series_id"]): xs for xs in xtream_series_list}

    # Índice plano de episodios para que el Worker resuelva streams rápidamente
    episodes_index = []

    for idx, xs in enumerate(xtream_series_list, 1):
        stalker_id = xs.get("_stalker_id", "")
        series_id = xs["series_id"]
        stalker_serie = stalker_series_map.get(stalker_id, xs)

        if idx % 10 == 0 or idx == len(xtream_series_list):
            logger.info(f"    - Procesando episodios: {idx}/{len(xtream_series_list)} series...")

        try:
            stalker_info = client.get_series_info(stalker_id) if stalker_id else None
            series_info = builder.build_series_info(series_id, stalker_serie, stalker_info)
            save_json(series_info, series_info_dir / f"{series_id}.json", indent=0)

            # Añadir episodios al índice global
            for season_eps in series_info.get("episodes", {}).values():
                for ep in season_eps:
                    episodes_index.append({
                        "id": int(ep["id"]),
                        "episode_id": int(ep["id"]),
                        "series_id": series_id,
                        "season": ep.get("season", 1),
                        "episode_num": ep.get("episode_num", 1),
                        "title": ep.get("title", ""),
                        "container_extension": ep.get("container_extension", "mkv"),
                        "_stalker_cmd": ep.get("_stalker_cmd", ""),
                        "_stalker_series_num": ep.get("_stalker_series_num", ep.get("episode_num", 1)),
                    })


        except Exception as e:
            logger.warning(f"  ⚠️  No se pudo obtener info de '{xs.get('name', series_id)}': {e}")
            # Guardar info mínima
            minimal_info = builder.build_series_info(series_id, stalker_serie, None)
            save_json(minimal_info, series_info_dir / f"{series_id}.json", indent=0)

        time.sleep(0.1)  # Rate limiting educado

    # Guardar índice de episodios (usado por el Worker para resolver streams de series)
    if episodes_index:
        save_json(episodes_index, portal_data_dir / "episodes_index.json", indent=0)
        logger.info(f"  📋 Índice de episodios: {len(episodes_index)} episodios indexados")

    logger.info(f"\n✅ Portal '{portal_name}' procesado correctamente")
    return True


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="MacToXtream — Extractor de portales MAC Stalker a formato Xtream Codes"
    )
    parser.add_argument(
        "--config",
        default="config/portals.json",
        help="Ruta al archivo de configuración (default: config/portals.json)",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directorio de salida para los JSON generados (default: data)",
    )
    parser.add_argument(
        "--worker-url",
        default=os.environ.get("WORKER_URL", "https://antigmac.workers.dev"),
        help="URL del Cloudflare Worker (también desde env WORKER_URL)",
    )
    parser.add_argument(
        "--portal",
        default=None,
        help="ID de portal específico a procesar (default: todos los activos)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Modo verbose (DEBUG)",
    )
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # ── Cargar configuración ──────────────────────────────────────────────────
    config_path = ROOT_DIR / args.config if not os.path.isabs(args.config) else Path(args.config)
    if not config_path.exists():
        logger.error(f"❌ Archivo de configuración no encontrado: {config_path}")
        sys.exit(1)

    config = load_config(str(config_path))
    settings = config.get("settings", {})
    xtream_users = config.get("xtream_users", [])
    portals = config.get("portals", [])

    data_dir = ROOT_DIR / args.data_dir if not os.path.isabs(args.data_dir) else Path(args.data_dir)
    worker_url = args.worker_url

    logger.info(f"\n{'='*60}")
    logger.info(f"🌟 MacToXtream v1.0")
    logger.info(f"   Config:     {config_path}")
    logger.info(f"   Data dir:   {data_dir}")
    logger.info(f"   Worker URL: {worker_url}")
    logger.info(f"   Portales:   {len([p for p in portals if p.get('enabled', True)])}")
    logger.info(f"   Usuarios:   {len(xtream_users)}")
    logger.info(f"{'='*60}\n")

    # ── Procesar portales ─────────────────────────────────────────────────────
    success_count = 0
    fail_count = 0

    for portal in portals:
        if not portal.get("enabled", True):
            logger.info(f"⏭️  Portal '{portal['name']}' desactivado, saltando...")
            continue

        if args.portal and portal["id"] != args.portal:
            continue

        try:
            ok = process_portal(
                portal_config=portal,
                xtream_users=xtream_users,
                worker_url=worker_url,
                data_dir=data_dir,
                settings=settings,
            )
            if ok:
                success_count += 1
            else:
                fail_count += 1
        except Exception as e:
            logger.error(f"❌ Error inesperado procesando '{portal['name']}': {e}", exc_info=True)
            fail_count += 1

    # ── Resumen ───────────────────────────────────────────────────────────────
    logger.info(f"\n{'='*60}")
    logger.info(f"📊 Resumen final:")
    logger.info(f"   ✅ Portales exitosos: {success_count}")
    logger.info(f"   ❌ Portales fallidos: {fail_count}")
    logger.info(f"   📁 Datos en: {data_dir}")
    logger.info(f"{'='*60}\n")

    if fail_count > 0 and success_count == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
