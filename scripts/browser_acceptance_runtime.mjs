export function boundedBrowserTimeout(requestedMs) {
  const configured = Number(process.env.STORY_AUDIO_BROWSER_TIMEOUT_MS);
  return Number.isFinite(configured) && configured > 0
    ? Math.max(requestedMs, configured)
    : requestedMs;
}
