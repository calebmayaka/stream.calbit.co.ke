// Deterministic gradient "poster" generator so the shell needs zero external
// images. Real posters later come from Jellyfin / your file index — just put a
// URL in item.poster and these are ignored.

const PALETTES = [
  ['#0f3d2e', '#95ff50'],
  ['#1a2a6c', '#b21f1f'],
  ['#232526', '#414345'],
  ['#42275a', '#734b6d'],
  ['#0f2027', '#2c5364'],
  ['#3a1c71', '#d76d77'],
  ['#136a8a', '#267871'],
  ['#4b6cb7', '#182848'],
  ['#5c258d', '#4389a2'],
  ['#1d4350', '#a43931']
];

function hash(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
  return Math.abs(h);
}

// Text goes straight into SVG markup, so XML-special characters must be escaped
// or titles like "Code & Chai" produce an invalid (blank) image.
const XML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;' };
function esc(str) {
  return String(str).replace(/[&<>"']/g, (c) => XML_ESCAPES[c]);
}

/** Build a 2:3 gradient poster as a data URI, seeded by the title. */
export function poster(title, kind = '') {
  const h = hash(title);
  const [a, b] = PALETTES[h % PALETTES.length];
  const angle = h % 360;
  const initials = title
    .split(/\s+/)
    .filter((w) => /^[\p{L}\p{N}]/u.test(w)) // skip "&", "-", etc.
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase();

  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='300' height='450' viewBox='0 0 300 450'>
    <defs>
      <linearGradient id='g' gradientTransform='rotate(${angle})'>
        <stop offset='0' stop-color='${a}'/>
        <stop offset='1' stop-color='${b}'/>
      </linearGradient>
    </defs>
    <rect width='300' height='450' fill='url(#g)'/>
    <circle cx='${h % 300}' cy='${h % 450}' r='120' fill='#ffffff' opacity='0.06'/>
    <text x='24' y='410' font-family='Montserrat, Inter, sans-serif' font-size='120'
      font-weight='800' fill='#ffffff' opacity='0.14'>${esc(initials)}</text>
    ${kind ? `<text x='24' y='40' font-family='Inter, sans-serif' font-size='16' font-weight='600' fill='#ffffff' opacity='0.5'>${esc(kind.toUpperCase())}</text>` : ''}
  </svg>`;

  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}

/** Wider 16:9 backdrop for the hero. */
export function backdrop(title) {
  const h = hash(title + 'bg');
  const [a, b] = PALETTES[h % PALETTES.length];
  const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' viewBox='0 0 1280 720'>
    <defs><radialGradient id='r' cx='30%' cy='35%' r='80%'>
      <stop offset='0' stop-color='${b}'/><stop offset='1' stop-color='${a}'/>
    </radialGradient></defs>
    <rect width='1280' height='720' fill='url(#r)'/>
    <circle cx='980' cy='200' r='300' fill='#ffffff' opacity='0.05'/>
    <circle cx='300' cy='560' r='240' fill='#000000' opacity='0.12'/>
  </svg>`;
  return 'data:image/svg+xml;utf8,' + encodeURIComponent(svg);
}
