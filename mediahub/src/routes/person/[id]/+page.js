import { getPerson } from '$lib/data/api.js';

// Not awaited, so hovering an actor starts loading their page.
export function load({ params }) {
  const person = getPerson(params.id);
  person.catch(() => {});
  return { id: params.id, person };
}
