<!--
  Instant search (header button, "/" or Ctrl/⌘+K). Titles and people come back
  as separate lists so a common first name can't crowd out every title.
-->
<script>
  import { goto } from '$app/navigation';
  import { Search, X } from 'lucide-svelte';
  import { search } from '$lib/data/api.js';
  import MediaCard from './MediaCard.svelte';

  /** @type {{ onclose: () => void }} */
  let { onclose } = $props();

  const DEBOUNCE_MS = 220;

  let term = $state('');
  let results = $state([]);
  let people = $state([]);
  let loading = $state(false);
  let searched = $state('');
  let input = $state(null);

  $effect(() => {
    input?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden'; // no page scroll behind the sheet
    return () => (document.body.style.overflow = prev);
  });

  $effect(() => {
    const q = term.trim();
    if (q.length < 2) {
      results = [];
      people = [];
      searched = '';
      loading = false;
      return;
    }
    const controller = new AbortController();
    loading = true;
    const timer = setTimeout(async () => {
      try {
        const res = await search(q, { signal: controller.signal });
        results = res.results;
        people = res.people;
        searched = q;
      } catch (e) {
        if (e.name !== 'AbortError') results = [];
      } finally {
        if (!controller.signal.aborted) loading = false;
      }
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  });

  function onKey(e) {
    if (e.key === 'Escape') onclose();
    if (e.key === 'Enter' && results[0]) goto(results[0].href ?? `/title/${results[0].id}`);
  }
</script>

<div class="sheet" role="dialog" aria-modal="true" aria-label="Search">
  <div class="bar">
    <Search size={20} />
    <input
      bind:this={input}
      bind:value={term}
      onkeydown={onKey}
      type="search"
      placeholder="Search movies, shows, episodes, people…"
      aria-label="Search"
      autocomplete="off"
      spellcheck="false"
    />
    <button class="close" onclick={onclose} aria-label="Close search"><X size={20} /></button>
  </div>

  <div class="body">
    {#if term.trim().length < 2}
      <p class="hint">Type at least two letters. <kbd>Enter</kbd> opens the top result, <kbd>Esc</kbd> closes.</p>
    {:else if !loading && searched && !results.length && !people.length}
      <p class="hint">Nothing in your library matches “{searched}”.</p>
    {:else}
      {#if people.length}
        <h2>People</h2>
        <ul class="people no-scrollbar">
          {#each people as p (p.id)}
            <li>
              <a href={p.href}>
                <span class="face">{#if p.poster && !p.poster.startsWith('data:')}<img src={p.poster} alt="" loading="lazy" />{:else}{p.title[0]}{/if}</span>
                <span class="pname">{p.title}</span>
              </a>
            </li>
          {/each}
        </ul>
      {/if}
      {#if results.length}
        <h2>Titles {#if loading}<span class="dot" aria-hidden="true"></span>{/if}</h2>
        <div class="grid">
          {#each results as item (item.id)}<MediaCard {item} fluid />{/each}
        </div>
      {:else if loading}
        <p class="hint">Searching…</p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .sheet {
    position: fixed;
    inset: 0;
    z-index: 80;
    display: flex;
    flex-direction: column;
    background: rgba(4, 18, 11, 0.94);
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    animation: fade 0.2s ease;
  }
  @keyframes fade {
    from {
      opacity: 0;
    }
  }
  .bar {
    display: flex;
    align-items: center;
    gap: 0.8rem;
    margin: 1rem 1.5rem 0;
    padding: 0 0.6rem 0 1.1rem;
    height: 58px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.07);
    border: 0.8px solid rgba(255, 255, 255, 0.12);
    color: rgba(255, 255, 255, 0.6);
  }
  @media (min-width: 1024px) {
    .bar {
      margin: 1.2rem auto 0;
      width: min(900px, calc(100% - 6rem));
    }
  }
  .bar:focus-within {
    border-color: rgba(149, 255, 80, 0.55);
  }
  input {
    flex: 1;
    min-width: 0;
    height: 100%;
    border: 0;
    outline: none;
    background: transparent;
    color: #fff;
    font: inherit;
    font-size: 1.05rem;
  }
  input::-webkit-search-cancel-button {
    display: none;
  }
  .close {
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    border: 0;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: #fff;
    cursor: pointer;
  }
  .body {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem 1.5rem 6rem;
  }
  @media (min-width: 1024px) {
    .body {
      padding: 1.8rem 3rem 3rem;
    }
  }
  .hint {
    margin-top: 2rem;
    text-align: center;
    color: rgba(255, 255, 255, 0.55);
  }
  kbd {
    padding: 1px 6px;
    border-radius: 5px;
    border: 0.8px solid rgba(255, 255, 255, 0.25);
    font: inherit;
    font-size: 0.8em;
  }
  h2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 0.9rem;
    font-family: var(--font-display);
    font-size: 1.05rem;
    font-weight: 700;
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    background: var(--color-accent);
    animation: pulse 0.8s ease-in-out infinite alternate;
  }
  @keyframes pulse {
    to {
      opacity: 0.2;
    }
  }
  .people {
    display: flex;
    gap: 1rem;
    overflow-x: auto;
    list-style: none;
    padding: 0 0 0.4rem;
    margin: 0 0 1.6rem;
  }
  .people a {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.45rem;
    width: 92px;
    color: inherit;
    text-decoration: none;
    text-align: center;
  }
  .face {
    display: grid;
    place-items: center;
    width: 72px;
    height: 72px;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.08);
    font-weight: 700;
    font-size: 1.3rem;
    color: rgba(255, 255, 255, 0.5);
    transition: box-shadow 0.25s ease;
  }
  .people a:hover .face,
  .people a:focus-visible .face {
    box-shadow: 0 0 0 2px var(--color-accent);
  }
  .face img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .pname {
    font-size: 0.78rem;
    font-weight: 600;
    line-height: 1.2;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 1rem;
  }
  @media (min-width: 768px) {
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
    }
  }
</style>
