/**
 * MacToXtream — Cloudflare Worker
 * ================================
 * Implementa la API Xtream Codes completa leyendo datos desde GitHub.
 * Sirve como puente entre TiviPlayer (WebOS) y los datos IPTV generados
 * por el extractor Python.
 *
 * Endpoints implementados:
 *   GET /player_api.php?username=X&password=X&action=get_live_categories
 *   GET /player_api.php?username=X&password=X&action=get_live_streams
 *   GET /player_api.php?username=X&password=X&action=get_vod_categories
 *   GET /player_api.php?username=X&password=X&action=get_vod_streams
 *   GET /player_api.php?username=X&password=X&action=get_series_categories
 *   GET /player_api.php?username=X&password=X&action=get_series
 *   GET /player_api.php?username=X&password=X&action=get_series_info&series_id=X
 *   GET /live/{user}/{pass}/{stream_id}.{ext}   → Redirect al stream original
 *   GET /movie/{user}/{pass}/{stream_id}.{ext}  → Redirect al stream original
 *   GET /series/{user}/{pass}/{ep_id}.{ext}     → Redirect al stream original
 *   GET /get.php?username=X&password=X&type=m3u_plus → Exportar M3U
 */

// ─────────────────────────────────────────────────────────────────────────────
// CONFIGURACIÓN
// ─────────────────────────────────────────────────────────────────────────────

// URL base del repositorio GitHub (raw content)
// Ajusta a tu usuario y nombre de repo
const GITHUB_RAW_BASE =
  "https://raw.githubusercontent.com/naimmeliana-prog/antigmac/main/data";

// Cache TTL en segundos (1 hora)
const CACHE_TTL = 3600;

// Headers CORS para TiviPlayer
const CORS_HEADERS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type, Authorization",
};

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Fetch con cache usando la Cache API de Cloudflare.
 * Evita hits innecesarios a GitHub raw.
 */
async function fetchWithCache(url, ttl = CACHE_TTL) {
  const cache = caches.default;
  const cacheKey = new Request(url);

  // Intentar desde cache
  let response = await cache.match(cacheKey);
  if (response) return response;

  // Fetch desde origen
  response = await fetch(url, {
    headers: { "User-Agent": "MacToXtream-Worker/1.0" },
    cf: { cacheTtl: ttl, cacheEverything: true },
  });

  if (!response.ok) {
    throw new Error(`GitHub fetch failed: ${response.status} ${url}`);
  }

  // Guardar en cache con TTL
  const cachedResponse = new Response(response.body, response);
  cachedResponse.headers.set("Cache-Control", `public, max-age=${ttl}`);
  await cache.put(cacheKey, cachedResponse.clone());

  return cachedResponse;
}

/**
 * Carga un JSON desde GitHub con cache.
 */
async function loadJson(filename) {
  const url = `${GITHUB_RAW_BASE}/${filename}`;
  const response = await fetchWithCache(url);
  return response.json();
}

/**
 * Respuesta JSON estándar.
 */
function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...CORS_HEADERS,
    },
  });
}

/**
 * Respuesta de error.
 */
