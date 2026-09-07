import re
import logging
from typing import List, Dict, Optional
from urllib.parse import urljoin

import requests

logger = logging.getLogger(__name__)


def fetch_url(url: str, params: dict = None, headers: dict = None, timeout: int = 15) -> Optional[str]:
    try:
        r = requests.get(url, params=params, headers=headers, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:
        logger.debug("fetch_url failed %s %s", url, e)
        return None


def parse_m3u(text: str) -> List[Dict]:
    # Very small M3U parser: yields entries with metadata and url
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    entries = []
    cur_meta = None
    for line in lines:
        if line.startswith('#EXTINF'):
            cur_meta = {'meta': line}
        elif line.startswith('#'):
            continue
        else:
            if cur_meta is None:
                # No meta, create basic
                entries.append({'title': line, 'url': line, 'meta': ''})
            else:
                cur_meta['url'] = line
                # try extract title after comma
                m = re.search(r'#EXTINF:[^-]*,(.*)$', cur_meta['meta'])
                cur_meta['title'] = m.group(1).strip() if m else ''
                entries.append(cur_meta)
                cur_meta = None
    return entries


def detect_series_episode(title: str) -> Optional[Dict]:
    # Detect SxxExx patterns and common season/ep markers like 1x02 or Season 1 Episode 2
    patterns = [r'[sS](\d{1,2})[eE](\d{1,2})', r'(\d{1,2})[xX](\d{1,2})', r'Season\s*(\d{1,2}).*Episode\s*(\d{1,2})']
    for pat in patterns:
        m = re.search(pat, title)
        if m:
            try:
                return {'season': int(m.group(1)), 'episode': int(m.group(2))}
            except Exception:
                continue
    return None


def try_endpoints(portal_url: str, mac: str) -> Dict[str, str]:
    # Try common endpoints to obtain playlist or API
    tests = [
        ("player_api", f"{portal_url.rstrip('/')}/player_api.php"),
        ("playlist", f"{portal_url.rstrip('/')}/playlist.php"),
        ("m3u", f"{portal_url.rstrip('/')}/get.php"),
        ("portal", f"{portal_url.rstrip('/')}/c/{mac}/"),
    ]
    found = {}
    for name, url in tests:
        text = fetch_url(url, params={'mac': mac} if '?' not in url else None)
        if text:
            found[name] = url
    return found


def filter_by_language_and_country(entry: Dict, desired: Dict) -> bool:
    """
    Determine if an entry matches desired languages/countries.
    `desired` is expected to be a dict with language keys (e.g. 'es_es','fr_fr','en_gb')
    or custom token lists under `desired['tokens']`.

    Heuristics used (in order):
    - explicit metadata tokens (tvg-language, tvg-country) in `meta` text
    - group-title or category tokens inside `meta`
    - language/country words inside title/meta
    - stream URL domain hints (e.g., .es)

    Rules are permissive if the user sets an `allow_all` flag in desired.
    """
    title = (entry.get('title') or '')
    meta = (entry.get('meta') or '')
    url = (entry.get('url') or '')
    combined = (title + ' ' + meta + ' ' + url).lower()

    # Allow-all shortcut
    if desired.get('allow_all'):
        return True

    # Custom token lists provided by the user
    tokens_cfg = desired.get('tokens', {})

    def contains_any(text, token_list):
        for t in token_list:
            if t and t.lower() in text:
                return True
        return False

    # Check explicit tvg-language or tvg-country markers in meta
    if 'tvg-language' in meta.lower() or 'tvg-country' in meta.lower():
        # If meta contains an explicit marker, try to match desired languages
        for lang_key in ['es_es', 'fr_fr', 'en_gb']:
            if desired.get(lang_key):
                tokens = tokens_cfg.get(lang_key) or default_language_tokens(lang_key)
                if contains_any(meta, tokens + [lang_key.replace('_', '-')]):
                    return True

    # Check URL domain hints
    if url:
        if desired.get('es_es') and (url.endswith('.es') or '.es/' in url):
            return True
        if desired.get('fr_fr') and (url.endswith('.fr') or '.fr/' in url):
            return True
        if desired.get('en_gb') and ('.uk/' in url or url.endswith('.uk')):
            return True

    # Check tokens and heuristics in title/meta
    for lang_key in ['es_es', 'fr_fr', 'en_gb']:
        if not desired.get(lang_key):
            continue
        tokens = tokens_cfg.get(lang_key) or default_language_tokens(lang_key)
        exclude = tokens_cfg.get(f'{lang_key}_exclude', [])
        if contains_any(combined, tokens) and not contains_any(combined, exclude):
            return True

    return False


def default_language_tokens(lang_key: str):
    if lang_key == 'es_es':
        return ['espa', 'espana', 'spain', 'es', 'castellano', 'español', 'espanol', 'esp']
    if lang_key == 'fr_fr':
        return ['france', 'franc', 'français', 'francais', 'fr', 'france']
    if lang_key == 'en_gb':
        return ['uk', 'united kingdom', 'england', 'britain', 'gb', 'uk']
    return []


def classify_and_build(entries: List[Dict], filters: Dict) -> Dict:
    result = {'live': [], 'movies': [], 'series': []}
    for e in entries:
        title = e.get('title', '')
        url = e.get('url')
        meta = e.get('meta', '')
        if not url:
            continue

        t = title.lower()
        # More robust classification using metadata tokens and common language markers
        if any(k in t for k in ['movie', 'pelicula', 'películas', 'pelicula', 'film', 'película']):
            cat = 'movies'
        elif any(k in t for k in ['serie', 'season', 'episode', 'episodio', 'temporada', 's0', 's1']):
            cat = 'series'
        else:
            # also check meta for group-title or category hints
            m = (meta or '').lower()
            if 'movie' in m or 'film' in m or 'pelicula' in m:
                cat = 'movies'
            elif 'series' in m or 'serie' in m or 'episodio' in m:
                cat = 'series'
            else:
                cat = 'live'

        if filters and not filter_by_language_and_country(e, filters.get('languages', {})):
            continue

        if cat == 'series':
            se = detect_series_episode(title + ' ' + meta)
            result['series'].append({'title': title, 'url': url, 'meta': meta, 'se': se})
        else:
            result[cat].append({'title': title, 'url': url, 'meta': meta})

    # Optional: group series by title and season/episode if detected
    grouped_series = {}
    for item in result['series']:
        base_title = re.sub(r'[\s\-_:,\|]+S?\d{1,2}E?\d{0,2}.*$', '', item['title'], flags=re.IGNORECASE).strip()
        key = base_title or item['title']
        grouped_series.setdefault(key, []).append(item)

    result['series_grouped'] = grouped_series
    return result


def generate_m3u(manifest: Dict) -> str:
    lines = ['#EXTM3U']
    # Live
    for ch in manifest.get('live', []):
        lines.append(f'#EXTINF:-1,group-title="Live", {ch["title"]}')
        lines.append(ch['url'])
    # Movies
    for mv in manifest.get('movies', []):
        lines.append(f'#EXTINF:-1,group-title="Movies", {mv["title"]}')
        lines.append(mv['url'])
    # Series: list episodes
    for s in manifest.get('series', []):
        title = s['title']
        lines.append(f'#EXTINF:-1,group-title="Series", {title}')
        lines.append(s['url'])
    return '\n'.join(lines) + '\n'
