/** One countdown per player. Media events pause it without losing its place. */
export function createAutoplay(video, {
  seconds = 10,
  onTick = () => {},
  onNext,
  schedule = (fn) => setInterval(fn, 1000),
  cancel = (timer) => clearInterval(timer)
}) {
  let remaining = seconds;
  let enabled = false;
  let buffering = false;
  let advanced = false;
  let disposed = false;
  let timer = null;

  const canCount = () => enabled && !disposed && !advanced && !buffering &&
    !video.paused && !video.seeking && !video.ended && video.readyState >= 3;

  function stop() {
    if (timer !== null) cancel(timer);
    timer = null;
  }

  function advance() {
    if (disposed || advanced) return;
    advanced = true; // Set before the callback: ended and timer may run together.
    stop();
    onNext();
  }

  function sync() {
    if (!canCount()) {
      stop();
    } else if (timer === null) {
      timer = schedule(() => {
        if (!canCount()) return sync();
        onTick(--remaining);
        if (remaining <= 0) advance();
      });
    }
  }

  const wait = () => { buffering = true; sync(); };
  const ready = () => { buffering = false; sync(); };
  const listeners = {
    pause: sync, playing: ready, canplay: ready, seeked: ready,
    waiting: wait, seeking: wait, emptied: wait, error: wait
  };
  for (const [name, listener] of Object.entries(listeners)) video.addEventListener(name, listener);

  return {
    setEnabled(value) {
      if (disposed) return;
      enabled = value;
      if (!enabled) onTick(remaining = seconds);
      sync();
    },
    advance,
    destroy() {
      disposed = true;
      stop();
      for (const [name, listener] of Object.entries(listeners)) video.removeEventListener(name, listener);
    }
  };
}
