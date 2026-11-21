<script>
  import '../app.css';
  import AuroraBackground from '$lib/components/AuroraBackground.svelte';
  import Header from '$lib/components/Header.svelte';

  let { data, children } = $props();
</script>

<AuroraBackground />
{#if data.user}
  <Header user={data.user} />

  <main>
    {@render children()}
  </main>

  <footer>
    <span class="font-display">MediaHub</span>
    <span>Your library · served from home</span>
  </footer>
{:else}
  <!-- signed out: just the login screen, no nav -->
  {@render children()}
{/if}

<style>
  main {
    min-height: 100vh;
  }
  footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 2.5rem 1.5rem;
    margin-top: 2rem;
    color: rgba(255, 255, 255, 0.4);
    font-size: 0.85rem;
    border-top: 0.8px solid rgba(255, 255, 255, 0.06);
  }
  @media (min-width: 1024px) {
    footer {
      padding-left: 3rem;
      padding-right: 3rem;
    }
  }
</style>
