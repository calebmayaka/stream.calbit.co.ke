// What this browser can decode, sent with every Play request so the server
// copies video it can play (repackaging only) and transcodes the rest.
// The server has no GPU, so every HEVC title a browser can play natively is a
// transcode the CPU doesn't have to do.

const TYPES = {
  hevc: 'video/mp4; codecs="hvc1.1.6.L120.90"', // HEVC Main, 1080p
  hevc10: 'video/mp4; codecs="hvc1.2.4.L120.90"', // HEVC Main 10
  av1: 'video/mp4; codecs="av01.0.08M.08"',
  av1_10: 'video/mp4; codecs="av01.0.08M.10"',
  ac3: 'audio/mp4; codecs="ac-3"',
  eac3: 'audio/mp4; codecs="ec-3"'
};

let cached = null;

/** @returns {{ hevc: boolean, hevc10: boolean, av1: boolean, av1_10: boolean, ac3: boolean, eac3: boolean }} */
export function detectCapabilities() {
  if (cached) return cached;
  // hls.js plays through Media Source Extensions; Safari/iOS may use native HLS.
  const mse = globalThis.ManagedMediaSource ?? globalThis.MediaSource;
  const probe = document.createElement('video');
  const can = (type) => {
    try {
      if (mse?.isTypeSupported?.(type)) return true;
    } catch {
      /* treat as unsupported */
    }
    return probe.canPlayType(type) === 'probably';
  };
  cached = Object.fromEntries(Object.entries(TYPES).map(([key, type]) => [key, can(type)]));
  // A Main 10 decoder implies Main.
  if (cached.hevc10) cached.hevc = true;
  if (cached.av1_10) cached.av1 = true;
  return cached;
}

/** Short "Browser/OS" label for playback stats (no version numbers or IDs). */
export function clientLabel() {
  const ua = navigator.userAgent;
  const browser = /Edg\//.test(ua)
    ? 'Edge'
    : /OPR\//.test(ua)
      ? 'Opera'
      : /Firefox\//.test(ua)
        ? 'Firefox'
        : /Chrome\//.test(ua)
          ? 'Chrome'
          : /Safari\//.test(ua)
            ? 'Safari'
            : 'Other';
  const os = /Android/.test(ua)
    ? 'Android'
    : /iPhone|iPad|iPod/.test(ua)
      ? 'iOS'
      : /Windows/.test(ua)
        ? 'Windows'
        : /Mac OS X/.test(ua)
          ? 'macOS'
          : /Linux/.test(ua)
            ? 'Linux'
            : 'Other';
  return `${browser}/${os}`;
}
