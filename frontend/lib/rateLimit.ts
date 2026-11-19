import { useCallback, useEffect, useState } from 'react';

/** The longest backend window (per minute), used when a 429 carries no wait at all. */
export const RATE_LIMIT_FALLBACK_SECONDS = 60;

const DETAIL_WAIT = /Aguarde (\d+) s/;

/** Seconds from a Retry-After value: delay-seconds or an HTTP-date (RFC 9110 §10.2.3). */
export function parseRetryAfter(value: string | null | undefined, now: number = Date.now()): number | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (/^\d+$/.test(trimmed)) {
    const seconds = Number(trimmed);
    return seconds > 0 ? seconds : null;
  }
  const at = Date.parse(trimmed);
  if (Number.isNaN(at)) return null;
  const seconds = Math.ceil((at - now) / 1000);
  return seconds > 0 ? seconds : null;
}

/**
 * Seconds to wait before retrying a rate-limited request, or null when `err` is not a 429.
 * Reads `retryAfter` (the Retry-After header), then "Aguarde N s" in the detail.
 */
export function rateLimitWait(err: unknown): number | null {
  if (typeof err !== 'object' || err === null) return null;
  const { status, retryAfter, message } = err as { status?: unknown; retryAfter?: unknown; message?: unknown };
  if (status !== 429) return null;
  if (typeof retryAfter === 'number' && Number.isFinite(retryAfter) && retryAfter > 0) {
    return Math.ceil(retryAfter);
  }
  const fromDetail = typeof message === 'string' ? DETAIL_WAIT.exec(message)?.[1] : undefined;
  if (fromDetail && Number(fromDetail) > 0) return Number(fromDetail);
  return RATE_LIMIT_FALLBACK_SECONDS;
}

/**
 * A wait that ticks down once a second. `message` is fixed when the wait starts, so a role="status"
 * node showing it is announced once; only `seconds` (shown on the button, outside any live region) ticks.
 * Both clear at 0.
 */
export function useRetryCountdown() {
  const [wait, setWait] = useState<{ seconds: number; message: string } | null>(null);

  const active = wait !== null;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => {
      setWait((current) => (current && current.seconds > 1 ? { ...current, seconds: current.seconds - 1 } : null));
    }, 1000);
    return () => clearInterval(timer);
  }, [active]);

  const start = useCallback((seconds: number, message: string) => {
    setWait({ seconds, message });
  }, []);

  return { seconds: wait?.seconds ?? null, message: wait?.message ?? null, start };
}
