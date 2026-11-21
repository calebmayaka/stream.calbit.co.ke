<!--
  Fixed ambient background: slow-drifting accent "aurora" blobs behind
  everything, plus a top vignette so the glass header reads cleanly.
-->
<div class="aurora" aria-hidden="true">
  <span class="blob blob-a"></span>
  <span class="blob blob-b"></span>
  <span class="blob blob-c"></span>
  <div class="vignette"></div>
  <div class="grain"></div>
</div>

<style>
  .aurora {
    position: fixed;
    inset: 0;
    z-index: -1;
    overflow: hidden;
    background: var(--color-bg);
  }

  /* No filter: blur() here. A 90px blur on half-screen blobs that also scale
     forced a full re-blur every frame and pegged CPU/GPU on weaker PCs. The
     radial gradients are soft on their own, and translate-only drift is a
     cheap GPU composite. */
  .blob {
    position: absolute;
    border-radius: 50%;
    opacity: 0.5;
  }

  .blob-a {
    top: -10%;
    left: -5%;
    width: 45vw;
    height: 45vw;
    background: radial-gradient(circle at 30% 30%, var(--color-accent), transparent 70%);
    opacity: 0.28;
    animation: drift-a 40s var(--ease-hover) infinite alternate;
  }
  .blob-b {
    top: 20%;
    right: -10%;
    width: 50vw;
    height: 50vw;
    background: radial-gradient(circle at 60% 40%, #1f7a4d, transparent 70%);
    opacity: 0.35;
    animation: drift-b 48s var(--ease-hover) infinite alternate;
  }
  .blob-c {
    bottom: -20%;
    left: 25%;
    width: 55vw;
    height: 55vw;
    background: radial-gradient(circle at 50% 50%, #0c4d2e, transparent 70%);
    opacity: 0.45;
    animation: drift-c 56s var(--ease-hover) infinite alternate;
  }

  .vignette {
    position: absolute;
    inset: 0;
    background:
      radial-gradient(120% 80% at 50% 0%, transparent 40%, rgba(0, 0, 0, 0.55) 100%),
      linear-gradient(to bottom, rgba(4, 18, 11, 0.6) 0%, transparent 30%);
  }

  .grain {
    position: absolute;
    inset: 0;
    opacity: 0.035;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  }

  @keyframes drift-a {
    to {
      transform: translate3d(8vw, 6vh, 0);
    }
  }
  @keyframes drift-b {
    to {
      transform: translate3d(-10vw, 4vh, 0);
    }
  }
  @keyframes drift-c {
    to {
      transform: translate3d(6vw, -8vh, 0);
    }
  }

  :global(body:has(.player)) .aurora {
    display: none;
  }

  @media (prefers-reduced-motion: reduce) {
    .blob {
      animation: none;
    }
  }
</style>
