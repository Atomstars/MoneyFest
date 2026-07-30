/**
 * Tiny trend mark for a position row. No axes, no labels -- it shows shape only,
 * and every row that carries one also shows the exact numbers beside it, so the
 * sparkline never has to be read precisely.
 */
export function Sparkline({
  values,
  width = 96,
  height = 30,
  direction = 'flat',
}: {
  values: number[]
  width?: number
  height?: number
  direction?: 'up' | 'down' | 'flat'
}) {
  if (values.length < 2) {
    return <svg width={width} height={height} aria-hidden="true" />
  }

  const color =
    direction === 'up' ? 'var(--up)' : direction === 'down' ? 'var(--down)' : 'var(--text-muted)'

  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const pad = 3

  const x = (i: number) => (i / (values.length - 1)) * (width - pad * 2) + pad
  const y = (v: number) => height - pad - ((v - min) / span) * (height - pad * 2)

  const d = values.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join('')

  return (
    <svg width={width} height={height} aria-hidden="true" className="overflow-visible">
      <path d={d} fill="none" stroke={color} strokeWidth="1.75"
            strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={x(values.length - 1)} cy={y(values[values.length - 1])} r="2.5"
              fill={color} stroke="var(--surface-1)" strokeWidth="1.5" />
    </svg>
  )
}
