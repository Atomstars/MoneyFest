import { useEffect, useRef, useState } from 'react'

/**
 * Motion primitives.
 *
 * Rule for everything here: an animation must say something. Numbers counting up
 * signals "this was just computed"; a shimmer signals "loading"; a flash signals
 * "this value changed". Nothing loops purely for decoration — a dashboard that never
 * settles is tiring to actually use, and this one is meant to be looked at daily.
 *
 * All of it degrades under `prefers-reduced-motion` (handled in index.css, plus the
 * explicit check in `useCountUp` — a JS-driven tween can't be stopped by CSS).
 */

function prefersReducedMotion(): boolean {
  return typeof window !== 'undefined' &&
    window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true
}

/**
 * Tween a number toward its target.
 *
 * Only animates on first appearance and on genuinely large jumps. Re-tweening on
 * every small quote refresh would leave the portfolio total permanently in motion
 * and unreadable — the opposite of what the effect is for.
 */
export function useCountUp(target: number | null | undefined, duration = 900): number | null {
  const [value, setValue] = useState<number | null>(target ?? null)
  const fromRef = useRef<number>(target ?? 0)
  const frameRef = useRef<number>(0)

  useEffect(() => {
    if (target == null || !Number.isFinite(target)) { setValue(null); return }
    const from = fromRef.current
    const delta = Math.abs(target - from)
    // Skip the tween for small deltas (a routine price tick) and honour the OS setting.
    if (prefersReducedMotion() || (from !== 0 && delta / Math.max(Math.abs(from), 1) < 0.02)) {
      fromRef.current = target
      setValue(target)
      return
    }

    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1)
      // easeOutExpo: fast commit, gentle settle — reads as "resolving", not "spinning".
      const eased = t === 1 ? 1 : 1 - Math.pow(2, -10 * t)
      setValue(from + (target - from) * eased)
      if (t < 1) frameRef.current = requestAnimationFrame(tick)
      else fromRef.current = target
    }
    frameRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frameRef.current)
  }, [target, duration])

  return value
}

/** A number that counts up on arrival, formatted by the caller. */
export function CountUp({ value, format, className, style }: {
  value: number | null | undefined
  format: (v: number | null) => string
  className?: string
  style?: React.CSSProperties
}) {
  const animated = useCountUp(value)
  return <span className={className} style={style}>{format(animated)}</span>
}

/** Loading placeholder. Sweeps rather than pulses — see index.css. */
export function Shimmer({ className = '', style }: { className?: string; style?: React.CSSProperties }) {
  return <div className={`shimmer ${className}`} style={style} aria-hidden="true" />
}

/** Briefly tints a value when it changes. Used on live-refreshing prices. */
export function FlashOnChange({ value, children }: { value: number | null | undefined; children: React.ReactNode }) {
  const previous = useRef(value)
  const [flash, setFlash] = useState<'up' | 'down' | null>(null)

  useEffect(() => {
    const before = previous.current
    if (before != null && value != null && before !== value) {
      setFlash(value > before ? 'up' : 'down')
      const timer = setTimeout(() => setFlash(null), 900)
      return () => clearTimeout(timer)
    }
    previous.current = value
  }, [value])

  useEffect(() => { previous.current = value }, [value])

  return <span className={flash ? `flash-${flash}` : undefined}>{children}</span>
}

/** Dot marking a value that refreshes. Blinks three times, then rests. */
export function LiveDot({ colour = 'var(--series-3)' }: { colour?: string }) {
  return (
    <span
      className="live-dot inline-block size-1.5 shrink-0"
      style={{ background: colour, color: colour }}
      aria-hidden="true"
    />
  )
}
