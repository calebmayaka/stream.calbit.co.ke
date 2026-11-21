<script>
  import { ChevronLeft, ChevronRight } from 'lucide-svelte';
  import MediaCard from './MediaCard.svelte';

  /** @type {{ title: string, items: any[], href?: string|null }} */
  let { title, items, href = null } = $props();

  let track = $state(null);

  function scroll(dir) {
    if (!track) return;
    track.scrollBy({ left: dir * track.clientWidth * 0.8, behavior: 'smooth' });
  }
</script>

<section class="row">
  <div class="row-head">
    <h2 class="row-title font-display">
      {#if href}<a {href}>{title} <span class="see-all">See all <ChevronRight size={14} /></span></a>{:else}{title}{/if}
    </h2>
    <div class="arrows">
      <button aria-label="Scroll left" onclick={() => scroll(-1)}><ChevronLeft size={18} /></button>
      <button aria-label="Scroll right" onclick={() => scroll(1)}><ChevronRight size={18} /></button>
    </div>
  </div>

  <div class="track no-scrollbar" bind:this={track}>
    {#each items as item (item.id)}
      <MediaCard {item} />
    {/each}
  </div>
</section>

<style>
  .row {
    margin: 2.2rem 0;
  }
  .row-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 1.5rem 0.8rem;
  }
  @media (min-width: 1024px) {
    .row-head {
      padding-left: 3rem;
      padding-right: 3rem;
    }
  }
  .row-title {
    font-size: 1.15rem;
    font-weight: 700;
    color: #fff;
    letter-spacing: -0.01em;
  }
  .row-title a {
    display: inline-flex;
    align-items: baseline;
    gap: 0.6rem;
    color: inherit;
    text-decoration: none;
  }
  .see-all {
    display: inline-flex;
    align-items: center;
    font-family: var(--font-sans);
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--color-accent);
    opacity: 0;
    transform: translateX(-4px);
    transition: opacity 0.3s ease, transform 0.3s var(--ease-hover);
  }
  .row-title a:hover .see-all,
  .row-title a:focus-visible .see-all {
    opacity: 1;
    transform: none;
  }
  @media (hover: none) {
    .see-all {
      opacity: 1;
      transform: none;
    }
  }
  .arrows {
    display: flex;
    gap: 0.4rem;
  }
  .arrows button {
    display: grid;
    place-items: center;
    width: 34px;
    height: 34px;
    border-radius: 999px;
    border: 0.8px solid rgba(255, 255, 255, 0.1);
    background: rgba(255, 255, 255, 0.05);
    color: rgba(255, 255, 255, 0.8);
    cursor: pointer;
    transition: background 0.25s ease, color 0.25s ease, transform 0.25s var(--ease-hover);
  }
  .arrows button:hover {
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
    transform: scale(1.08);
  }

  .track {
    display: flex;
    gap: 0.9rem;
    overflow-x: auto;
    scroll-snap-type: x proximity;
    padding: 0.5rem 1.5rem 0.5rem;
  }
  @media (min-width: 1024px) {
    .track {
      padding-left: 3rem;
      padding-right: 3rem;
    }
  }
  .track > :global(.card) {
    scroll-snap-align: start;
  }
</style>
