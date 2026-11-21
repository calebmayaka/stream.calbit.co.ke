<script>
  import MediaCard from '$lib/components/MediaCard.svelte';

  let data = $state(null);
  let error = $state(null);
  let expanded = $state(false);

  // From +page.js; the fetch starts on hover/touch, before the click.
  let { data: route } = $props();

  $effect(() => {
    const personId = route.id;
    data = null;
    error = null;
    expanded = false;
    route.person
      .then((d) => personId === route.id && (data = d))
      .catch((e) => personId === route.id && (error = e.message));
  });

  function age(born) {
    const b = new Date(born);
    const now = new Date();
    let years = now.getFullYear() - b.getFullYear();
    if (now < new Date(now.getFullYear(), b.getMonth(), b.getDate())) years--;
    return years;
  }
</script>

<svelte:head>
  <title>{data ? `${data.name} · MediaHub` : 'MediaHub'}</title>
</svelte:head>

{#if error}
  <div class="state">
    <p class="font-display">Couldn’t load this person</p>
    <span>{error}</span>
  </div>
{:else if data}
  <section class="head">
    <div class="photo">
      {#if data.image}<img src={data.image} alt="" />{:else}<span>{data.name[0]}</span>{/if}
    </div>
    <div class="info">
      <span class="kind">Cast</span>
      <h1 class="font-display">{data.name}</h1>
      {#if data.born || data.birthplace}
        <p class="facts">
          {#if data.born}Born {new Date(data.born).toLocaleDateString(undefined, { dateStyle: 'long', timeZone: 'UTC' })} ({age(data.born)}){/if}
          {#if data.born && data.birthplace} · {/if}
          {#if data.birthplace}{data.birthplace}{/if}
        </p>
      {/if}
      {#if data.overview}
        <p class="bio" class:expanded>{data.overview}</p>
        {#if data.overview.length > 420}
          <button class="more" onclick={() => (expanded = !expanded)}>{expanded ? 'Less' : 'Read more'}</button>
        {/if}
      {/if}
    </div>
  </section>

  <section class="block">
    <h2 class="font-display">In your library <span>{data.items.length}</span></h2>
    {#if data.items.length}
      <div class="grid">
        {#each data.items as item (item.id)}<MediaCard {item} fluid />{/each}
      </div>
    {:else}
      <p class="empty">Nothing with {data.name} in your library yet.</p>
    {/if}
  </section>
{:else}
  <div class="skeleton" aria-busy="true"></div>
{/if}

<style>
  .head {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: 2rem;
    padding: 7.5rem 1.5rem 1.5rem;
  }
  @media (min-width: 1024px) {
    .head {
      padding: 8.5rem 3rem 2rem;
    }
  }
  .photo {
    display: grid;
    place-items: center;
    width: 180px;
    aspect-ratio: 2 / 3;
    flex: 0 0 auto;
    border-radius: 16px;
    overflow: hidden;
    background: rgba(255, 255, 255, 0.06);
    box-shadow: 0 30px 50px -10px rgba(0, 0, 0, 0.7), 0 0 0 1px rgba(255, 255, 255, 0.08);
    font-size: 3rem;
    font-weight: 800;
    color: rgba(255, 255, 255, 0.4);
  }
  .photo img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  .info {
    flex: 1 1 320px;
    max-width: 760px;
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
  h1 {
    font-size: clamp(2rem, 5vw, 3.4rem);
    font-weight: 800;
    line-height: 1.05;
    letter-spacing: -0.03em;
  }
  .facts {
    margin-top: 0.6rem;
    color: rgba(255, 255, 255, 0.7);
    font-size: 0.9rem;
  }
  .bio {
    margin-top: 1rem;
    line-height: 1.6;
    color: rgba(255, 255, 255, 0.82);
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 5;
    line-clamp: 5;
    overflow: hidden;
  }
  .bio.expanded {
    display: block;
  }
  .more {
    margin-top: 0.4rem;
    padding: 0;
    border: 0;
    background: none;
    color: var(--color-accent);
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
  .block {
    padding: 1rem 1.5rem 2rem;
  }
  @media (min-width: 1024px) {
    .block {
      padding: 1rem 3rem 2rem;
    }
  }
  h2 {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 1rem;
    font-size: 1.2rem;
    font-weight: 700;
  }
  h2 span {
    font-size: 0.8rem;
    padding: 1px 9px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.7);
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
  .empty {
    color: rgba(255, 255, 255, 0.6);
  }
  .skeleton {
    height: 60vh;
  }
  .state {
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 0.6rem;
    min-height: 70vh;
    text-align: center;
    color: rgba(255, 255, 255, 0.6);
  }
  .state p {
    color: #fff;
    font-size: 1.3rem;
    font-weight: 700;
  }
</style>
