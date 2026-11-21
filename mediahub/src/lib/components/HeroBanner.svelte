<!--
  Rotating featured banner. Django sends a fresh random set of titles with
  backdrop art on every load; this crossfades through them every SLIDE_MS,
  pausing while the pointer/focus is on it or the tab is hidden. Only the
  current and next backdrops are fetched, so 8 slides don't cost 8 big images
  up front.
-->
<script>
  import { fade } from 'svelte/transition';
  import { Play, Plus, Info, Check } from 'lucide-svelte';
  import { setFavorite } from '$lib/data/api.js';

  /** @typedef {{ id: string, title: string, overview: string, backdrop: string, meta?: string[], badge?: string, favorite?: boolean }} Hero */
  /** @type {{ items: Hero[] }} */
  let { items } = $props();

  // items arrive as plain (non-reactive) data, so My List state lives here.
  let saved = $state({});
  const isSaved = (hero) => saved[hero.id] ?? !!hero.favorite;

  async function toggleList(hero) {
    const want = !isSaved(hero);
    saved[hero.id] = want; // optimistic
    try {
      saved[hero.id] = (await setFavorite(hero.id, want)).favorite;
    } catch {
      saved[hero.id] = !want;
    }
  }

  const SLIDE_MS = 8000;

  let index = $state(0);
  let hovering = $state(false);
  let keyboardFocus = $state(false); // mouse clicks on dots shouldn't stop the rotation
  let hidden = $state(false);
  let reducedMotion = $state(false);
  // Only the current slide and the one fading out are in the page. Keeping all
  // eight full-screen backdrops stacked (even invisible) cost a lot of memory
  // and compositing on weaker PCs.
  let previous = $state(-1);
  // Off-screen (scrolled down): stop rotating. Browsers skip drawing and
  // decoding off-screen images, so slides that changed while away glitched
  // (blank/half-faded) on the way back up.
  let onScreen = $state(true);
  let section = $state(null);

  const item = $derived(items[index]);
  const paused = $derived(hovering || keyboardFocus || hidden || !onScreen || items.length < 2);

  /** Load *and decode* a backdrop, so it can be drawn the moment it's shown. */
  const ready = new Map();
  function prepare(i) {
    const slide = items[(i + items.length) % items.length];
    if (!slide?.backdrop) return Promise.resolve();
    if (!ready.has(slide.backdrop)) {
      const img = new Image();
      img.src = slide.backdrop;
      // decode() can reject (e.g. broken image): still allow the switch.
      ready.set(slide.backdrop, img.decode().catch(() => {}));
    }
    return ready.get(slide.backdrop);
  }

  let switching = 0;
  async function go(i) {
    const target = (i + items.length) % items.length;
    const ticket = ++switching;
    // Wait (up to 4 s) until the picture is decoded, so it never fades in empty.
    await Promise.race([prepare(target), new Promise((r) => setTimeout(r, 4000))]);
    if (ticket !== switching) return; // a newer click/tick won
    previous = index;
    index = target;
    remaining = SLIDE_MS;
    prepare(target + 1);
  }

  // Time left on the current slide (plain variable: not a reactive dependency).
  // After a pause the timer resumes where the progress dot stopped, instead of
  // restarting the full 8 s while the dot is already half full.
  let remaining = SLIDE_MS;

  $effect(() => {
    prepare(1);
  });

  $effect(() => {
    if (!section) return;
    const io = new IntersectionObserver((entries) => (onScreen = entries[0].isIntersecting), { threshold: 0.15 });
    io.observe(section);
    return () => io.disconnect();
  });

  $effect(() => {
    if (paused) return;
    const slide = index;
    const started = performance.now();
    const timer = setTimeout(() => go(slide + 1), remaining);
    return () => {
      clearTimeout(timer);
      // Paused mid-slide: keep what's left. (A slide change resets it in go().)
      if (index === slide) remaining = Math.max(0, remaining - (performance.now() - started));
    };
  });

  $effect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const sync = () => (reducedMotion = media.matches);
    const vis = () => (hidden = document.hidden);
    sync();
    media.addEventListener('change', sync);
    document.addEventListener('visibilitychange', vis);
    return () => {
      media.removeEventListener('change', sync);
      document.removeEventListener('visibilitychange', vis);
    };
  });
</script>

<section
  bind:this={section}
  class="hero"
  aria-roledescription="carousel"
  aria-label="Featured"
  onpointerenter={() => (hovering = true)}
  onpointerleave={() => (hovering = false)}
  onfocusin={(e) => (keyboardFocus = e.target.matches(':focus-visible'))}
  onfocusout={() => (keyboardFocus = false)}
