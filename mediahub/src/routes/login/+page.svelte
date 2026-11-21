<script>
  import { goto } from '$app/navigation';
  import { LoaderCircle, LogIn } from 'lucide-svelte';
  import { signIn, setupFirstAccount } from '$lib/data/api.js';

  let { data } = $props();

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let busy = $state(false);
  // first-run setup (no accounts exist yet)
  let code = $state('');
  let name = $state('');
  let confirm = $state('');

  const setup = $derived(data.setup);
  const ready = $derived(
    setup ? code.trim() && username.trim() && password && password === confirm : username.trim() && password
  );

  async function submit(e) {
    e.preventDefault();
    if (busy || !ready) return;
    busy = true;
    error = '';
    const target = data.next; // read before navigating: data changes with the URL
    try {
      if (setup) {
        await setupFirstAccount({ code: code.trim().toUpperCase(), username: username.trim(), name: name.trim(), password });
        confirm = '';
      } else {
        await signIn(username.trim(), password);
      }
      password = '';
      // invalidateAll re-runs the layout gate with the new session
      await goto(target, { replaceState: true, invalidateAll: true });
    } catch (err) {
      error = err.message || 'Sign-in failed.';
      password = '';
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Sign in · MediaHub</title>
</svelte:head>

<div class="wrap">
  <form class="card glass" onsubmit={submit} novalidate>
    <div class="brand">
      <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4 5.5 12 2l8 3.5v13L12 22l-8-3.5z" stroke="var(--color-accent)" stroke-width="1.6" stroke-linejoin="round" />
        <path d="m9.5 8.5 5 3.5-5 3.5z" fill="var(--color-accent)" />
      </svg>
      <span class="font-display">MediaHub</span>
    </div>

    {#if setup}
      <h1 class="font-display">Create the first account</h1>
      <p class="lead">No one has an account yet. Enter the setup code from the server, then choose your login.</p>

      <label>
        <span>Setup code</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input bind:value={code} name="setup-code" autocomplete="one-time-code" autocapitalize="characters" spellcheck="false" placeholder="XXXX-XXXX-XXXX" required autofocus />
      </label>
      <label>
        <span>Your name</span>
        <input bind:value={name} name="name" autocomplete="name" placeholder="Caleb" />
      </label>
    {:else}
      <h1 class="font-display">Welcome back</h1>
      <p class="lead">Sign in to watch your library.</p>
    {/if}

    <label>
      <span>Username</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={username} name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus={!setup} />
    </label>
    <label>
      <span>Password</span>
      <input bind:value={password} name="password" type="password" autocomplete={setup ? 'new-password' : 'current-password'} required />
    </label>
    {#if setup}
      <label>
        <span>Confirm password</span>
        <input bind:value={confirm} name="confirm" type="password" autocomplete="new-password" required />
      </label>
      {#if confirm && confirm !== password}<p class="hint">Passwords don’t match yet.</p>{/if}
      <p class="hint">At least 10 characters; not a common password.</p>
    {/if}

    {#if error}<p class="error" role="alert">{error}</p>{/if}

    <button class="submit" type="submit" disabled={busy || !ready}>
      {#if busy}<span class="spin"><LoaderCircle size={18} /></span> {setup ? 'Creating…' : 'Signing in…'}
      {:else}<LogIn size={18} /> {setup ? 'Create account & sign in' : 'Sign in'}{/if}
    </button>

    {#if !setup}<p class="foot">Need an account? Ask Caleb.</p>{/if}
  </form>
</div>

<style>
  .wrap {
    display: grid;
    place-items: center;
    min-height: 100vh;
    min-height: 100dvh;
    padding: 1.5rem 1rem;
  }
  .card {
    display: grid;
    gap: 1rem;
    width: min(400px, 100%);
    padding: 2rem 1.75rem 1.6rem;
    border-radius: 24px;
    box-shadow: 0 40px 80px -20px rgba(0, 0, 0, 0.7);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-size: 1.25rem;
    font-weight: 800;
  }
  h1 {
    margin-top: 0.6rem;
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
  .lead {
    margin-top: -0.6rem;
    color: rgba(255, 255, 255, 0.6);
    font-size: 0.92rem;
  }
  label {
    display: grid;
    gap: 0.4rem;
  }
  label span {
    font-size: 0.8rem;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.75);
  }
  input {
    height: 48px;
    padding: 0 1rem;
    border-radius: 14px;
    border: 0.8px solid rgba(255, 255, 255, 0.14);
    background: rgba(0, 0, 0, 0.3);
    color: #fff;
    font: inherit;
    font-size: 1rem;
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }
  input:focus {
    border-color: rgba(149, 255, 80, 0.6);
    box-shadow: 0 0 0 3px rgba(149, 255, 80, 0.15);
  }
  .hint {
    margin-top: -0.4rem;
    font-size: 0.78rem;
    color: rgba(255, 255, 255, 0.5);
  }
  .error {
    padding: 0.65rem 0.9rem;
    border-radius: 12px;
    background: rgba(255, 90, 90, 0.12);
    border: 0.8px solid rgba(255, 90, 90, 0.4);
    color: #ffb4b4;
    font-size: 0.88rem;
  }
  .submit {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    height: 50px;
    margin-top: 0.3rem;
    border: 0;
    border-radius: 999px;
    background: var(--color-accent);
    color: #04120b;
    font: inherit;
    font-weight: 700;
    font-size: 1rem;
    cursor: pointer;
    transition: filter 0.2s ease, transform 0.3s var(--ease-hover);
  }
  .submit:hover:not(:disabled) {
    filter: brightness(1.08);
    transform: scale(1.02);
  }
  .submit:disabled {
    opacity: 0.55;
    cursor: not-allowed;
  }
  .spin {
    display: inline-flex;
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .foot {
    text-align: center;
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.45);
  }
</style>
