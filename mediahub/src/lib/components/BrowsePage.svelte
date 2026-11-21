<!--
  Shared library grid for /movies, /series, /collections and /mylist.
  Sort + genre live in the URL (?sort=&genre=) so views are linkable and the
  back button works; more titles load as you scroll.
-->
<script>
  import { untrack } from 'svelte';
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { browse, getGenres } from '$lib/data/api.js';
  import MediaCard from './MediaCard.svelte';

  /** @type {{ type: 'movies'|'series'|'collections'|'mylist', heading: string, blurb?: string, empty?: string }} */
  let { type, heading, blurb = '', empty = 'Nothing here yet.' } = $props();

  const PAGE = 48;
  const SORTS = [
    { id: 'added', label: 'Recently added' },
    { id: 'title', label: 'A–Z' },
    { id: 'year', label: 'Newest' },
    { id: 'rating', label: 'Top rated' },
    { id: 'random', label: 'Shuffle' }
  ];

  let items = $state([]);
  let total = $state(0);
  let next = $state(0);
  let loading = $state(false);
  let error = $state(null);
  let genres = $state([]);
  let sentinel = $state(null);
  let generation = 0;

  const sort = $derived(page.url.searchParams.get('sort') ?? 'added');
  const genre = $derived(page.url.searchParams.get('genre') ?? '');
  const hasGenres = $derived(type === 'movies' || type === 'series');
  const done = $derived(next >= total && total > 0);

  function setParam(key, value) {
    const url = new URL(page.url);
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
    goto(url, { replaceState: true, noScroll: true, keepFocus: true });
  }

  async function loadMore() {
    if (loading || (total && next >= total)) return;
    loading = true;
    const gen = generation;
    try {
      const res = await browse({ type, sort, genre, start: next, limit: PAGE });
      if (gen !== generation) return; // filters changed meanwhile
      const seen = new Set(items.map((i) => i.id));
      items = [...items, ...res.items.filter((i) => !seen.has(i.id))];
      total = res.total;
      next = res.next;
      error = null;
    } catch (e) {
      if (gen === generation) error = e.message;
    } finally {
      if (gen === generation) loading = false;
    }
  }

  // Reset + first page whenever the view or its filters change.
  $effect(() => {
    type;
    sort;
    genre;
    generation++;
    items = [];
    total = 0;
    next = 0;
    loading = false;
    error = null;
    untrack(loadMore); // its reads of loading/next/total must not re-trigger this reset
  });

  $effect(() => {
    if (!hasGenres) return;
    getGenres(type)
      .then((g) => (genres = g))
      .catch(() => (genres = []));
  });

  // Infinite scroll: keep fetching while the sentinel is near the viewport.
  // (The observer only fires on changes, so a page that finishes loading with
  // the sentinel still visible must trigger the next fetch itself.)
  let nearEnd = $state(false);
  $effect(() => {
    if (!sentinel) return;
    const io = new IntersectionObserver((entries) => (nearEnd = entries[0].isIntersecting), {
      rootMargin: '800px 0px'
    });
    io.observe(sentinel);
    return () => io.disconnect();
  });
  $effect(() => {
    if (nearEnd && !loading && !error && !done && items.length) untrack(loadMore);
  });

  // Fallback for webviews/background panes where observers don't fire.
  function checkNearEnd() {
    if (sentinel) nearEnd = sentinel.getBoundingClientRect().top < window.innerHeight + 800;
  }
</script>

<svelte:head>
  <title>{heading} · MediaHub</title>
</svelte:head>

<svelte:window onscroll={checkNearEnd} onresize={checkNearEnd} />

