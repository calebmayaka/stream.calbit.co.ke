<script>
  import { getHome } from '$lib/data/api.js';
  import HeroBanner from '$lib/components/HeroBanner.svelte';
  import MediaRow from '$lib/components/MediaRow.svelte';

  const home = getHome();
</script>

<svelte:head>
  <title>MediaHub</title>
</svelte:head>

{#await home then data}
  {#if data.heroes.length}<HeroBanner items={data.heroes} />{/if}
  <div class="rows" class:no-hero={!data.heroes.length}>
    {#each data.rows as row (row.title)}
      <MediaRow title={row.title} items={row.items} href={row.href} />
    {/each}
  </div>
{:catch}
  <div class="state">
    <p class="font-display">Can’t reach your media server</p>
    <span>The MediaHub API didn’t respond. Check that it’s running, then refresh.</span>
  </div>
{/await}

<style>
  .rows {
    position: relative;
    margin-top: -6vh; /* rows ride up over the hero fade, like Cinejoy */
    padding-bottom: 2rem;
  }
  .rows.no-hero {
    margin-top: 0;
    padding-top: 6rem;
  }
  .state {
    display: grid;
    place-content: center;
    gap: 0.5rem;
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
</style>
