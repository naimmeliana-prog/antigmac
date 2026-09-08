"""
filters.py
----------
Sistema de filtros para contenidos IPTV.
Filtra por idioma y región geográfica según configuración en portals.json.

Reglas de filtrado:
  - TV Live: Español España | Francés Francia | Inglés UK
  - Películas: Español España | Francés Francia
  - Series: Español España
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# KEYWORDS POR DEFECTO (se complementan con las de portals.json)
# ═══════════════════════════════════════════════════════════════════════════════

# --- ESPAÑOL ESPAÑA -----------------------------------------------------------
ES_SPAIN_INCLUDE = [
    r"\bespañ", r"\bspain\b", r"\bespañol\b", r"\bes\b", r"\[es\]", r"\(es\)",
    r"tvE\b", r"antena\s*3", r"telecinco", r"cuatro\b", r"la\s*sexta",
    r"rtve", r"canal\s*sur", r"canal\s*9\b", r"\btv3\b", r"\betb\b",
    r"telemadrid", r"aragón\s*tv", r"tv\s*canaria", r"ib3\b", r"la\s*1\b",
    r"la\s*2\b", r"esport\s*3", r"canal\s*historia", r"paramount\s*channel\s*es",
    r"mega\b.*es", r"esmatv", r"tdtcat", r"à\s*punt", r"forta\b",
    r"canal\s*extremadura", r"canal\s*castilla", r"tv\s*galicia", r"tvg\b",
    r"eitb\b", r"canal\s*sur", r"trece\b", r"dmax\s*es", r"be\s*mad",
    r"neox\b", r"nova\b.*es", r"energia\b.*es", r"ten\b.*es", r"fdf\b",
    r"divinity\b", r"atreseries", r"cine\+", r"movistar\+", r"#0\b",
    r"disney\+\s*es", r"espanish", r"\[esp\]", r"\(esp\)",
    # Plataformas OTT / VOD / Series
    r"disney", r"netflix", r"hbo", r"amazon", r"prime", r"apple\s*tv", r"apple\+",
    r"movistar", r"hulu", r"dazn", r"paramount\+", r"skyshowtime", r"pluto",
    # Regiones España
    r"madrid", r"barcelona", r"andalucia", r"andalucía", r"cataluña",
    r"valencia", r"galicia", r"asturias", r"cantabria", r"murcia",
    r"navarra", r"rioja", r"aragon", r"aragón", r"castilla", r"canarias",
    r"baleares", r"extremadura", r"euskadi", r"euskal", r"basque",
]

ES_SPAIN_EXCLUDE = [
    r"\blatino\b", r"\blatin\b", r"\blatam\b", r"\blatinoamerica\b",
    r"\bmexico\b", r"\bmexicano\b", r"\bmex\b", r"\bargentina\b",
    r"\bcolombia\b", r"\bchile\b", r"\bvenezuela\b", r"\bperu\b",
    r"\becuador\b", r"\bbolivia\b", r"\bparaguay\b", r"\buruguay\b",
    r"\bcuba\b", r"\bdominicana\b", r"\bhonduras\b", r"\bguatemala\b",
    r"\bsalvador\b", r"\bnicaragua\b", r"\bcosta\s*rica\b", r"\bpanama\b",
    r"\bpuerto\s*rico\b", r"\brepublica\s*dominicana\b",
    r"\bsudamerica\b", r"\bsudamérica\b", r"\bcentroamerica\b",
    r"\bamericas?\b", r"\bvenezolan\b",
]

# --- FRANCÉS FRANCIA ----------------------------------------------------------
FR_FRANCE_INCLUDE = [
    r"\bfrance\b", r"\bfrançais\b", r"\bfrancais\b", r"\bfr\b",
    r"\[fr\]", r"\(fr\)",
    r"\btf1\b", r"\bfrance\s*2\b", r"\bfrance\s*3\b", r"\bfrance\s*4\b",
    r"\bfrance\s*5\b", r"\bfrance\s*info\b", r"\bfranceinfo\b",
    r"\bm6\b", r"\bcanal\s*\+\b", r"\bbfm\b", r"\barte\b.*fr",
    r"\blci\b", r"\bitele\b", r"\btmc\b", r"\btfx\b", r"\btf1\s*\+\b",
    r"\bgulli\b", r"\bc8\b", r"\bcnews\b", r"\bcstar\b", r"\bcherie\s*25\b",
    r"\bnumero\s*23\b", r"\w2\b", r"\bfrance\s*\d+\b", r"\brtbf\b.*fr",
    r"\beuronews.*fr\b", r"\bfr24\b", r"\bfrance\s*24\b",
    r"\bparis\b", r"\blyon\b", r"\bmarseille\b", r"\bstrasbourg\b",
    r"\bbordeaux\b", r"\btoulouse\b", r"\bnantes\b",
]

FR_FRANCE_EXCLUDE = [
    r"\bcanada\b", r"\bquébec\b", r"\bquebec\b", r"\bquébécois\b",
    r"\bbbelgique\b", r"\bbelgium\b", r"\bbelge\b", r"\brtbf\b",
    r"\bsuisse\b", r"\bswitzerland\b", r"\bgeneve\b", r"\bgenève\b",
    r"\bcaraïbes\b", r"\bcaraibes\b", r"\bcaribbean\b", r"\bantilles\b",
    r"\bafrique\b", r"\bafrica\b", r"\bmaghreb\b", r"\bmaroc\b",
    r"\balgerie\b", r"\balgérie\b", r"\btunisie\b", r"\bsénégal\b",
    r"\bsenegal\b", r"\bcôte\s*d.ivoire\b", r"\bcameroun\b",
    r"\bhaïti\b", r"\bhaiti\b", r"\bguadeloupe\b", r"\bmartinique\b",
    r"\bréunion\b", r"\breunion\b", r"\blouisian\b", r"\bmaurice\b",
    r"\bburundi\b", r"\brwanda\b", r"\bcongo\b", r"\bgabon\b",
]

# --- INGLÉS REINO UNIDO -------------------------------------------------------
EN_UK_INCLUDE = [
    r"\buk\b", r"\[uk\]", r"\(uk\)", r"\bunited\s*kingdom\b",
    r"\bbritain\b", r"\bbritish\b", r"\bengland\b", r"\benglish\b",
    r"\bscotland\b", r"\bscottish\b", r"\bwales\b", r"\bwelsh\b",
    r"\bbbc\b", r"\bitv\b", r"\bchannel\s*4\b", r"\bchannel\s*5\b",
    r"\bsky\b.*uk", r"\bbt\s*sport\b", r"\bdave\b.*uk", r"\bgold\b.*uk",
    r"\balibi\b.*uk", r"\byesterday\b.*uk", r"\breally\b.*uk",
    r"\bquest\b.*uk", r"\bmore4\b", r"\bfilm4\b", r"\be4\b",
    r"\b4seven\b", r"\bfreeview\b", r"\bvirgin\b.*uk",
    r"\blondon\b", r"\bmanchester\b", r"\bbirmingham\b", r"\bglasgow\b",
    r"\bedinburgh\b", r"\bliverpool\b", r"\bleeds\b", r"\bnewcastle\b",
    r"\bcardiff\b", r"\bbristol\b", r"\bsheffield\b",
]

EN_UK_EXCLUDE = [
    r"\busa\b", r"\bus\b", r"\[us\]", r"\(us\)", r"\bamerican\b",
    r"\bamerica\b", r"\bunited\s*states\b", r"\bcanada\b", r"\bcanadian\b",
    r"\baustralia\b", r"\baustralian\b", r"\bau\b", r"\bireland\b",
    r"\birish\b", r"\bsouth\s*africa\b", r"\bnew\s*zealand\b", r"\bnz\b",
    r"\bindia\b", r"\bindian\b", r"\bpakistan\b", r"\bbangladesh\b",
    r"\burdu\b", r"\bhindi\b", r"\barabic\b",
]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPILACIÓN DE PATRONES
# ═══════════════════════════════════════════════════════════════════════════════

def _compile_patterns(patterns: List[str]) -> List[re.Pattern]:
    """Compila una lista de patrones de texto a expresiones regulares."""
    compiled = []
    for p in patterns:
        try:
            compiled.append(re.compile(p, re.IGNORECASE | re.UNICODE))
        except re.error as e:
            logger.warning(f"Patrón regex inválido '{p}': {e}")
    return compiled


# Compilar una sola vez
_ES_INC = _compile_patterns(ES_SPAIN_INCLUDE)
_ES_EXC = _compile_patterns(ES_SPAIN_EXCLUDE)
_FR_INC = _compile_patterns(FR_FRANCE_INCLUDE)
_FR_EXC = _compile_patterns(FR_FRANCE_EXCLUDE)
_EN_INC = _compile_patterns(EN_UK_INCLUDE)
_EN_EXC = _compile_patterns(EN_UK_EXCLUDE)


# ═══════════════════════════════════════════════════════════════════════════════
# FUNCIONES DE DETECCIÓN DE IDIOMA/REGIÓN
# ═══════════════════════════════════════════════════════════════════════════════

def _matches_any(text: str, patterns: List[re.Pattern]) -> bool:
    """Devuelve True si el texto coincide con algún patrón."""
    return any(p.search(text) for p in patterns)


def _normalize(text: str) -> str:
    """Normaliza el texto para la búsqueda."""
    return (text or "").lower().strip()


def is_spain_spanish(category_name: str, channel_name: str = "") -> bool:
    """
    Determina si un canal/categoría es Español de España.
    Excluye contenido Latino.
    """
    text = _normalize(f"{category_name} {channel_name}")
    if not text:
        return False
    # Primero verificar exclusiones
    if _matches_any(text, _ES_EXC):
        return False
    # Luego verificar inclusiones
    return _matches_any(text, _ES_INC)


def is_france_french(category_name: str, channel_name: str = "") -> bool:
    """
    Determina si un canal/categoría es Francés de Francia.
    Excluye Canada, Bélgica, Suiza, África, Caribe.
    """
    text = _normalize(f"{category_name} {channel_name}")
    if not text:
        return False
    if _matches_any(text, _FR_EXC):
        return False
    return _matches_any(text, _FR_INC)


def is_uk_english(category_name: str, channel_name: str = "") -> bool:
    """
    Determina si un canal/categoría es Inglés del Reino Unido.
    Excluye USA, Canada, Australia, Irlanda, etc.
    """
    text = _normalize(f"{category_name} {channel_name}")
    if not text:
        return False
    if _matches_any(text, _EN_EXC):
        return False
    return _matches_any(text, _EN_INC)


# ═══════════════════════════════════════════════════════════════════════════════
# FILTROS POR TIPO DE CONTENIDO
# ═══════════════════════════════════════════════════════════════════════════════

def filter_live_category(category: Dict) -> Tuple[bool, str]:
    """
    Filtra una categoría de TV en Vivo.
    Returns: (aceptada, idioma)
    """
    name = category.get("title", category.get("name", ""))

    if is_spain_spanish(name):
        return True, "es_spain"
    if is_france_french(name):
        return True, "fr_france"
    if is_uk_english(name):
        return True, "en_uk"

    return False, ""


def filter_live_channel(channel: Dict) -> Tuple[bool, str]:
    """
    Filtra un canal de TV en Vivo usando nombre + nombre de categoría.
    Returns: (aceptado, idioma)
    """
    ch_name = channel.get("name", channel.get("title", ""))
    cat_name = channel.get("_category_name", channel.get("genre_title", ""))

    # Si la categoría ya pasó el filtro, aceptamos el canal automáticamente
    if channel.get("_lang"):
        return True, channel["_lang"]

    if is_spain_spanish(cat_name, ch_name):
        return True, "es_spain"
    if is_france_french(cat_name, ch_name):
        return True, "fr_france"
    if is_uk_english(cat_name, ch_name):
        return True, "en_uk"

    return False, ""


def filter_movie(movie: Dict) -> Tuple[bool, str]:
    """
    Filtra una película.
    Solo acepta Español España y Francés Francia.
    Returns: (aceptada, idioma)
    """
    name = movie.get("name", movie.get("title", ""))
    cat_name = movie.get("_category_name", "")

    if is_spain_spanish(cat_name, name):
        return True, "es_spain"
    if is_france_french(cat_name, name):
        return True, "fr_france"

    return False, ""


def filter_series(serie: Dict) -> Tuple[bool, str]:
    """
    Filtra una serie.
    Solo acepta Español España.
    Returns: (aceptada, idioma)
    """
    name = serie.get("name", serie.get("title", ""))
    cat_name = serie.get("_category_name", "")

    if is_spain_spanish(cat_name, name):
        return True, "es_spain"

    return False, ""


# ═══════════════════════════════════════════════════════════════════════════════
# APLICACIÓN DE FILTROS A LISTAS
# ═══════════════════════════════════════════════════════════════════════════════

class ContentFilter:
    """
    Gestor de filtros de contenido.
    Filtra categorías y streams por idioma/región.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Args:
            config: Configuración de filtros desde portals.json (opcional)
        """
        self.config = config or {}

    def filter_live_categories(self, categories: List[Dict]) -> List[Dict]:
        """Filtra categorías de TV en Vivo."""
        filtered = []
        for cat in categories:
            accepted, lang = filter_live_category(cat)
            if accepted:
                cat["_lang"] = lang
                filtered.append(cat)

        logger.info(f"Categorías Live: {len(categories)} total → {len(filtered)} aceptadas")
        return filtered

    def filter_live_channels(self, channels: List[Dict], filtered_categories: List[Dict]) -> List[Dict]:
        """Filtra canales de TV en Vivo."""
        accepted_cat_ids = {str(c.get("id", "")) for c in filtered_categories}
        accepted_cat_langs = {str(c.get("id", "")): c.get("_lang", "") for c in filtered_categories}

        filtered = []
        for ch in channels:
            cat_id = str(ch.get("_category_id", ch.get("genre", "")))

            # Si la categoría del canal está aceptada
            if cat_id in accepted_cat_ids:
                ch["_lang"] = accepted_cat_langs.get(cat_id, "")
                filtered.append(ch)
                continue

            # Filtrar por nombre del canal
            accepted, lang = filter_live_channel(ch)
            if accepted:
                ch["_lang"] = lang
                filtered.append(ch)

        logger.info(f"Canales Live: {len(channels)} total → {len(filtered)} aceptados")
        return filtered

    def filter_vod_categories(self, categories: List[Dict]) -> List[Dict]:
        """Filtra categorías de Películas."""
        filtered = []
        for cat in categories:
            name = cat.get("title", cat.get("name", ""))
            if is_spain_spanish(name):
                cat["_lang"] = "es_spain"
                filtered.append(cat)
            elif is_france_french(name):
                cat["_lang"] = "fr_france"
                filtered.append(cat)

        logger.info(f"Categorías VOD: {len(categories)} total → {len(filtered)} aceptadas")
        return filtered

    def filter_movies(self, movies: List[Dict], filtered_categories: List[Dict]) -> List[Dict]:
        """Filtra películas."""
        accepted_cat_ids = {str(c.get("id", "")) for c in filtered_categories}
        accepted_cat_langs = {str(c.get("id", "")): c.get("_lang", "") for c in filtered_categories}

        filtered = []
        for movie in movies:
            cat_id = str(movie.get("_category_id", ""))

            if cat_id in accepted_cat_ids:
                movie["_lang"] = accepted_cat_langs.get(cat_id, "")
                filtered.append(movie)
                continue

            accepted, lang = filter_movie(movie)
            if accepted:
                movie["_lang"] = lang
                filtered.append(movie)

        logger.info(f"Películas: {len(movies)} total → {len(filtered)} aceptadas")
        return filtered

    def filter_series_categories(self, categories: List[Dict]) -> List[Dict]:
        """Filtra categorías de Series (Español España y plataformas, excluyendo Latino/otras regiones)."""
        filtered = []
        for cat in categories:
            name = cat.get("title", cat.get("name", ""))
            norm = _normalize(name)

            # Excluir explícitamente contenido Latino / otras regiones
            if _matches_any(norm, _ES_EXC) and not _matches_any(norm, _ES_INC):
                continue

            # Aceptar si coincide con España/plataformas o si la categoría no es de otra región
            if is_spain_spanish(name) or _matches_any(norm, _ES_INC):
                cat["_lang"] = "es_spain"
                filtered.append(cat)

        logger.info(f"Categorías Series: {len(categories)} total → {len(filtered)} aceptadas")
        return filtered

    def filter_series_list(self, series_list: List[Dict], filtered_categories: List[Dict]) -> List[Dict]:
        """Filtra series descartando las que contengan etiquetas latinas/excluidas."""
        accepted_cat_ids = {str(c.get("id", "")) for c in filtered_categories}

        filtered = []
        for serie in series_list:
            name = serie.get("name", serie.get("title", ""))
            norm = _normalize(name)
            cat_id = str(serie.get("_category_id", ""))

            # Si el título individual de la serie indica que es Latina, la descartamos
            if _matches_any(norm, _ES_EXC) and not _matches_any(norm, _ES_INC):
                continue

            if cat_id in accepted_cat_ids:
                serie["_lang"] = "es_spain"
                filtered.append(serie)
            elif is_spain_spanish("", name):
                serie["_lang"] = "es_spain"
                filtered.append(serie)

        logger.info(f"Series: {len(series_list)} total → {len(filtered)} aceptadas")
        return filtered
