import { getTitle } from '$lib/data/api.js';

// Not awaited: SvelteKit starts this on hover/touch (data-sveltekit-preload-data)
// and the page shows its skeleton until it resolves.
export function load({ params }) {
  const title = getTitle(params.id);
  title.catch(() => {}); // the page reports errors; don't log preloads nobody opened
  return { id: params.id, title };
}