<section class="browse">
  <header class="head">
    <div>
      <h1 class="font-display">{heading}{#if genre}<span class="genre-tag">{genre}</span>{/if}</h1>
      <p class="sub">
        {#if total}{total} {total === 1 ? 'title' : 'titles'}{:else if !loading}{blurb}{/if}
      </p>
    </div>
    <div class="sorts" role="radiogroup" aria-label="Sort by">
      {#each SORTS as s (s.id)}
        <button role="radio" aria-checked={sort === s.id} class:active={sort === s.id} onclick={() => setParam('sort', s.id === 'added' ? '' : s.id)}>
          {s.label}
        </button>
      {/each}
    </div>
  </header>

  {#if hasGenres && genres.length}
    <div class="genres no-scrollbar" role="radiogroup" aria-label="Genre">
      <button role="radio" aria-checked={!genre} class:active={!genre} onclick={() => setParam('genre', '')}>All</button>
      {#each genres as g (g)}
        <button role="radio" aria-checked={genre === g} class:active={genre === g} onclick={() => setParam('genre', g)}>{g}</button>
      {/each}
    </div>
  {/if}

  {#if error && !items.length}
    <div class="state">
      <p class="font-display">Couldn’t load {heading.toLowerCase()}</p>
      <span>{error}</span>
      <button class="retry" onclick={loadMore}>Try again</button>
    </div>
  {:else if !loading && !items.length}
    <div class="state">
      <p class="font-display">{empty}</p>
      {#if genre}<button class="retry" onclick={() => setParam('genre', '')}>Show all genres</button>{/if}
    </div>
  {:else}
    <div class="grid">
      {#each items as item (item.id)}<MediaCard {item} fluid />{/each}
      {#if loading}
        {#each { length: items.length ? 6 : 18 } as _}<div class="ghost-card" aria-hidden="true"></div>{/each}
      {/if}
    </div>
  {/if}

  {#if !done}<div bind:this={sentinel} class="sentinel" aria-hidden="true"></div>{/if}
</section>

<style>
  .browse {
    padding: 6.5rem 1.5rem 2rem;
  }
  @media (min-width: 1024px) {
    .browse {
      padding: 7.5rem 3rem 2rem;
    }
  }
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.1rem;
  }
  h1 {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    font-size: clamp(1.8rem, 4vw, 2.6rem);
    font-weight: 800;
    letter-spacing: -0.03em;
  }
  .genre-tag {
    padding: 4px 12px;
    border-radius: 999px;
    font-family: var(--font-sans);
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0;
    color: var(--color-accent);
    background: rgba(149, 255, 80, 0.1);
    border: 0.8px solid rgba(149, 255, 80, 0.4);
  }
  .sub {
    margin-top: 0.25rem;
    color: rgba(255, 255, 255, 0.55);
    font-size: 0.9rem;
    min-height: 1.3em;
  }
  .sorts,
  .genres {
    display: flex;
    gap: 4px;
  }
  .sorts {
    flex-wrap: wrap;
    padding: 5px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.05);
    border: 0.8px solid rgba(255, 255, 255, 0.07);
  }
  .genres {
    overflow-x: auto;
    margin-bottom: 1.4rem;
    padding-bottom: 2px;
  }
  .sorts button,
  .genres button {
    flex: 0 0 auto;
    height: 34px;
    padding: 0 0.95rem;
    border: 0;
    border-radius: 999px;
    background: transparent;
    color: rgba(255, 255, 255, 0.65);
    font: inherit;
    font-size: 0.83rem;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.25s ease, color 0.25s ease;
  }
  .genres button {
    background: rgba(255, 255, 255, 0.06);
  }
  .sorts button:hover,
  .genres button:hover {
    color: #fff;
  }
  .sorts button.active,
  .genres button.active {
    background: #fff;
    color: #000;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 1rem;
  }
  @media (min-width: 768px) {
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
      gap: 1.3rem 1.2rem;
    }
  }
  .ghost-card {
    aspect-ratio: 2 / 3;
    border-radius: 12px;
    background: linear-gradient(110deg, rgba(255, 255, 255, 0.04) 30%, rgba(255, 255, 255, 0.09) 50%, rgba(255, 255, 255, 0.04) 70%);
    background-size: 200% 100%;
    animation: shimmer 1.4s linear infinite;
  }
  @keyframes shimmer {
    to {
      background-position: -200% 0;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .ghost-card {
      animation: none;
    }
  }
  .sentinel {
    height: 1px;
  }
  .state {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 0.6rem;
    min-height: 40vh;
    text-align: center;
    color: rgba(255, 255, 255, 0.6);
  }
  .state p {
    color: #fff;
    font-size: 1.2rem;
    font-weight: 700;
  }
  .retry {
    margin-top: 0.4rem;
    height: 40px;
    padding: 0 1.2rem;
    border: 0;
    border-radius: 999px;
    background: var(--color-accent);
    color: #04120b;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
</style>
