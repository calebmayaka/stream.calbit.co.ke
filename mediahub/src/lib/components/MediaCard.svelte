<script>
  import { Play, Star, Check } from 'lucide-svelte';

  /** @type {{ item: { id: string, title: string, href?: string, year?: string|number, rating?: number, badge?: string, poster: string, kind?: string, progress?: number, played?: boolean }, fluid?: boolean }} */
  let { item, fluid = false } = $props();
</script>

<a class="card group" class:fluid href={item.href ?? `/title/${item.id}`} aria-label={item.title}>
  <div class="poster">
    <img src={item.poster} alt={item.title} loading="lazy" draggable="false" />

    <!-- base gradients (match Cinejoy: dark from top + right) -->
    <span class="veil veil-base"></span>
    <!-- hover sheen -->
    <span class="veil veil-hover"></span>

    {#if item.badge}
      <span class="badge">{item.badge}</span>
    {/if}
    {#if item.played}
      <span class="watched" title="Watched"><Check size={13} strokeWidth={3} /></span>
    {/if}
    {#if item.progress}
      <span class="progress" aria-label={`${Math.round(item.progress)}% watched`}><span style="width: {item.progress}%"></span></span>
    {/if}

    <!-- hover content -->
    <div class="overlay">
      <span class="play"><Play size={18} fill="#04120b" stroke="#04120b" /></span>
      <div class="meta">
        <p class="title">{item.title}</p>
        <p class="sub">
          {#if item.rating}
            <span class="rating"><Star size={12} fill="var(--color-accent)" stroke="var(--color-accent)" />{item.rating}</span>
          {/if}
          {#if item.year}<span>{item.year}</span>{/if}
          {#if item.kind}<span class="kind">{item.kind}</span>{/if}
        </p>
      </div>
    </div>
  </div>
</a>

<style>
  .card {
    display: block;
    text-decoration: none;
    flex: 0 0 auto;
    width: 160px;
  }
  @media (min-width: 768px) {
    .card {
      width: 190px;
    }
  }
  .card.fluid {
    width: 100%;
  }
  .card:focus-visible {
    outline: none;
  }
  .card:focus-visible .poster {
    box-shadow: 0 0 0 2px var(--color-accent), 0 20px 25px -5px rgba(0, 0, 0, 0.4);
  }
  .card:focus-visible .overlay,
  .card:focus-visible .play {
    opacity: 1;
  }

  .watched {
    position: absolute;
    top: 8px;
    right: 8px;
    display: grid;
    place-items: center;
    width: 22px;
    height: 22px;
    border-radius: 999px;
    background: rgba(4, 18, 11, 0.75);
    color: var(--color-accent);
    border: 0.8px solid rgba(149, 255, 80, 0.5);
  }
  .progress {
    position: absolute;
    left: 8px;
    right: 8px;
    bottom: 8px;
    height: 4px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.25);
    overflow: hidden;
    z-index: 1;
  }
  .progress span {
    display: block;
    height: 100%;
    background: var(--color-accent);
  }

  .poster {
    position: relative;
    aspect-ratio: 2 / 3;
    border-radius: 12px;
    overflow: hidden;
    background: var(--color-bg-soft);
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.4);
    transform: scale(1);
    transition: transform var(--hover-time) var(--ease-hover),
      box-shadow var(--hover-time) var(--ease-hover);
  }
  .card:hover .poster {
    transform: scale(1.08);
    box-shadow: 0 30px 40px -8px rgba(0, 0, 0, 0.55), 0 0 0 1px rgba(255, 255, 255, 0.08);
  }

  img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    display: block;
  }

  .veil {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }
  .veil-base {
    background:
      linear-gradient(to top, rgba(0, 0, 0, 0.4) 0%, transparent 45%),
      linear-gradient(to right, rgba(0, 0, 0, 0.3) 0%, transparent 50%);
  }
  .veil-hover {
    background: linear-gradient(135deg, rgba(255, 255, 255, 0.1), transparent 60%);
    opacity: 0;
    transition: opacity var(--hover-time) var(--ease-hover);
  }
  .card:hover .veil-hover {
    opacity: 1;
  }

  .badge {
    position: absolute;
    top: 8px;
    left: 8px;
    padding: 2px 8px;
    border-radius: 999px;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    background: rgba(149, 255, 80, 0.92);
    color: #04120b;
  }

  .overlay {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 0.7rem;
    opacity: 0;
    transform: translateY(6px);
    transition: opacity var(--hover-time) var(--ease-hover),
      transform var(--hover-time) var(--ease-hover);
  }
  .card:hover .overlay {
    opacity: 1;
    transform: translateY(0);
  }

  .play {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%) scale(0.8);
    display: grid;
    place-items: center;
    width: 46px;
    height: 46px;
    border-radius: 999px;
    background: var(--color-accent);
    opacity: 0;
    transition: opacity var(--hover-time) var(--ease-hover),
      transform var(--hover-time) var(--ease-spring);
  }
  .card:hover .play {
    opacity: 1;
    transform: translate(-50%, -50%) scale(1);
  }

  .title {
    font-weight: 600;
    font-size: 0.85rem;
    line-height: 1.2;
    color: #fff;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sub {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 2px;
    font-size: 0.72rem;
    color: rgba(255, 255, 255, 0.7);
  }
  .rating {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    color: var(--color-accent);
    font-weight: 600;
  }
  .kind {
    margin-left: auto;
    padding: 1px 6px;
    border-radius: 6px;
    background: rgba(255, 255, 255, 0.12);
    text-transform: capitalize;
  }
</style>
