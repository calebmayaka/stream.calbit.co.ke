<!--
  Trailer overlay. Jellyfin only stores YouTube links for trailers, so this is
  the one place the app embeds a third party — youtube-nocookie, and only once
  someone presses "Trailer".
-->
<script>
  import { X } from 'lucide-svelte';

  /** @type {{ trailers: { name: string, youtubeId: string }[], onclose: () => void }} */
  let { trailers, onclose } = $props();

  let current = $state(0);
  const trailer = $derived(trailers[current]);

  function onKey(e) {
    if (e.key === 'Escape') onclose();
  }
</script>

<svelte:window onkeydown={onKey} />

<div class="backdrop" role="presentation" onclick={onclose}>
  <div
    class="dialog"
    role="dialog"
    aria-modal="true"
    aria-label={trailer.name}
    tabindex="-1"
    onclick={(e) => e.stopPropagation()}
    onkeydown={() => {}}
  >
    <div class="head">
      {#if trailers.length > 1}
        <div class="tabs">
          {#each trailers as t, i (t.youtubeId)}
            <button class:active={i === current} onclick={() => (current = i)}>{t.name}</button>
          {/each}
        </div>
      {:else}
        <p>{trailer.name}</p>
      {/if}
      <button class="close" onclick={onclose} aria-label="Close trailer"><X size={20} /></button>
    </div>
    <div class="frame">
      {#key trailer.youtubeId}
        <iframe
          src={`https://www.youtube-nocookie.com/embed/${trailer.youtubeId}?autoplay=1&rel=0&modestbranding=1`}
          title={trailer.name}
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
          allowfullscreen
          referrerpolicy="strict-origin-when-cross-origin"
        ></iframe>
      {/key}
    </div>
  </div>
</div>

<style>
  .backdrop {
    position: fixed;
    inset: 0;
    z-index: 90;
    display: grid;
    place-items: center;
    padding: 1rem;
    background: rgba(0, 0, 0, 0.78);
    backdrop-filter: blur(6px);
  }
  .dialog {
    width: min(1100px, 100%);
    outline: none;
  }
  .head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 0.7rem;
  }
  .head p {
    font-weight: 600;
  }
  .tabs {
    display: flex;
    gap: 4px;
    overflow-x: auto;
  }
  .tabs button {
    flex: 0 0 auto;
    height: 32px;
    padding: 0 0.9rem;
    border: 0;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: rgba(255, 255, 255, 0.75);
    font: inherit;
    font-size: 0.82rem;
    cursor: pointer;
  }
  .tabs button.active {
    background: #fff;
    color: #000;
  }
  .close {
    display: grid;
    place-items: center;
    flex: 0 0 auto;
    width: 38px;
    height: 38px;
    border: 0;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
    cursor: pointer;
  }
  .frame {
    position: relative;
    aspect-ratio: 16 / 9;
    border-radius: 14px;
    overflow: hidden;
    background: #000;
    box-shadow: 0 30px 60px rgba(0, 0, 0, 0.6);
  }
  iframe {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    border: 0;
  }
</style>