>
  {#each items as slide, i (slide.id)}
    {#if i === index || i === previous}
      <img
        class="backdrop"
        class:active={i === index}
        class:still={reducedMotion}
        src={slide.backdrop}
        alt=""
        aria-hidden="true"
      />
    {/if}
  {/each}
  <div class="scrim"></div>

  {#key item.id}
    <div class="content" in:fade={{ duration: reducedMotion ? 0 : 500, delay: reducedMotion ? 0 : 150 }}>
      {#if item.badge}<span class="tag">{item.badge}</span>{/if}
      <h1 class="title font-display">{item.title}</h1>
      {#if item.meta?.length}
        <div class="meta">
          {#each item.meta as m}<span>{m}</span>{/each}
        </div>
      {/if}
      <p class="overview">{item.overview}</p>
      <div class="cta">
        <a class="btn primary" href={`/title/${item.id}?play=1`}><Play size={18} fill="#04120b" stroke="#04120b" /> Play</a>
        <button class="btn ghost glass" class:saved={isSaved(item)} onclick={() => toggleList(item)} aria-pressed={isSaved(item)}>
          {#if isSaved(item)}<Check size={18} strokeWidth={2.6} /> In My List{:else}<Plus size={18} /> My List{/if}
        </button>
        <a class="btn icon glass" href={`/title/${item.id}`} aria-label="More info"><Info size={18} /></a>
      </div>
    </div>
  {/key}

  {#if items.length > 1}
    <div class="dots" role="tablist" aria-label="Choose featured title">
      {#each items as slide, i (slide.id)}
        <button
          role="tab"
          aria-selected={i === index}
          aria-label={slide.title}
          class:active={i === index}
          onclick={() => go(i)}
        >
          {#if i === index}
            {#key index}
              <span class="fill" class:paused style="animation-duration: {SLIDE_MS}ms"></span>
            {/key}
          {/if}
        </button>
      {/each}
    </div>
  {/if}
</section>

<style>
  .hero {
    position: relative;
    height: 78vh;
    min-height: 480px;
    max-height: 760px;
    width: 100%;
    overflow: hidden;
  }
  .backdrop {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    /* The outgoing slide stays put underneath (at its end state) while the
       new one fades in on top; then the old one is removed from the page. */
    z-index: 0;
    transform: scale(1.08);
  }
  /* fade in + slow push-in while showing */
  .backdrop.active {
    z-index: 1;
    animation: slide-in 9s linear both;
  }
  @keyframes slide-in {
    from {
      opacity: 0;
      transform: scale(1.02);
    }
    13% {
      opacity: 1;
    }
    to {
      opacity: 1;
      transform: scale(1.08);
    }
  }
  .backdrop.still,
  .backdrop.still.active {
    transform: scale(1.02);
    animation: none;
  }

  .dots {
    position: absolute;
    right: 1.5rem;
    bottom: 8%;
    display: flex;
    gap: 6px;
  }
  @media (min-width: 1024px) {
    .dots {
      right: 3rem;
    }
  }
  .dots button {
    position: relative;
    width: 18px;
    height: 6px;
    padding: 0;
    border: 0;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.28);
    overflow: hidden;
    cursor: pointer;
    transition: width 0.4s var(--ease-hover), background 0.3s ease;
  }
  .dots button:hover {
    background: rgba(255, 255, 255, 0.5);
  }
  .dots button.active {
    width: 42px;
  }
  .fill {
    position: absolute;
    inset: 0;
    background: var(--color-accent);
    transform-origin: left;
    animation: fill linear forwards;
  }
  .fill.paused {
    animation-play-state: paused;
  }
  @keyframes fill {
    from {
      transform: scaleX(0);
    }
    to {
      transform: scaleX(1);
    }
  }
  .scrim {
    position: absolute;
    inset: 0;
    background:
      linear-gradient(to top, var(--color-bg) 2%, transparent 55%),
      linear-gradient(to right, rgba(4, 18, 11, 0.9) 0%, rgba(4, 18, 11, 0.35) 45%, transparent 75%);
  }

  .content {
    position: absolute;
    left: 0;
    bottom: 8%;
    max-width: 640px;
    padding: 0 1.5rem;
  }
  @media (min-width: 1024px) {
    .content {
      padding: 0 3rem;
    }
  }

  .tag {
    display: inline-block;
    margin-bottom: 0.9rem;
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
    font-size: clamp(2.2rem, 6vw, 4.2rem);
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.03em;
    text-shadow: 0 4px 30px rgba(0, 0, 0, 0.5);
  }
  .meta {
    display: flex;
    gap: 0.9rem;
    margin: 1rem 0 0.8rem;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.75);
  }
  .meta span:not(:last-child)::after {
    content: '•';
    margin-left: 0.9rem;
    color: rgba(255, 255, 255, 0.35);
  }
  .overview {
    font-size: 0.95rem;
    line-height: 1.5;
    color: rgba(255, 255, 255, 0.82);
    max-width: 48ch;
    /* real Jellyfin overviews run long; keep the CTAs in view */
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 4;
    line-clamp: 4;
    overflow: hidden;
  }
  .cta {
    display: flex;
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
  .btn.primary:hover {
    filter: brightness(1.08);
  }
  .btn.ghost {
    color: #fff;
  }
  .btn.saved {
    color: var(--color-accent);
  }
  .btn.icon {
    padding: 0;
    width: 46px;
    justify-content: center;
    color: #fff;
  }
</style>
