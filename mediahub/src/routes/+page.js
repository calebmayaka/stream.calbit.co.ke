import { getHome } from '$lib/data/api.js';

// Not awaited, so hovering "Home" or the logo starts loading the rows.
export function load() {
  const home = getHome();
  home.catch(() => {});
  return { home };
}
