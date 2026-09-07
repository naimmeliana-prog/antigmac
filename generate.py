import os
import argparse
import json
import logging
from pathlib import Path

from mac_to_xtream.extractor import try_endpoints, fetch_url, parse_m3u, classify_and_build, generate_m3u

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('generate')


def load_config(path: str) -> dict:
    import yaml
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', default='config.yaml')
    p.add_argument('--outdir', default='generated')
    args = p.parse_args()

    cfg_path = args.config
    if not os.path.exists(cfg_path):
        logger.error('Config file not found: %s', cfg_path)
        return

    cfg = load_config(cfg_path)
    portal = cfg.get('portal_url')
    mac = cfg.get('mac')
    filters = cfg.get('filters', {})

    endpoints = try_endpoints(portal, mac)
    logger.info('Detected endpoints: %s', endpoints)

    # prefer m3u-like endpoints
    playlist_text = None
    for name in ['m3u', 'playlist', 'player_api', 'portal']:
        url = endpoints.get(name)
        if not url:
            continue
        # try fetch raw
        playlist_text = fetch_url(url, params={'mac': mac})
        if playlist_text:
            logger.info('Fetched from %s', url)
            break

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if not playlist_text:
        logger.error('No playlist content found from portal')
        return

    entries = parse_m3u(playlist_text)
    manifest = classify_and_build(entries, {'languages': filters.get('languages', {})})

    # write JSON manifest
    json_path = outdir / 'manifest.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    # write M3U
    m3u_text = generate_m3u(manifest)
    m3u_path = outdir / 'playlist.m3u'
    with open(m3u_path, 'w', encoding='utf-8') as f:
        f.write(m3u_text)

    logger.info('Generated %s and %s', json_path, m3u_path)


if __name__ == '__main__':
    main()
