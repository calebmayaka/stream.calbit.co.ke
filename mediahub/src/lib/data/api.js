// ---------------------------------------------------------------------------
// DATA LAYER — the one place the UI talks to for content.
//
// Reads the Django API (backend/). In dev, Vite proxies /api to the Django dev
// server; in production IIS does. The API returns { hero, rows:[{title, items}] }.
//
// Django leaves `poster` / `backdrop` null when it has no image (mock mode, or
// a Jellyfin item without artwork); those get the offline gradient placeholder.
// ---------------------------------------------------------------------------

import { poster, backdrop } from './placeholder.js';

/** Session expired / signed out elsewhere: back to the login page. */
function toLogin() {
  const here = location.pathname + location.search;
  if (!location.pathname.startsWith('/login')) location.assign(`/login?next=${encodeURIComponent(here)}`);
}

async function getJSON(path) {
  const res = await fetch(path, { headers: { Accept: 'application/json' } });
  if (res.status === 401) toLogin();
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

/** Django's CSRF token, set as a cookie by /api/auth/me. */
function csrfToken() {
  return document.cookie.match(/(?:^|;\s*)mediahub_csrf=([^;]+)/)?.[1] ?? '';
}

async function postJSON(path, body, { keepalive = false } = {}) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRFToken': csrfToken() },
    body: JSON.stringify(body),
    keepalive // lets the final progress report survive tab close
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401 && !path.startsWith('/api/auth/')) toLogin();
  if (!res.ok) throw new Error(data.error || `${path} failed: ${res.status}`);
  return data;
}

// --- Account -----------------------------------------------------------------

/** @returns {Promise<{ authenticated: boolean, setup?: boolean, user?: { username: string, name: string } }>} */
// Signed-in state is checked once per visit, not on every click (each check is
// a ~0.4 s round trip through the VPS). Anything that changes it forgets the
// cached answer; an expired session is caught by the API's 401 (toLogin).
let me = null;

export async function getMe({ fresh = false } = {}) {
  if (me && !fresh) return me;
  const res = await fetch('/api/auth/me', { headers: { Accept: 'application/json' } });
  if (!res.ok) throw new Error(`Couldn’t reach MediaHub (${res.status})`);
  const data = await res.json();
  me = data.authenticated ? data : null; // only remember signed-in answers
  return data;
}

export function signIn(username, password) {
  me = null;
  return postJSON('/api/auth/login', { username, password });
}

/** First-run only (no accounts yet): create the first login with the server's setup code. */
export function setupFirstAccount({ code, username, name, password }) {
  me = null;
  return postJSON('/api/auth/setup', { code, username, name, password });
}

/** "Forgot password?": account name + the server's reset pass key + new password. Signs in on success. */
export function resetPassword({ username, key, password }) {
  me = null;
  return postJSON('/api/auth/reset', { username, key, password });
}

export function signOut() {
  me = null;
  return postJSON('/api/auth/logout', {});
}

const id = (value) => encodeURIComponent(value);
const withPoster = (item) => ({ ...item, poster: item.poster ?? poster(item.title, item.kind) });
const withPosters = (items = []) => items.map(withPoster);

export async function getHome() {
  const data = await getJSON('/api/home');
  const heroes = (data.heroes ?? (data.hero ? [data.hero] : [])).map((h) => ({
    ...h,
    backdrop: h.backdrop ?? backdrop(h.title)
  }));
  const rows = data.rows.map((row) => ({ ...row, items: withPosters(row.items) }));
  return { heroes, rows };
}

/** Detail page: movie, series (with seasons), episode or collection. */
export async function getTitle(itemId) {
  const data = await getJSON(`/api/title/${id(itemId)}`);
  return {
    ...data,
    poster: data.poster ?? poster(data.title, data.kind),
    backdrop: data.backdrop ?? backdrop(data.title),
    similar: withPosters(data.similar),
    items: withPosters(data.items)
  };
}

export async function getPerson(personId) {
  const data = await getJSON(`/api/person/${id(personId)}`);
  return { ...data, items: withPosters(data.items) };
}

/**
 * Paged library listing.
 * @param {{ type: 'movies'|'series'|'collections'|'mylist', sort?: string, genre?: string, start?: number, limit?: number }} q
 * @returns {Promise<{ items: any[], total: number, next: number }>}
 */
export async function browse({ type, sort = 'added', genre = '', start = 0, limit = 48 }) {
  const params = new URLSearchParams({ type, sort, start: String(start), limit: String(limit) });
  if (genre) params.set('genre', genre);
  const data = await getJSON(`/api/browse?${params}`);
  return { ...data, items: withPosters(data.items) };
}

export function getGenres(type) {
  return getJSON(`/api/genres?type=${id(type)}`).then((d) => d.genres);
}

/** @returns {Promise<{ results: any[], people: any[] }>} titles and people, separately */
export async function search(term, { signal } = {}) {
  const res = await fetch(`/api/search?q=${id(term)}`, { headers: { Accept: 'application/json' }, signal });
  if (res.status === 401) toLogin();
  if (!res.ok) throw new Error(`search failed: ${res.status}`);
  const data = await res.json();
  return { results: withPosters(data.results), people: data.people ?? [] };
}

export function setPlayed(itemId, played) {
  return postJSON(`/api/played/${id(itemId)}`, { played });
}

export function setFavorite(itemId, favorite) {
  return postJSON(`/api/favorite/${id(itemId)}`, { favorite });
}

/**
 * Ask Django for a stream:
 * { url, type: 'hls'|'file', startSeconds, duration, playSessionId,
 *   audioTracks[], audioIndex, subtitles[], next, segments }
 */
export function startPlayback(itemId, startSeconds = 0, audioIndex = null, { caps = {}, quality = 'auto' } = {}) {
  return postJSON(`/api/play/${id(itemId)}`, { startSeconds, audioIndex, caps, quality });
}

/** One watch's startup time / buffering / delivery method (see manage.py playbackstats). */
export function reportPlaybackStats(itemId, stats) {
  return postJSON(`/api/playstats/${id(itemId)}`, stats, { keepalive: true }).catch(() => {});
}

export function saveProgress(itemId, positionSeconds, durationSeconds, opts) {
  return postJSON(`/api/progress/${id(itemId)}`, { positionSeconds, durationSeconds }, opts);
}

export function stopPlayback(playSessionId) {
  return postJSON('/api/stop', { playSessionId }, { keepalive: true }).catch(() => {});
}
