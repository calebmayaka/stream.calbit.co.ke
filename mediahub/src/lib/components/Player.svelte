<!--
  Full-screen video overlay. Django brokers the stream (limited-user token);
  the <video> then pulls straight from Jellyfin — HLS via hls.js, or the
  native player where HLS is built in (Safari/iOS), or a plain MP4 file.
  Progress is reported back every 15s, on pause and on close.

  Extras: audio-track + subtitle menu, "Skip intro/recap" when the server has
  segment markers, and an "Up next" countdown at the end of an episode.
-->
<script>
  import { onMount } from 'svelte';
  import { ArrowLeft, LoaderCircle, SlidersHorizontal, Check, Play, X } from 'lucide-svelte';
  import { startPlayback, saveProgress, stopPlayback, reportPlaybackStats } from '$lib/data/api.js';
  import { createAutoplay } from '$lib/playback/autoplay.js';
  import { detectCapabilities, clientLabel } from '$lib/playback/capabilities.js';

  /** @type {{ itemId: string, title: string, subtitle?: string|null, startSeconds?: number, onclose: () => void, onnext?: (next: { id: string, label: string }) => void }} */
  let { itemId, title, subtitle = null, startSeconds = 0, onclose, onnext } = $props();

  const REPORT_EVERY = 15_000;
  const NEXT_CARD_AT = 25; // seconds before the end
  const COUNTDOWN = 10;

  let video = $state(null);
  let error = $state(null);
  let loading = $state(true);
  /** @type {any} */
  let session = $state(null);
  let now = $state(0);
  let menuOpen = $state(false);
  let subIndex = $state(null); // Jellyfin stream index of the showing subtitle, or null
  let nextDismissed = $state(false);
  let countdown = $state(COUNTDOWN);
  let autoplay = $state(null);

  // Quality menu. "auto" lets the server cap remote streams to share the home
  // upload; the choice is remembered per browser.
  const QUALITY_KEY = 'mediahub-quality';
  const QUALITIES = [
    { id: 'auto', label: 'Auto' },
    { id: 'original', label: 'Original' },
    { id: '720p', label: '720p · 3 Mbps' },
    { id: '480p', label: '480p · 1.5 Mbps' }
  ];
  const METHOD_LABEL = {
    direct: 'Playing the original file',
    remux: 'Original video, repackaged (no conversion)',
    transcode: 'Converted on the server'
  };
  let quality = $state(readQuality());

  function readQuality() {
    try {
      const saved = localStorage.getItem(QUALITY_KEY);
      return QUALITIES.some((q) => q.id === saved) ? saved : 'auto';
    } catch {
      return 'auto';
    }
  }

  let hls = null;
  let lastReport = 0;
  let cancelled = false;
  // Some browsers claim HEVC/AV1 support but can't decode a given file. If the
  // original (copied) stream fails, retry once with H.264 conversion.
  let forceH264 = false;

  function fallbackToH264() {
    if (forceH264 || !session || session.method === 'transcode') return false;
    if (!['hevc', 'av1'].includes(session.sourceVideo?.codec)) return false;
    forceH264 = true;
    load(video?.currentTime || startSeconds, { audioIndex: session.audioIndex ?? null });
    return true;
  }

  // Playback measurements, sent once when the player closes (manage.py playbackstats).
  const stats = { loadAt: 0, startupMs: 0, started: false, stalls: 0, stallMs: 0, stallAt: 0, seeking: false, watched: 0, lastTime: 0, sent: false };

  function onPlaying() {
    const t = performance.now();
    if (!stats.started) {
      stats.started = true;
      stats.startupMs = Math.round(t - stats.loadAt);
    } else if (stats.stallAt) {
      stats.stallMs += Math.round(t - stats.stallAt);
    }
    stats.stallAt = 0;
    stats.seeking = false;
  }

  function onWaiting() {
    // Buffering after the picture started, not caused by the viewer seeking.
    if (stats.started && !stats.seeking && !stats.stallAt) {
      stats.stalls += 1;
      stats.stallAt = performance.now();
    }
  }

  function sendStats() {
    if (stats.sent || !session) return;
    stats.sent = true;
    if (stats.stallAt) stats.stallMs += Math.round(performance.now() - stats.stallAt);
    reportPlaybackStats(itemId, {
      method: session.method,
      codec: session.sourceVideo?.codec ?? '',
      quality: session.quality,
      maxBitrate: session.maxBitrate ?? 0,
      startupMs: Math.min(stats.startupMs, 600_000),
      stalls: stats.stalls,
      stallMs: Math.min(stats.stallMs, 86_400_000),
      watchedSeconds: Math.min(Math.round(stats.watched), 86_400),
      client: clientLabel()
    });
  }

  const total = $derived(Number.isFinite(video?.duration) && video.duration > 0 ? video.duration : (session?.duration ?? 0));
  const segment = $derived(
    session?.segments.find((s) => (s.kind === 'intro' || s.kind === 'recap') && now >= s.start && now < s.end - 1)
  );
  const creditsStart = $derived(session?.segments.find((s) => s.kind === 'credits')?.start ?? null);
  const showNext = $derived(
    !!session?.next &&
      !!onnext &&
      !nextDismissed &&
      total > 0 &&
      (now >= total - NEXT_CARD_AT || (creditsStart !== null && now >= creditsStart))
  );

  function report(opts) {
    if (!session || !video || video.currentTime < 1) return;
    lastReport = Date.now();
    saveProgress(itemId, video.currentTime, total, opts).catch(() => {});
  }

  function onTimeUpdate() {
    now = video.currentTime;
    // Count actually-played time (small forward steps), not seeks.
    const step = now - stats.lastTime;
    if (!video.paused && step > 0 && step < 2) stats.watched += step;
    stats.lastTime = now;
    if (Date.now() - lastReport > REPORT_EVERY) report();
  }

  function close() {
    autoplay?.destroy();
    report({ keepalive: true });
    sendStats();
    onclose();
  }

  function goNext() {
    if (session?.next && onnext) autoplay?.advance();
  }

  function onKey(e) {
    if (e.key === 'Escape') {
      if (menuOpen) menuOpen = false;
      else close();
    }
  }

  function teardown() {
    hls?.destroy();
    hls = null;
    if (video) {
      video.removeAttribute('src');
      video.load();
    }
    if (session?.playSessionId) stopPlayback(session.playSessionId);
  }

  /** (Re)start the stream — on open, and when the audio track or quality changes. */
  async function load(at, { audioIndex = null, repickSubs = false } = {}) {
    loading = true;
    error = null;
    if (!stats.started) stats.loadAt = performance.now();
    try {
      const fresh = await startPlayback(itemId, at, audioIndex, { caps: forceH264 ? {} : detectCapabilities(), quality });
      if (cancelled) return stopPlayback(fresh.playSessionId);
      teardown();
      session = fresh;
      stats.lastTime = at;
      // New audio language -> re-pick subtitles (e.g. Japanese audio turns English subs on).
      if (repickSubs || !fresh.subtitles.some((s) => s.index === subIndex)) {
        subIndex = fresh.subtitles.find((s) => s.default)?.index ?? null;
      }

      if (fresh.type === 'hls' && !video.canPlayType('application/vnd.apple.mpegurl')) {
        const { default: Hls } = await import('hls.js');
        if (cancelled) return;
        if (!Hls.isSupported()) throw new Error('This browser can’t play HLS video.');
        hls = new Hls({ startPosition: at || -1 });
        hls.on(Hls.Events.ERROR, (_e, data) => {
          if (!data.fatal) return;
          const decodeProblem = data.type === Hls.ErrorTypes.MEDIA_ERROR || /codec|parsing|buffer/i.test(data.details);
          if (decodeProblem && fallbackToH264()) return;
          error = `Playback failed (${data.details}).`;
        });
        hls.loadSource(fresh.url);
        hls.attachMedia(video);
      } else {
        // Native HLS (Safari) or a direct MP4 file.
        video.addEventListener('loadedmetadata', () => at > 0 && (video.currentTime = at), { once: true });
        video.src = fresh.url;
      }
      await video.play().catch(() => {}); // autoplay may need a click; controls are there
    } catch (e) {
      error = e.message || 'Playback failed.';
    } finally {
      loading = false;
    }
  }

  function chooseAudio(index) {
    menuOpen = false;
    if (index === session?.audioIndex) return;
    report();
    load(video.currentTime, { audioIndex: index, repickSubs: true });
  }

  function chooseQuality(id) {
    menuOpen = false;
    if (id === quality) return;
    quality = id;
    try {
      localStorage.setItem(QUALITY_KEY, id);
    } catch {
      /* remembered for this session only */
    }
    report();
    load(video.currentTime, { audioIndex: session?.audioIndex ?? null });
  }

  function mbps(bits) {
    return bits >= 1_000_000 ? `${Math.round(bits / 1_000_000)} Mbps` : `${Math.round(bits / 1000)} kbps`;
  }

  // Show exactly the chosen subtitle track (tracks render in session.subtitles order).
  $effect(() => {
    const subs = session?.subtitles ?? [];
    const want = subIndex;
    if (!video) return;
    const apply = () => {
      for (let i = 0; i < video.textTracks.length; i++) {
        video.textTracks[i].mode = subs[i] && subs[i].index === want ? 'showing' : 'disabled';
      }
    };
    apply();
    video.textTracks.addEventListener('addtrack', apply);
    return () => video.textTracks.removeEventListener('addtrack', apply);
  });

  // Media events control the timer, including pause/buffer/seek transitions.
  $effect(() => {
    autoplay?.setEnabled(showNext && !loading && !error);
  });

  onMount(() => {
    autoplay = createAutoplay(video, {
      seconds: COUNTDOWN,
      onTick: (value) => (countdown = value),
      onNext: () => {
        report({ keepalive: true });
        onnext?.(session.next);
      }
    });
    load(startSeconds);
    const onHide = () => {
      report({ keepalive: true });
      sendStats();
    };
    window.addEventListener('pagehide', onHide);
    return () => {
      cancelled = true;
      autoplay.destroy();
      window.removeEventListener('pagehide', onHide);
      sendStats(); // also covers "next episode" swapping this player out
      teardown();
    };
  });
