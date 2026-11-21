<script>
  import { goto } from '$app/navigation';
  import { KeyRound, LoaderCircle } from 'lucide-svelte';
  import { resetPassword } from '$lib/data/api.js';

  let username = $state('');
  let key = $state('');
  let password = $state('');
  let confirm = $state('');
  let error = $state('');
  let busy = $state(false);

  const ready = $derived(username.trim() && key && password && password === confirm);

  async function submit(e) {
    e.preventDefault();
    if (busy || !ready) return;
    busy = true;
    error = '';
    try {
      await resetPassword({ username: username.trim(), key, password });
      key = password = confirm = '';
      await goto('/', { replaceState: true, invalidateAll: true }); // reset also signs you in
    } catch (err) {
      error = err.message || 'Reset failed.';
      key = '';
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head>
  <title>Reset password · MediaHub</title>
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

    <h1 class="font-display">Reset password</h1>
    <p class="lead">Enter the account name, the pass key, and a new password.</p>

    <label>
      <span>Account name</span>
      <!-- svelte-ignore a11y_autofocus -->
      <input bind:value={username} name="username" autocomplete="username" autocapitalize="none" spellcheck="false" required autofocus />
    </label>
    <label>
      <span>Pass key</span>
      <input bind:value={key} name="pass-key" type="password" autocomplete="off" required />
    </label>
    <label>
      <span>New password</span>
      <input bind:value={password} name="password" type="password" autocomplete="new-password" required />
    </label>
    <label>
      <span>Confirm new password</span>
      <input bind:value={confirm} name="confirm" type="password" autocomplete="new-password" required />
    </label>
    {#if confirm && confirm !== password}<p class="hint">Passwords don’t match yet.</p>{/if}
    <p class="hint">At least 10 characters; not a common password. You’ll be signed out on other devices.</p>

    {#if error}<p class="error" role="alert">{error}</p>{/if}

    <button class="submit" type="submit" disabled={busy || !ready}>
      {#if busy}<span class="spin"><LoaderCircle size={18} /></span> Resetting…{:else}<KeyRound size={18} /> Reset &amp; sign in{/if}
    </button>

    <p class="foot"><a href="/login">Back to sign in</a></p>
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
  .foot a {
    color: var(--color-accent);
    text-decoration: none;
  }
  .foot a:hover {
    text-decoration: underline;
  }
</style>
