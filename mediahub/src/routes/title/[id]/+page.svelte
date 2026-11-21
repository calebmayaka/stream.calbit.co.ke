<script>
  import { page } from '$app/state';
  import { goto } from '$app/navigation';
  import { Play, RotateCcw, Star, Plus, Check, Clapperboard, Eye, EyeOff } from 'lucide-svelte';
  import { getTitle, setFavorite, setPlayed } from '$lib/data/api.js';
  import Player from '$lib/components/Player.svelte';
  import MediaRow from '$lib/components/MediaRow.svelte';
  import MediaCard from '$lib/components/MediaCard.svelte';
  import TrailerModal from '$lib/components/TrailerModal.svelte';

  let data = $state(null);
  let error = $state(null);
  let seasonId = $state(null);
  let trailerOpen = $state(false);
  let busy = $state(false);
  /** @type {{ id: string, subtitle: string|null, start: number } | null} */
  let playing = $state(null);

  const id = $derived(page.params.id);
  const season = $derived(data?.seasons.find((s) => s.id === seasonId) ?? data?.seasons[0]);
  const canMarkWatched = $derived(data && (data.playable || data.kind === 'series'));

  // Route data from +page.js: the fetch starts on hover/touch (preloading),
  // so the page is often ready by the time the link is clicked.
  let { data: route } = $props();

  async function show(itemId, pending) {
    try {
      const fresh = await pending;
      if (itemId !== id) return; // navigated away meanwhile
      data = fresh;
      error = null;
      if (!fresh.seasons.some((s) => s.id === seasonId)) seasonId = fresh.seasons[0]?.id ?? null;
    } catch (e) {
      if (itemId === id) error = e.message;
    }
  }

  /** Re-fetch (after playing or marking watched). */
  function load(itemId) {
    return show(itemId, getTitle(itemId));
  }

  $effect(() => {
    const itemId = route.id;
    const pending = route.title;
    data = null;
    playing = null;
    trailerOpen = false;
    error = null;
    show(itemId, pending);
  });

  // ?play=1 (hero "Play" button) starts playback as soon as details arrive.
  $effect(() => {
    if (data && !playing && page.url.searchParams.get('play') === '1') {
      goto(`/title/${id}`, { replaceState: true, noScroll: true, keepFocus: true });
      playMain(true);
    }
  });

  function playMain(resume = true) {
    if (!data?.playId) return;
    playing = { id: data.playId, subtitle: data.subtitle, start: resume ? (data.resume?.seconds ?? 0) : 0 };
  }

  function playEpisode(ep) {
    const resumeAt = ep.percent > 0 && !ep.played && ep.id === data.playId ? (data.resume?.seconds ?? 0) : 0;
    playing = { id: ep.id, subtitle: [ep.code, ep.title].filter(Boolean).join(' · '), start: resumeAt };
  }

  /** Player finished an episode and the countdown ran out (or "Play now"). */
  function playNext(next) {
    playing = { id: next.id, subtitle: next.label, start: 0 };
  }

  function closePlayer() {
    playing = null;
    load(id); // pick up the new resume point / watched state
  }

  async function toggleFavorite() {
    if (busy) return;
    busy = true;
    const want = !data.favorite;
    data.favorite = want; // optimistic
    try {
      data.favorite = (await setFavorite(data.id, want)).favorite;
    } catch {
      data.favorite = !want;
    } finally {
      busy = false;
    }
  }

  async function togglePlayed() {
    if (busy) return;
    busy = true;
    try {
      await setPlayed(data.id, !data.played);
      await load(id); // series/episode progress all change
    } finally {
      busy = false;
    }
  }

  async function toggleEpisodePlayed(ep) {
    const want = !ep.played;
    ep.played = want;
    ep.percent = 0;
    try {
      await setPlayed(ep.id, want);
    } catch {
      ep.played = !want;
    }
  }

  function clock(seconds) {
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    const mm = String(m).padStart(h ? 2 : 1, '0');
    return `${h ? `${h}:` : ''}${mm}:${String(s).padStart(2, '0')}`;
  }
</script>

