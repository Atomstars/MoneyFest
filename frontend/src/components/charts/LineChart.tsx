import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { compactMoney, shortDate } from '../../lib/format'

type Point = { date: string; value: number }

/**
 * Single-series time chart with a crosshair + tooltip.
 *
 * Per the mark spec: 2px stroke, recessive hairline grid, no marker on every
 * point (only the hovered one), and no legend -- the title names the one series.
 * A single measure means one axis; there is deliberately no second y-scale.
 */
export function LineChart({
  data,
  height = 260,
  color = 'var(--series-1)',
  label = 'Value',
}: {
  data: Point[]
  height?: number
  color?: string
  label?: string
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<number | null>(null)
  const [width, setWidth] = useState(720)

  // Observe the container so the viewBox matches real layout width. This must be an
  // effect, not useMemo: useMemo runs during render while the ref is still null, so
  // the observer was never attached and its cleanup never ran -- width stayed pinned
  // at the default and the SVG letterboxed badly on narrow screens.
  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    setWidth(el.clientWidth)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(([entry]) => setWidth(entry.contentRect.width))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const pad = { top: 16, right: 16, bottom: 26, left: 52 }
  const w = Math.max(width, 320)
  const innerW = w - pad.left - pad.right
  const innerH = height - pad.top - pad.bottom

  const { min, max } = useMemo(() => {
    if (!data.length) return { min: 0, max: 1 }
    const vs = data.map((d) => d.value)
    const lo = Math.min(...vs)
    const hi = Math.max(...vs)
    const span = hi - lo || Math.abs(hi) || 1
    return { min: lo - span * 0.08, max: hi + span * 0.08 }
  }, [data])

  if (!data.length) {
    return (
      <div className="grid place-items-center text-sm" style={{ height, color: 'var(--text-muted)' }}>
        No history yet
      </div>
    )
  }

  const x = (i: number) => pad.left + (data.length === 1 ? innerW / 2 : (i / (data.length - 1)) * innerW)
  const y = (v: number) => pad.top + innerH - ((v - min) / (max - min)) * innerH

  const path = data.map((d, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(d.value).toFixed(1)}`).join('')
  const area = `${path}L${x(data.length - 1).toFixed(1)},${pad.top + innerH}L${x(0).toFixed(1)},${pad.top + innerH}Z`

  const ticks = 4
  const gridVals = Array.from({ length: ticks + 1 }, (_, i) => min + ((max - min) * i) / ticks)
  const gid = useMemo(() => `lg-${Math.random().toString(36).slice(2, 9)}`, [])

  const onMove = (e: React.PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const rel = ((e.clientX - rect.left) / rect.width) * w
    const i = Math.round(((rel - pad.left) / innerW) * (data.length - 1))
    setHover(Math.max(0, Math.min(data.length - 1, i)))
  }

  const hp = hover !== null ? data[hover] : null

  return (
    <div ref={wrapRef} className="relative w-full">
      <svg
        width="100%"
        height={height}
        viewBox={`0 0 ${w} ${height}`}
        role="img"
        aria-label={`${label} over time, ${data.length} points`}
        onPointerMove={onMove}
        onPointerLeave={() => setHover(null)}
        style={{ touchAction: 'pan-y' }}
      >
        <defs>
          <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity="0.18" />
            <stop offset="100%" stopColor={color} stopOpacity="0" />
          </linearGradient>
        </defs>

        {gridVals.map((v, i) => (
          <g key={i}>
            <line
              x1={pad.left} x2={w - pad.right} y1={y(v)} y2={y(v)}
              stroke="var(--gridline)" strokeWidth="1"
            />
            <text
              x={pad.left - 8} y={y(v)} textAnchor="end" dominantBaseline="middle"
              fontSize="11" fill="var(--text-muted)" className="tnum"
            >
              {compactMoney(v)}
            </text>
          </g>
        ))}

        <path d={area} fill={`url(#${gid})`} />
        <path d={path} fill="none" stroke={color} strokeWidth="2"
              strokeLinejoin="round" strokeLinecap="round" />

        {[0, Math.floor((data.length - 1) / 2), data.length - 1].map((i) => (
          <text key={i} x={x(i)} y={height - 6} fontSize="11" fill="var(--text-muted)"
                textAnchor={i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle'}>
            {shortDate(data[i].date)}
          </text>
        ))}

        {hp && (
          <g pointerEvents="none">
            <line x1={x(hover!)} x2={x(hover!)} y1={pad.top} y2={pad.top + innerH}
                  stroke="var(--baseline)" strokeWidth="1" strokeDasharray="3 3" />
            {/* 2px surface ring so the marker reads on top of the line */}
            <circle cx={x(hover!)} cy={y(hp.value)} r="5.5"
                    fill={color} stroke="var(--surface-1)" strokeWidth="2" />
          </g>
        )}
      </svg>

      {hp && (
        <div
          className="pointer-events-none absolute z-10 rounded-lg px-2.5 py-1.5 text-xs shadow-lg"
          style={{
            left: `${Math.min(Math.max((x(hover!) / w) * 100, 8), 92)}%`,
            top: 4,
            transform: 'translateX(-50%)',
            background: 'var(--surface-1)',
            border: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        >
          <div style={{ color: 'var(--text-secondary)' }}>{shortDate(hp.date)}</div>
          <div className="tnum font-semibold">{compactMoney(hp.value)}</div>
        </div>
      )}
    </div>
  )
}
