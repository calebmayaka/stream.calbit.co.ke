import adapter from '@sveltejs/adapter-static';

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    // SPA build: IIS serves build/ as plain files and rewrites unknown paths
    // to index.html (see static/web.config). All dynamic data comes from /api.
    adapter: adapter({
      pages: 'build',
      assets: 'build',
      fallback: 'index.html'
    })
  }
};

export default config;
