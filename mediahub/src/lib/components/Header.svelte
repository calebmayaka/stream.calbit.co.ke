<script>
  import { page } from '$app/state';
  import { House, Clapperboard, Tv, Library, Bookmark, Search, LogOut } from 'lucide-svelte';
  import { signOut } from '$lib/data/api.js';
  import SearchOverlay from './SearchOverlay.svelte';

  /** @type {{ user: { username: string, name: string } }} */
  let { user } = $props();

  let menuOpen = $state(false);
  let menuEl = $state(null);

  async function logout() {
    await signOut().catch(() => {});
    location.assign('/login'); // full reload: drop every cached page/state
  }

  function onDocClick(e) {
    if (menuOpen && menuEl && !menuEl.contains(e.target)) menuOpen = false;
  }

  // Photos / Retro come back once there's a library for them (Jellyfin has none yet).
  const nav = [
    { id: 'home', href: '/', label: 'Home', icon: House },
    { id: 'movies', href: '/movies', label: 'Movies', icon: Clapperboard },
    { id: 'series', href: '/series', label: 'Series', icon: Tv },
    { id: 'collections', href: '/collections', label: 'Collections', icon: Library },
    { id: 'mylist', href: '/mylist', label: 'My List', icon: Bookmark }
  ];

  let scrolled = $state(false);
  let searchOpen = $state(false);

  // Highlight follows the URL; detail pages (/title, /person) highlight nothing.
  const active = $derived(nav.find((n) => (n.href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(n.href)))?.id ?? null);

  // Sliding white pill: measured from the active nav link.
  let itemEls = $state({});
  let pill = $state({ left: 0, width: 0, ready: false });

  function movePill() {
    const el = active && itemEls[active];
    pill = el ? { left: el.offsetLeft, width: el.offsetWidth, ready: true } : { left: 0, width: 0, ready: false };
  }

  $effect(() => {
    active; // re-run when the route changes
    movePill();
    document.fonts?.ready.then(movePill); // widths shift once the webfont loads
  });

  // Close search when navigating to a result.
  $effect(() => {
    page.url.pathname;
    searchOpen = false;
  });

  function onScroll() {
    scrolled = window.scrollY > 10;
  }

  function onKey(e) {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName ?? '');
    if ((e.key === '/' && !typing) || (e.key.toLowerCase() === 'k' && (e.ctrlKey || e.metaKey))) {
      e.preventDefault();
      searchOpen = true;
    }
  }
</script>

<svelte:window onscroll={onScroll} onresize={movePill} onkeydown={onKey} onclick={onDocClick} />