function errorResponse(message, status = 400) {
  return new Response(JSON.stringify({ error: message }), {
    status,
    headers: {
      "Content-Type": "application/json",
      ...CORS_HEADERS,
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// AUTENTICACIÓN
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Verifica si las credenciales son válidas.
 * Lee los usuarios desde data/users.json en GitHub.
 */
async function verifyCredentials(username, password) {
  if (!username || !password) return null;

  try {
    const users = await loadJson("users.json");
    return users.find(
      (u) => u.username === username && u.password === password
    ) || null;
  } catch {
    return null;
  }
}

/**
 * Construye el objeto user_info para la respuesta de autenticación.
 */
function buildUserInfo(user, workerUrl) {
  const now = Math.floor(Date.now() / 1000);
  return {
    user_info: {
      username: user.username,
      password: user.password,
      message: user.message || "MacToXtream",
      auth: 1,
      status: "Active",
      exp_date: user.exp_date || "9999999999",
      is_trial: "0",
      active_cons: "0",
      created_at: String(now),
      max_connections: user.max_connections || "3",
      allowed_output_formats: ["ts", "m3u8", "rtmp"],
    },
    server_info: {
      url: workerUrl,
      port: "80",
      https_port: "443",
      server_protocol: "https",
      rtmp_port: "1935",
      timezone: "Europe/Madrid",
      timestamp_now: now,
      time_now: new Date().toISOString().replace("T", " ").substring(0, 19),
    },
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// LOOKUP DE STREAMS (para proxy/redirect)
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Busca un stream por ID en una lista y devuelve su _stalker_cmd.
 */
async function findStreamById(listFile, streamId) {
  const streams = await loadJson(listFile);
  const id = parseInt(streamId);
  return streams.find(
    (s) => s.stream_id === id || s.series_id === id
  );
}

/**
 * Obtiene la URL real de un stream Stalker desde su cmd.
 * En modo redirect, simplemente devuelve el cmd o construye la URL.
 */
function buildStreamUrl(stalkerCmd, portalUrl) {
  if (!stalkerCmd) return null;

  // El cmd puede ser una URL completa o un path relativo
  if (stalkerCmd.startsWith("http")) return stalkerCmd;

  // Intentar construir URL desde el portal
  const cmd = stalkerCmd.startsWith("/") ? stalkerCmd : `/${stalkerCmd}`;
  return `${portalUrl}${cmd}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// GENERADOR M3U
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Genera una playlist M3U Plus completa.
 */
async function generateM3U(username, password, workerUrl, type = "all") {
  const lines = [`#EXTM3U url-tvg="" refresh="600"`];

  const base = `${workerUrl}`;

  // Live channels
  if (type === "all" || type === "live") {
    const [liveCats, liveStreams] = await Promise.all([
      loadJson("live_categories.json"),
      loadJson("live_streams.json"),
    ]);

    const catMap = {};
    liveCats.forEach((c) => (catMap[c.category_id] = c.category_name));

    for (const ch of liveStreams) {
      const catName = catMap[ch.category_id] || "Live TV";
      lines.push(
        `#EXTINF:-1 tvg-id="${ch.epg_channel_id || ""}" tvg-name="${ch.name}" tvg-logo="${ch.stream_icon || ""}" group-title="${catName}",${ch.name}`
      );
      lines.push(
        `${base}/live/${username}/${password}/${ch.stream_id}.ts`
      );
    }
  }

  // VOD
  if (type === "all" || type === "movie") {
    const [vodCats, vodStreams] = await Promise.all([
      loadJson("vod_categories.json"),
      loadJson("vod_streams.json"),
    ]);

    const catMap = {};
    vodCats.forEach((c) => (catMap[c.category_id] = c.category_name));

    for (const movie of vodStreams) {
      const catName = catMap[movie.category_id] || "Películas";
      const ext = movie.container_extension || "mkv";
      lines.push(
        `#EXTINF:-1 tvg-name="${movie.name}" tvg-logo="${movie.stream_icon || ""}" group-title="${catName}",${movie.name}`
      );
      lines.push(
        `${base}/movie/${username}/${password}/${movie.stream_id}.${ext}`
      );
    }
  }

  return lines.join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
// MANEJADOR PRINCIPAL
// ─────────────────────────────────────────────────────────────────────────────

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const workerUrl = `${url.protocol}//${url.host}`;

    // CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    try {
      // ── player_api.php ────────────────────────────────────────────────────
      if (url.pathname === "/player_api.php" || url.pathname === "/api/player_api.php") {
        return handlePlayerApi(request, url, workerUrl, env);
      }

      // ── get.php (M3U export) ──────────────────────────────────────────────
      if (url.pathname === "/get.php") {
        return handleGetPhp(request, url, workerUrl, env);
      }

      // ── Stream proxy/redirect: /live/{user}/{pass}/{id}.ext ───────────────
      const liveMatch = url.pathname.match(
        /^\/live\/([^/]+)\/([^/]+)\/(\d+)\.(\w+)$/
      );
      if (liveMatch) {
        return handleLiveStream(liveMatch, env);
      }

      // ── Movie proxy/redirect: /movie/{user}/{pass}/{id}.ext ───────────────
      const movieMatch = url.pathname.match(
        /^\/movie\/([^/]+)\/([^/]+)\/(\d+)\.(\w+)$/
      );
      if (movieMatch) {
        return handleMovieStream(movieMatch, env);
      }

      // ── Series episode: /series/{user}/{pass}/{id}.ext ───────────────────
      const seriesMatch = url.pathname.match(
        /^\/series\/([^/]+)\/([^/]+)\/(\d+)\.(\w+)$/
      );
      if (seriesMatch) {
        return handleSeriesStream(seriesMatch, env);
      }

      // ── Raíz: info básica ─────────────────────────────────────────────────
      if (url.pathname === "/" || url.pathname === "") {
        return new Response(
          JSON.stringify({
            status: "MacToXtream Worker Online",
            version: "1.0",
            endpoints: ["/player_api.php", "/get.php", "/live/", "/movie/", "/series/"],
          }),
          { headers: { "Content-Type": "application/json", ...CORS_HEADERS } }
        );
      }

      return errorResponse("Endpoint no encontrado", 404);

    } catch (error) {
      console.error("Worker error:", error);
      return errorResponse(`Error interno: ${error.message}`, 500);
    }
  },
};

// ─────────────────────────────────────────────────────────────────────────────
// MANEJADORES DE ENDPOINTS
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Maneja todos los endpoints de /player_api.php
 */
async function handlePlayerApi(request, url, workerUrl, env) {
  const params = url.searchParams;
  const username = params.get("username") || "";
  const password = params.get("password") || "";
  const action = params.get("action") || "";

  // Verificar credenciales
  const user = await verifyCredentials(username, password);

  // Si no hay action, devolver server info (autenticación)
  if (!action) {
    if (!user) {
      return jsonResponse({
        user_info: { auth: 0 },
        server_info: {},
      });
    }
    return jsonResponse(buildUserInfo(user, workerUrl));
  }

  // Para todas las demás acciones, requerir autenticación
  if (!user) {
    return jsonResponse({ error: "Credenciales inválidas", auth: 0 }, 401);
  }

  // ── Dispatch por acción ───────────────────────────────────────────────────
  switch (action) {
    // ── LIVE TV ──────────────────────────────────────────────────────────────
    case "get_live_categories": {
      const data = await loadJson("live_categories.json");
      return jsonResponse(data);
    }

    case "get_live_streams": {
      const categoryId = params.get("category_id");
      let data = await loadJson("live_streams.json");
      if (categoryId) {
        data = data.filter((s) => s.category_id === categoryId);
      }
      // Limpiar campos internos antes de devolver
      return jsonResponse(data.map(cleanStreamFields));
    }

    // ── VOD ───────────────────────────────────────────────────────────────────
    case "get_vod_categories": {
      const data = await loadJson("vod_categories.json");
      return jsonResponse(data);
    }

    case "get_vod_streams": {
      const categoryId = params.get("category_id");
      let data = await loadJson("vod_streams.json");
      if (categoryId) {
        data = data.filter((s) => s.category_id === categoryId);
      }
      return jsonResponse(data.map(cleanStreamFields));
    }

    case "get_vod_info": {
      const vodId = params.get("vod_id");
      if (!vodId) return errorResponse("vod_id requerido");
      const streams = await loadJson("vod_streams.json");
      const movie = streams.find((s) => String(s.stream_id) === String(vodId));
      if (!movie) return errorResponse("Película no encontrada", 404);
      return jsonResponse({
        info: {
          tmdb_id: "",
          name: movie.name,
          o_name: movie.name,
          cover_big: movie.stream_icon,
          movie_image: movie.stream_icon,
          releasedate: movie.releaseDate || "",
          episode_run_time: "0",
          youtube_trailer: "",
          director: movie.director || "",
          actors: movie.cast || "",
          cast: movie.cast || "",
          description: movie.plot || "",
          plot: movie.plot || "",
          age: "",
          mpaa_rating: "",
          rating_count_kinopoisk: 0,
          kinopoisk_url: "",
          imdb_id: "",
          country: "",
          genre: movie.genre || "",
          backdrop_path: [],
          duration_secs: 0,
          duration: "00:00:00",
          video: {},
          audio: {},
          bitrate: 0,
          rating: movie.rating || "0",
          status: "Active",
        },
        movie_data: cleanStreamFields(movie),
      });
    }

    // ── SERIES ────────────────────────────────────────────────────────────────
    case "get_series_categories": {
      const data = await loadJson("series_categories.json");
      return jsonResponse(data);
    }

    case "get_series": {
      const categoryId = params.get("category_id");
      let data = await loadJson("series.json");
      if (categoryId) {
        data = data.filter((s) => s.category_id === categoryId);
      }
      return jsonResponse(data.map(cleanStreamFields));
    }

    case "get_series_info": {
      const seriesId = params.get("series_id");
      if (!seriesId) return errorResponse("series_id requerido");

      try {
        const data = await loadJson(`series_info/${seriesId}.json`);
        return jsonResponse(data);
      } catch {
        return errorResponse("Serie no encontrada", 404);
      }
    }

    // ── EPG (básico) ──────────────────────────────────────────────────────────
    case "get_short_epg": {
      // EPG no implementado - devolver estructura vacía
      return jsonResponse({ epg_listings: [] });
    }

    case "get_simple_data_table": {
      return jsonResponse({
        epg_listings: [],
        available_channels: [],
      });
    }

    default:
      return errorResponse(`Acción desconocida: ${action}`, 400);
  }
}

/**
 * Maneja el endpoint /get.php (exportar M3U)
 */
async function handleGetPhp(request, url, workerUrl, env) {
  const params = url.searchParams;
  const username = params.get("username") || "";
  const password = params.get("password") || "";
  const type = params.get("type") || "m3u_plus";
  const output = params.get("output") || "ts";

  const user = await verifyCredentials(username, password);
  if (!user) {
    return new Response("Credenciales inválidas", { status: 401 });
  }

  if (type === "m3u" || type === "m3u_plus") {
    const m3u = await generateM3U(username, password, workerUrl);
    return new Response(m3u, {
      headers: {
        "Content-Type": "application/x-mpegURL; charset=utf-8",
        "Content-Disposition": 'attachment; filename="mactoxtream.m3u"',
        ...CORS_HEADERS,
      },
    });
  }

  return errorResponse(`Tipo de output no soportado: ${type}`);
}

/**
 * Maneja streams de Live TV → Redirect 302 al stream del portal
 */
async function handleLiveStream([, username, password, streamId, ext], env) {
  try {
    const streams = await loadJson("live_streams.json");
    const id = parseInt(streamId);
    const stream = streams.find((s) => s.stream_id === id);

    if (!stream || !stream._stalker_cmd) {
      return new Response("Stream no encontrado", { status: 404 });
    }

    // Construir URL del stream Stalker
    const stalkerUrl = resolveStreamUrl(stream._stalker_cmd, env);
    if (!stalkerUrl) {
      return new Response("URL de stream no disponible", { status: 503 });
    }

    // Redirect 302 al stream original
    return Response.redirect(stalkerUrl, 302);
  } catch (e) {
    return new Response(`Error: ${e.message}`, { status: 500 });
  }
}

/**
 * Maneja streams de Películas → Redirect 302
 */
async function handleMovieStream([, username, password, streamId, ext], env) {
  try {
    const streams = await loadJson("vod_streams.json");
    const id = parseInt(streamId);
    const stream = streams.find((s) => s.stream_id === id);

    if (!stream || !stream._stalker_cmd) {
      return new Response("Película no encontrada", { status: 404 });
    }

    const stalkerUrl = resolveStreamUrl(stream._stalker_cmd, env);
    if (!stalkerUrl) {
      return new Response("URL de stream no disponible", { status: 503 });
    }

    return Response.redirect(stalkerUrl, 302);
  } catch (e) {
    return new Response(`Error: ${e.message}`, { status: 500 });
  }
}

/**
 * Maneja streams de Series → Redirect 302
 */
async function handleSeriesStream([, username, password, episodeId, ext], env) {
  try {
    // Buscar en todos los archivos de series_info
    // Por simplicidad, el episodeId es el ID del episodio

    // Nota: Para una implementación completa se necesitaría un índice de episodios
    // Por ahora devolvemos un redirect genérico
    return new Response(
      "Para acceder a episodios, usa el endpoint get_series_info y construye la URL desde el episode data",
      { status: 501 }
    );
  } catch (e) {
    return new Response(`Error: ${e.message}`, { status: 500 });
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// UTILIDADES
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Resuelve la URL real de un stream desde su cmd Stalker.
 * Si el env tiene PORTAL_URL configurado, lo usa como base.
 */
function resolveStreamUrl(stalkerCmd, env) {
  if (!stalkerCmd) return null;

  // Si ya es una URL completa
  if (stalkerCmd.startsWith("http://") || stalkerCmd.startsWith("https://")) {
    return stalkerCmd;
  }

  // Intentar con el portal URL del env
  const portalUrl = env?.PORTAL_URL || "http://mag.greatott.me:80";
  const path = stalkerCmd.startsWith("/") ? stalkerCmd : `/${stalkerCmd}`;
  return `${portalUrl}${path}`;
}

/**
 * Limpia campos internos (prefijados con _) de un objeto stream
 * antes de devolverlo al cliente.
 */
function cleanStreamFields(stream) {
  const cleaned = {};
  for (const [key, value] of Object.entries(stream)) {
    if (!key.startsWith("_")) {
      cleaned[key] = value;
    }
  }
  return cleaned;
}
