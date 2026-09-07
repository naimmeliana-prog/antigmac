addEventListener('fetch', event => {
  event.respondWith(handle(event.request))
})

const OWNER = 'naimmeliana-prog'
const REPO = 'antigmac'
const BRANCH = 'generated-playlists'

async function handle(request) {
  const url = new URL(request.url)
  // expected path: /xtream/playlist.m3u or /xtream/manifest.json
  const parts = url.pathname.split('/').filter(Boolean)
  if (parts.length === 0) return new Response('OK from worker')
  const filename = parts.slice(-1)[0]
  const rawUrl = `https://raw.githubusercontent.com/${OWNER}/${REPO}/${BRANCH}/generated/${filename}`
  const resp = await fetch(rawUrl)
  if (!resp.ok) return new Response('Not found', {status: 404})
  const headers = new Headers(resp.headers)
  // set proper content type for m3u
  if (filename.endsWith('.m3u')) headers.set('Content-Type', 'audio/mpegurl')
  return new Response(resp.body, {status: 200, headers})
}
