// Client-rendered SPA: no Node server in production, IIS serves the static build.
import { redirect } from '@sveltejs/kit';
import { getMe } from '$lib/data/api.js';

export const ssr = false;
export const prerender = false;

/** Only the next= targets we'd navigate to ourselves (no //evil.example). */
function safeNext(value) {
  return value && value.startsWith('/') && !value.startsWith('//') && !value.startsWith('/login') ? value : '/';
}

// Login gate: every page needs a session except /login. (The API enforces the
// same thing server-side; this just sends people to the form instead of
// showing them errors.)
export async function load({ url }) {
  const me = await getMe();
  const onLogin = url.pathname === '/login';

  if (!me.authenticated && !onLogin) {
    redirect(307, `/login?next=${encodeURIComponent(url.pathname + url.search)}`);
  }
  if (me.authenticated && onLogin) {
    redirect(307, safeNext(url.searchParams.get('next')));
  }
  return { user: me.user ?? null, setup: !!me.setup, next: safeNext(url.searchParams.get('next')) };
}