<svelte:head>
  <title>{data ? `${data.title} · MediaHub` : 'MediaHub'}</title>
</svelte:head>

{#if error}
  <div class="state">
    <p class="font-display">Couldn’t load this title</p>
    <span>{error}</span>
    <a href="/" class="btn ghost glass">Back home</a>
  </div>
{:else if !data}
  <div class="skeleton" aria-busy="true"></div>
{:else}
  <section class="hero">
    <img class="backdrop" src={data.backdrop} alt="" aria-hidden="true" />
    <div class="scrim"></div>

    <div class="content">
      <img class="poster" src={data.poster} alt="" />
      <div class="info">
        <span class="kind">{data.kind}</span>
        <h1 class="title font-display">{data.title}</h1>
        {#if data.subtitle}<p class="subtitle">{data.subtitle}</p>{/if}

        <div class="meta">
          {#if data.rating}<span class="rating"><Star size={13} fill="currentColor" stroke="currentColor" />{data.rating}</span>{/if}
          {#if data.year}<span>{data.year}</span>{/if}
          {#if data.runtime}<span>{data.runtime}</span>{/if}
          {#if data.officialRating}<span class="cert">{data.officialRating}</span>{/if}
          {#if data.played}<span class="seen"><Check size={13} strokeWidth={3} /> Watched</span>{/if}
        </div>

        {#if data.genres.length}
          <div class="genres">
            {#each data.genres.slice(0, 4) as g}<a href={`/${data.kind === 'series' ? 'series' : 'movies'}?genre=${encodeURIComponent(g)}`}>{g}</a>{/each}
          </div>
        {/if}

        {#if data.tagline}<p class="tagline">“{data.tagline}”</p>{/if}
        <p class="overview">{data.overview}</p>

        <div class="cta">
          {#if data.playable}
            {#if data.resume}
              <button class="btn primary" onclick={() => playMain(true)}>
                <Play size={18} fill="#04120b" stroke="#04120b" /> Resume {clock(data.resume.seconds)}
              </button>
              <button class="btn ghost glass" onclick={() => playMain(false)}>
                <RotateCcw size={17} /> From start
              </button>
            {:else}
              <button class="btn primary" onclick={() => playMain(false)}>
                <Play size={18} fill="#04120b" stroke="#04120b" /> Play
              </button>
            {/if}
          {/if}
          {#if data.trailers.length}
            <button class="btn ghost glass" onclick={() => (trailerOpen = true)}><Clapperboard size={17} /> Trailer</button>
          {/if}
          <button
            class="btn icon glass"
            class:on={data.favorite}
            onclick={toggleFavorite}
            aria-pressed={data.favorite}
            aria-label={data.favorite ? 'Remove from My List' : 'Add to My List'}
            title={data.favorite ? 'In My List' : 'Add to My List'}
          >
            {#if data.favorite}<Check size={19} strokeWidth={2.6} />{:else}<Plus size={19} />{/if}
          </button>
          {#if canMarkWatched}
            <button
              class="btn icon glass"
              onclick={togglePlayed}
              disabled={busy}
              aria-label={data.played ? 'Mark as unwatched' : 'Mark as watched'}
              title={data.played ? 'Mark as unwatched' : 'Mark as watched'}
            >
              {#if data.played}<EyeOff size={18} />{:else}<Eye size={18} />{/if}
            </button>
          {/if}
          {#if data.seriesId}
            <a class="btn ghost glass" href={`/title/${data.seriesId}`}>All episodes</a>
          {/if}
        </div>
        {#if data.playable && data.resume}
          <div class="resume-bar" aria-hidden="true"><span style="width: {data.resume.percent}%"></span></div>
        {/if}
      </div>
    </div>
  </section>

  {#if data.items.length}
    <section class="block">
      <div class="block-head"><h2 class="font-display">In this collection</h2></div>
      <div class="grid">
        {#each data.items as item (item.id)}<MediaCard {item} fluid />{/each}
      </div>
    </section>
  {/if}

  {#if data.seasons.length}
    <section class="block">
      <div class="block-head">
        <h2 class="font-display">Episodes</h2>
        {#if data.seasons.length > 1}
          <div class="seasons no-scrollbar" role="tablist">
            {#each data.seasons as s (s.id)}
              <button
                role="tab"
                aria-selected={s.id === season?.id}
                class:active={s.id === season?.id}
                onclick={() => (seasonId = s.id)}>{s.name}</button
              >
            {/each}
          </div>
        {/if}
      </div>

      <ol class="episodes">
        {#each season?.episodes ?? [] as ep, i (ep.id)}
          <li>
            <button class="episode" onclick={() => playEpisode(ep)}>
              <div class="thumb">
                {#if ep.thumb}<img src={ep.thumb} alt="" loading="lazy" />{/if}
                <span class="play-dot"><Play size={16} fill="#04120b" stroke="#04120b" /></span>
                {#if ep.percent > 0 && !ep.played}
                  <span class="ep-progress"><span style="width: {ep.percent}%"></span></span>
                {/if}
              </div>
              <div class="ep-text">
                <p class="ep-title">
                  <span class="ep-num">{ep.number ?? i + 1}</span>
                  {ep.title}
                  {#if ep.played}<span class="watched">Watched</span>{/if}
                </p>
                {#if ep.runtime}<span class="ep-runtime">{ep.runtime}</span>{/if}
                {#if ep.overview}<p class="ep-overview">{ep.overview}</p>{/if}
              </div>
            </button>
            <button
              class="ep-toggle"
              class:on={ep.played}
              onclick={() => toggleEpisodePlayed(ep)}
              aria-label={ep.played ? `Mark ${ep.title} unwatched` : `Mark ${ep.title} watched`}
              title={ep.played ? 'Mark unwatched' : 'Mark watched'}
            >
              <Check size={15} strokeWidth={2.6} />
            </button>
          </li>
        {/each}
      </ol>
    </section>
  {/if}

  {#if data.cast.length}
    <section class="block">
      <div class="block-head"><h2 class="font-display">Cast</h2></div>
      <ul class="cast no-scrollbar">
        {#each data.cast as person (person.id + person.role)}
          <li>
            <a class="person" href={`/person/${person.id}`}>
              <div class="face">
                {#if person.image}<img src={person.image} alt="" loading="lazy" />{:else}<span>{person.name[0]}</span>{/if}
              </div>
              <p class="name">{person.name}</p>
              {#if person.role}<p class="role">{person.role}</p>{/if}
            </a>
          </li>
        {/each}
      </ul>
    </section>
  {/if}

  {#if data.similar.length}
    <MediaRow title="More like this" items={data.similar} />
  {/if}
{/if}

{#if trailerOpen && data?.trailers.length}
  <TrailerModal trailers={data.trailers} onclose={() => (trailerOpen = false)} />
{/if}

{#if playing && data}
  {#key playing.id}
    <Player
      itemId={playing.id}
      title={data.title}
      subtitle={playing.subtitle}
      startSeconds={playing.start}
      onclose={closePlayer}
      onnext={playNext}
    />
  {/key}
{/if}

<style>
  .hero {
    position: relative;
    min-height: 82vh;
    display: flex;
    align-items: flex-end;
    overflow: hidden;
  }
  .backdrop {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    object-position: center 20%;
  }
  .scrim {
    position: absolute;
    inset: 0;
    background:
      linear-gradient(to top, var(--color-bg) 4%, rgba(4, 18, 11, 0.55) 45%, rgba(4, 18, 11, 0.2) 75%),
      linear-gradient(to right, rgba(4, 18, 11, 0.92) 0%, rgba(4, 18, 11, 0.4) 50%, transparent 80%);
  }
  .content {
    position: relative;
    display: flex;
    align-items: flex-end;
    gap: 2rem;
    width: 100%;
    padding: 7rem 1.5rem 2.5rem;
  }
  @media (min-width: 1024px) {
    .content {
      padding: 8rem 3rem 3rem;
    }
  }
  .poster {
    display: none;
    width: 220px;
    aspect-ratio: 2 / 3;
    object-fit: cover;
    border-radius: 14px;
    box-shadow: 0 30px 50px -10px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.08);
    flex: 0 0 auto;
  }
  @media (min-width: 900px) {
    .poster {
      display: block;
    }
  }
  .info {
    max-width: 680px;
  }
  .kind {
    display: inline-block;
    margin-bottom: 0.7rem;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--color-accent);
    border: 0.8px solid rgba(149, 255, 80, 0.4);
    background: rgba(149, 255, 80, 0.08);
  }
  .title {
    font-size: clamp(2rem, 5.5vw, 3.8rem);
    font-weight: 800;
    line-height: 1.02;
    letter-spacing: -0.03em;
    text-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
  }
  .subtitle {
    margin-top: 0.5rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.85);
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.9rem;
    margin: 1rem 0 0.8rem;
    font-size: 0.88rem;
    color: rgba(255, 255, 255, 0.78);
  }
  .rating {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--color-accent);
    font-weight: 700;
  }
  .cert {
    padding: 1px 7px;
    border: 0.8px solid rgba(255, 255, 255, 0.35);
    border-radius: 5px;
    font-size: 0.75rem;
  }
  .genres {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
    margin-bottom: 1rem;
  }
  .genres a {
    padding: 3px 11px;
    border-radius: 999px;
    font-size: 0.75rem;
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.85);
    text-decoration: none;
    transition: background 0.25s ease;
  }
  .genres a:hover {
    background: rgba(255, 255, 255, 0.16);
  }
  .seen {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--color-accent);
    font-weight: 600;
  }
  .btn.icon {
    width: 46px;
    padding: 0;
    justify-content: center;
  }
  .btn.icon.on {
    color: var(--color-accent);
    border-color: rgba(149, 255, 80, 0.5);
  }
  .btn:disabled {
    opacity: 0.6;
    cursor: progress;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 1rem;
  }
  @media (min-width: 768px) {
    .grid {
      grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
      gap: 1.2rem;
    }
  }
  .episodes li {
    position: relative;
  }
  .ep-toggle {
    position: absolute;
    top: 0.9rem;
    right: 0.6rem;
    display: grid;
    place-items: center;
    width: 32px;
    height: 32px;
    border: 0.8px solid rgba(255, 255, 255, 0.18);
    border-radius: 999px;
    background: rgba(4, 18, 11, 0.6);
    color: rgba(255, 255, 255, 0.45);
    cursor: pointer;
    transition: color 0.2s ease, border-color 0.2s ease, background 0.2s ease;
  }
  .ep-toggle:hover {
    color: #fff;
    border-color: rgba(255, 255, 255, 0.4);
  }
  .ep-toggle.on {
    color: #04120b;
    background: var(--color-accent);
    border-color: var(--color-accent);
  }
  .episode {
    padding-right: 3.2rem;
  }
  .person {
    display: block;
    color: inherit;
    text-decoration: none;
  }
  .person:hover .face {
    box-shadow: 0 0 0 2px var(--color-accent);
  }
  .tagline {
    font-style: italic;
    color: rgba(255, 255, 255, 0.7);
    margin-bottom: 0.4rem;
  }
  .overview {
    font-size: 0.95rem;
    line-height: 1.55;
    color: rgba(255, 255, 255, 0.84);
    max-width: 62ch;
  }
  .cta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.7rem;
    margin-top: 1.6rem;
  }
  .btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    height: 46px;
    padding: 0 1.4rem;
    border: 0;
    border-radius: 999px;
    font: inherit;
    font-weight: 600;
    font-size: 0.95rem;
    color: #fff;
    text-decoration: none;
    cursor: pointer;
    transition: transform var(--hover-time) var(--ease-hover), filter 0.25s ease;
  }
  .btn:hover {
    transform: scale(1.04);
  }
  .btn.primary {
    background: var(--color-accent);
    color: #04120b;
  }
  .resume-bar {
    width: 260px;
    max-width: 100%;
    height: 4px;
    margin-top: 0.9rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.15);
    overflow: hidden;
  }
  .resume-bar span,
  .ep-progress span {
    display: block;
    height: 100%;
    background: var(--color-accent);
  }

  .block {
    padding: 1rem 1.5rem 1.5rem;
  }
  @media (min-width: 1024px) {
    .block {
      padding: 1rem 3rem 2rem;
    }
  }
  .block-head {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 0.8rem;
    margin-bottom: 1rem;
  }
  .block-head h2 {
    font-size: 1.2rem;
    font-weight: 700;
  }
  .seasons {
    display: flex;
    gap: 4px;
    padding: 5px;
    max-width: 100%;
    overflow-x: auto;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.05);
    border: 0.8px solid rgba(255, 255, 255, 0.07);
  }
  .seasons button {
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
  .seasons button:hover {
    color: #fff;
  }
  .seasons button.active {
    background: #fff;
    color: #000;
  }

  .episodes {
    display: grid;
    gap: 0.6rem;
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .episode {
    display: flex;
    gap: 1rem;
    width: 100%;
    padding: 0.6rem;
    border: 0;
    border-radius: 14px;
    background: transparent;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
    transition: background 0.25s ease;
  }
  .episode:hover,
  .episode:focus-visible {
    background: rgba(255, 255, 255, 0.06);
  }
  .thumb {
    position: relative;
    flex: 0 0 auto;
    width: 150px;
    aspect-ratio: 16 / 9;
    border-radius: 10px;
    overflow: hidden;
    background: var(--color-bg-soft);
  }
  @media (min-width: 768px) {
    .thumb {
      width: 220px;
    }
  }
  .thumb img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .play-dot {
    position: absolute;
    top: 50%;
    left: 50%;
    display: grid;
    place-items: center;
    width: 38px;
    height: 38px;
    border-radius: 999px;
    background: var(--color-accent);
    transform: translate(-50%, -50%) scale(0.8);
    opacity: 0;
    transition: opacity var(--hover-time) var(--ease-hover), transform var(--hover-time) var(--ease-spring);
  }
  .episode:hover .play-dot,
  .episode:focus-visible .play-dot {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }
  .ep-progress {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 3px;
    background: rgba(0, 0, 0, 0.5);
  }
  .ep-text {
    min-width: 0;
    padding-top: 0.2rem;
  }
  .ep-title {
    font-weight: 600;
    font-size: 0.95rem;
  }
  .ep-num {
    margin-right: 0.35rem;
    color: rgba(255, 255, 255, 0.45);
  }
  .watched {
    margin-left: 0.4rem;
    padding: 1px 7px;
    border-radius: 999px;
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    background: rgba(149, 255, 80, 0.15);
    color: var(--color-accent);
  }
  .ep-runtime {
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.55);
  }
  .ep-overview {
    margin-top: 0.35rem;
    font-size: 0.85rem;
    line-height: 1.45;
    color: rgba(255, 255, 255, 0.68);
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    overflow: hidden;
  }

  .cast {
    display: flex;
    gap: 1.1rem;
    overflow-x: auto;
    list-style: none;
    padding: 0 0 0.5rem;
    margin: 0;
  }
  .cast li {
    flex: 0 0 auto;
    width: 104px;
    text-align: center;
  }
  .face {
    display: grid;
    place-items: center;
    width: 88px;
    height: 88px;
    margin: 0 auto 0.5rem;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.08);
    font-weight: 700;
    font-size: 1.4rem;
    color: rgba(255, 255, 255, 0.5);
  }
  .face img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .name {
    font-size: 0.8rem;
    font-weight: 600;
  }
  .role {
    font-size: 0.72rem;
    color: rgba(255, 255, 255, 0.55);
  }

  .skeleton {
    height: 82vh;
    background: linear-gradient(to top, var(--color-bg), rgba(255, 255, 255, 0.03));
  }
  .state {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 0.6rem;
    min-height: 70vh;
    padding: 0 1.5rem;
    text-align: center;
    color: rgba(255, 255, 255, 0.6);
  }
  .state p {
    color: #fff;
    font-size: 1.3rem;
    font-weight: 700;
  }
  .state .btn {
    margin-top: 0.8rem;
  }
</style>