</script>

<svelte:window onkeydown={onKey} />

<div class="player" role="dialog" aria-modal="true" aria-label={`Playing ${title}`}>
  <video
    bind:this={video}
    controls
    playsinline
    ontimeupdate={onTimeUpdate}
    onplaying={onPlaying}
    onwaiting={onWaiting}
    onseeking={() => (stats.seeking = true)}
    onerror={() => {
      // Native players (Safari) report decode failures here.
      if (video?.error?.code === 3 || video?.error?.code === 4) fallbackToH264();
    }}
    onpause={() => report()}
    onended={() => {
      report();
      if (session?.next && onnext && !nextDismissed) goNext();
    }}
  >
    {#each session?.subtitles ?? [] as track (track.url)}
      <track kind="subtitles" src={track.url} label={track.label} srclang={track.lang} />
    {/each}
  </video>

  <div class="top">
    <button class="back glass" onclick={close} aria-label="Close player"><ArrowLeft size={20} /></button>
    <div class="label">
      <p class="font-display">{title}</p>
      {#if subtitle}<span>{subtitle}</span>{/if}
    </div>
    {#if session}
      <button
        class="tracks glass"
        onclick={() => (menuOpen = !menuOpen)}
        aria-expanded={menuOpen}
        aria-label="Quality, audio and subtitles"
      >
        <SlidersHorizontal size={20} />
      </button>
    {/if}
  </div>

  {#if menuOpen && session}
    <div class="menu glass" role="menu">
      <p class="menu-title">Quality</p>
      {#each QUALITIES as q (q.id)}
        <button role="menuitemradio" aria-checked={q.id === quality} onclick={() => chooseQuality(q.id)}>
          <span class="tick">{#if q.id === quality}<Check size={15} />{/if}</span>{q.label}
          {#if q.id === 'auto' && quality === 'auto' && session.maxBitrate}
            <span class="aside">up to {mbps(session.maxBitrate)}</span>
          {/if}
        </button>
      {/each}
      <p class="method" class:converting={session.method === 'transcode'}>{METHOD_LABEL[session.method] ?? ''}</p>
      {#if session.audioTracks.length > 1}
        <p class="menu-title">Audio</p>
        {#each session.audioTracks as a (a.index)}
          <button role="menuitemradio" aria-checked={a.index === session.audioIndex} onclick={() => chooseAudio(a.index)}>
            <span class="tick">{#if a.index === session.audioIndex}<Check size={15} />{/if}</span>{a.label}
          </button>
        {/each}
      {/if}
      {#if session.subtitles.length}
        <p class="menu-title">Subtitles</p>
        <button role="menuitemradio" aria-checked={subIndex === null} onclick={() => ((subIndex = null), (menuOpen = false))}>
          <span class="tick">{#if subIndex === null}<Check size={15} />{/if}</span>Off
        </button>
        {#each session.subtitles as s (s.index)}
          <button role="menuitemradio" aria-checked={s.index === subIndex} onclick={() => ((subIndex = s.index), (menuOpen = false))}>
            <span class="tick">{#if s.index === subIndex}<Check size={15} />{/if}</span>{s.label}
          </button>
        {/each}
      {/if}
    </div>
  {/if}

  {#if segment}
    <button class="skip glass" onclick={() => (video.currentTime = segment.end)}>
      Skip {segment.kind}
    </button>
  {/if}

  {#if showNext}
    <div class="next glass" role="status">
      {#if session.next.thumb}<img src={session.next.thumb} alt="" />{/if}
      <div class="next-text">
        <span>Next episode in {countdown}s</span>
        <p>{session.next.label || session.next.title}</p>
        <div class="next-actions">
          <button class="btn" onclick={goNext}><Play size={15} fill="#04120b" stroke="#04120b" /> Play now</button>
          <button class="btn ghost" onclick={() => (nextDismissed = true)} aria-label="Cancel autoplay"><X size={16} /></button>
        </div>
      </div>
    </div>
  {/if}

  {#if loading && !error}
    <div class="center"><span class="spin"><LoaderCircle size={36} /></span></div>
  {/if}
  {#if error}
    <div class="center">
      <p class="err">{error}</p>
      <button class="btn" onclick={close}>Back</button>
    </div>
  {/if}
</div>

<style>
  .player {
    position: fixed;
    inset: 0;
    z-index: 100;
    background: #000;
  }
  video {
    width: 100%;
    height: 100%;
    background: #000;
  }
  .top {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    display: flex;
    align-items: center;
    gap: 0.8rem;
    padding: 1rem 1.25rem;
    background: linear-gradient(to bottom, rgba(0, 0, 0, 0.7), transparent);
    pointer-events: none;
  }
  .back {
    pointer-events: auto;
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    border-radius: 999px;
    color: #fff;
    cursor: pointer;
  }
  .tracks {
    pointer-events: auto;
    margin-left: auto;
    display: grid;
    place-items: center;
    width: 42px;
    height: 42px;
    border-radius: 999px;
    color: #fff;
    cursor: pointer;
  }
  .menu {
    position: absolute;
    top: 4.2rem;
    right: 1.25rem;
    z-index: 2;
    width: min(300px, calc(100vw - 2.5rem));
    max-height: calc(100vh - 9rem);
    overflow-y: auto;
    padding: 0.5rem;
    border-radius: 16px;
    background: rgba(10, 12, 12, 0.88);
  }
  .menu-title {
    padding: 0.6rem 0.7rem 0.3rem;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(255, 255, 255, 0.5);
  }
  .menu button {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    width: 100%;
    padding: 0.55rem 0.7rem;
    border: 0;
    border-radius: 10px;
    background: transparent;
    color: #fff;
    font: inherit;
    font-size: 0.9rem;
    text-align: left;
    cursor: pointer;
  }
  .menu button:hover,
  .menu button:focus-visible {
    background: rgba(255, 255, 255, 0.08);
  }
  .menu button[aria-checked='true'] {
    color: var(--color-accent);
  }
  .aside {
    margin-left: auto;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.45);
  }
  .method {
    margin: 0.2rem 0.7rem 0.3rem;
    padding: 0.45rem 0.6rem;
    border-radius: 8px;
    font-size: 0.75rem;
    color: rgba(255, 255, 255, 0.6);
    background: rgba(149, 255, 80, 0.08);
  }
  .method.converting {
    background: rgba(255, 255, 255, 0.06);
  }
  .tick {
    display: grid;
    place-items: center;
    width: 16px;
  }
  .skip {
    position: absolute;
    right: 1.5rem;
    bottom: 5.5rem;
    height: 44px;
    padding: 0 1.3rem;
    border-radius: 12px;
    color: #fff;
    font: inherit;
    font-weight: 600;
    text-transform: capitalize;
    cursor: pointer;
  }
  .skip:hover {
    background: rgba(255, 255, 255, 0.2);
  }
  .next {
    position: absolute;
    right: 1.5rem;
    bottom: 5.5rem;
    display: flex;
    gap: 0.9rem;
    width: min(420px, calc(100vw - 3rem));
    padding: 0.75rem;
    border-radius: 16px;
    background: rgba(10, 12, 12, 0.85);
    animation: rise 0.4s var(--ease-hover);
  }
  .next img {
    width: 140px;
    aspect-ratio: 16 / 9;
    object-fit: cover;
    border-radius: 10px;
    flex: 0 0 auto;
  }
  .next-text {
    min-width: 0;
  }
  .next-text span {
    font-size: 0.75rem;
    color: var(--color-accent);
    font-weight: 600;
  }
  .next-text p {
    margin: 0.2rem 0 0.6rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .next-actions {
    display: flex;
    gap: 0.4rem;
  }
  .next-actions .btn {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    height: 34px;
    padding: 0 0.9rem;
    font-size: 0.85rem;
  }
  .next-actions .btn.ghost {
    padding: 0 0.6rem;
    background: rgba(255, 255, 255, 0.1);
    color: #fff;
  }
  @keyframes rise {
    from {
      opacity: 0;
      transform: translateY(10px);
    }
  }
  .label p {
    font-weight: 700;
    font-size: 1.05rem;
  }
  .label span {
    font-size: 0.8rem;
    color: rgba(255, 255, 255, 0.7);
  }
  .center {
    position: absolute;
    inset: 0;
    display: grid;
    place-content: center;
    justify-items: center;
    gap: 1rem;
    pointer-events: none;
  }
  .center .btn {
    pointer-events: auto;
  }
  .spin {
    color: var(--color-accent);
    animation: spin 0.9s linear infinite;
  }
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
  .err {
    max-width: 40ch;
    text-align: center;
    color: rgba(255, 255, 255, 0.85);
  }
  .btn {
    height: 42px;
    padding: 0 1.3rem;
    border: 0;
    border-radius: 999px;
    background: var(--color-accent);
    color: #04120b;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
  }
</style>