<header class="app-header" class:is-scrolled={scrolled}>
  <!-- Brand -->
  <a href="/" class="brand" aria-label="MediaHub home">
    <span class="logomark">
      <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path
          d="M4 5.5 12 2l8 3.5v13L12 22l-8-3.5z"
          stroke="var(--color-accent)"
          stroke-width="1.6"
          stroke-linejoin="round"
        />
        <path d="m9.5 8.5 5 3.5-5 3.5z" fill="var(--color-accent)" />
      </svg>
    </span>
    <span class="wordmark font-display">MediaHub</span>
  </a>

  <!-- Center pill nav -->
  <nav class="glass nav-pill" aria-label="Primary">
    {#if pill.ready}
      <span
        class="active-pill"
        style="transform: translateX({pill.left}px); width: {pill.width}px"
      ></span>
    {/if}
    {#each nav as item (item.id)}
      {@const Icon = item.icon}
      <a
        href={item.href}
        class="nav-item"
        class:active={active === item.id}
        aria-current={active === item.id ? 'page' : undefined}
        bind:this={itemEls[item.id]}
      >
        <Icon size={16} strokeWidth={2} />
        <span>{item.label}</span>
      </a>
    {/each}
  </nav>

  <!-- Right actions -->
  <div class="actions">
    <button class="icon-btn glass" aria-label="Search (press /)" title="Search  ( / )" onclick={() => (searchOpen = true)}>
      <Search size={18} />
    </button>
    <div class="account" bind:this={menuEl}>
      <button
        class="avatar"
        onclick={() => (menuOpen = !menuOpen)}
        aria-expanded={menuOpen}
        aria-haspopup="menu"
        aria-label={`Account: ${user.name}`}
      >
        {user.name[0].toUpperCase()}
      </button>
      {#if menuOpen}
        <div class="account-menu glass" role="menu">
          <p class="who">
            <span class="font-display">{user.name}</span>
            {#if user.name !== user.username}<span class="handle">@{user.username}</span>{/if}
          </p>
          <button role="menuitem" onclick={logout}><LogOut size={16} /> Sign out</button>
        </div>
      {/if}
    </div>
  </div>
</header>

<!-- Mobile/tablet: the center pill is hidden below 1024px, so the same nav
     lives in a glass tab bar pinned to the bottom (thumb reach). -->
<nav class="glass tab-bar" aria-label="Primary">
  {#each nav as item (item.id)}
    {@const Icon = item.icon}
    <a
      href={item.href}
      class="tab"
      class:active={active === item.id}
      aria-current={active === item.id ? 'page' : undefined}
    >
      <Icon size={20} strokeWidth={2} />
      <span>{item.label}</span>
    </a>
  {/each}
</nav>

{#if searchOpen}
  <SearchOverlay onclose={() => (searchOpen = false)} />
{/if}

<style>
  .app-header {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 50;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.75rem;
    padding: 1rem 1.5rem;
    transition: padding 0.3s var(--ease-condense);
  }
  @media (min-width: 1024px) {
    .app-header {
      padding: 0.75rem 3rem;
    }
  }
  .app-header.is-scrolled {
    padding-top: 0.6rem;
    padding-bottom: 0.6rem;
  }

  .brand {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    text-decoration: none;
    transition: transform var(--hover-time) var(--ease-hover);
  }
  .brand:hover {
    transform: scale(1.04);
  }
  .logomark {
    display: grid;
    place-items: center;
  }
  .wordmark {
    color: #fff;
    font-weight: 800;
    font-size: 1.15rem;
    letter-spacing: -0.02em;
  }

  .nav-pill {
    position: relative;
    display: none;
    align-items: center;
    gap: 2px;
    padding: var(--nav-pad);
    border-radius: 999px;
  }
  @media (min-width: 1024px) {
    .nav-pill {
      display: flex;
    }
  }

  .active-pill {
    position: absolute;
    top: var(--nav-pad);
    left: 0;
    height: var(--nav-item-h);
    background: #fff;
    border-radius: 999px;
    box-shadow:
      0 2px 8px rgba(0, 0, 0, 0.35),
      0 0 16px 1px rgba(255, 255, 255, 0.18);
    transition: transform var(--hover-time) var(--ease-spring),
      width var(--hover-time) var(--ease-spring);
    z-index: 0;
  }

  .nav-item {
    text-decoration: none;
    position: relative;
    z-index: 1;
    display: flex;
    align-items: center;
    gap: 0.4rem;
    height: var(--nav-item-h);
    padding: 0 1rem;
    border: 0;
    background: transparent;
    color: rgba(255, 255, 255, 0.6);
    font: inherit;
    font-size: 0.875rem;
    font-weight: 500;
    white-space: nowrap;
    border-radius: 999px;
    cursor: pointer;
    transition: color 0.3s ease;
  }
  .nav-item:hover {
    color: #fff;
  }
  .nav-item.active {
    color: #000;
  }

  .tab-bar {
    position: fixed;
    left: 0.75rem;
    right: 0.75rem;
    bottom: calc(0.75rem + env(safe-area-inset-bottom));
    z-index: 50;
    display: flex;
    justify-content: space-around;
    padding: 6px;
    border-radius: 22px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.45);
  }
  @media (min-width: 1024px) {
    .tab-bar {
      display: none;
    }
  }

  .tab {
    text-decoration: none;
    flex: 1 1 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 3px;
    min-width: 0;
    padding: 7px 4px 6px;
    border: 0;
    border-radius: 16px;
    background: transparent;
    color: rgba(255, 255, 255, 0.55);
    font: inherit;
    font-size: 0.68rem;
    font-weight: 500;
    cursor: pointer;
    transition: color 0.3s ease, background 0.3s var(--ease-hover);
  }
  .tab.active {
    color: var(--color-accent);
    background: rgba(149, 255, 80, 0.1);
  }

  .actions {
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .icon-btn {
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 999px;
    color: #fff;
    cursor: pointer;
    transition: transform var(--hover-time) var(--ease-hover);
  }
  .icon-btn:hover {
    transform: scale(1.08);
  }
  .account {
    position: relative;
  }
  .account-menu {
    position: absolute;
    top: calc(100% + 10px);
    right: 0;
    min-width: 200px;
    padding: 0.5rem;
    border-radius: 16px;
    background: rgba(10, 14, 12, 0.92);
    box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
  }
  .who {
    display: grid;
    padding: 0.5rem 0.7rem 0.6rem;
    border-bottom: 0.8px solid rgba(255, 255, 255, 0.08);
    margin-bottom: 0.35rem;
  }
  .who span:first-child {
    font-weight: 700;
  }
  .handle {
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.5);
  }
  .account-menu button {
    display: flex;
    align-items: center;
    gap: 0.55rem;
    width: 100%;
    padding: 0.6rem 0.7rem;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: #fff;
    font: inherit;
    font-size: 0.9rem;
    cursor: pointer;
  }
  .account-menu button:hover,
  .account-menu button:focus-visible {
    background: rgba(255, 255, 255, 0.08);
  }
  .avatar {
    border: 0;
    cursor: pointer;
    font-family: inherit;
    display: grid;
    place-items: center;
    width: 40px;
    height: 40px;
    border-radius: 999px;
    background: linear-gradient(135deg, var(--color-accent), var(--color-accent-dim));
    color: #04120b;
    font-weight: 700;
    font-size: 0.95rem;
  }
</style>
