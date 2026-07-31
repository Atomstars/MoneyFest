import { useEffect, useState } from 'react'
import { api, type Shareholding as ShareholdingData } from '../../lib/api'
import { count, pct, periodLabel } from '../../lib/format'
import { Card, CardTitle, Skeleton } from '../ui'

/**
 * Who owns the company, and how that has changed.
 *
 * The promoter share is the number Indian retail investors actually watch -- a stake
 * falling several quarters running is the classic thing people look for -- so it gets
 * the headline and the trend, not just a slice of a pie.
 *
 * A note on scope, made visible rather than glossed over: the exchange feed publishes
 * the promoter/public split, not the FII/DII breakdown. That detail lives inside the
 * XBRL attachments on each filing. The aggregate institutional figure shown alongside
 * comes from a different source with a different as-of date, and says so.
 */
function StackedBar({ promoter, publicPct }: { promoter: number | null; publicPct: number | null }) {
  if (promoter == null && publicPct == null) return null
  const p = (promoter ?? 0) * 100
  const q = (publicPct ?? 0) * 100
  return (
    <div className="flex h-7 overflow-hidden rounded-lg" role="img"
         aria-label={`Promoter ${p.toFixed(2)} percent, public ${q.toFixed(2)} percent`}>
      <div className="flex items-center justify-center text-[11px] font-medium"
           style={{ width: `${p}%`, background: 'var(--series-1)', color: '#fff' }}>
        {p >= 12 ? `${p.toFixed(1)}%` : ''}
      </div>
      <div className="flex items-center justify-center text-[11px] font-medium"
           style={{ width: `${q}%`, background: 'var(--series-3)', color: '#fff' }}>
        {q >= 12 ? `${q.toFixed(1)}%` : ''}
      </div>
    </div>
  )
}

/** Promoter share across quarters. Sparse bars, oldest to newest. */
function PromoterTrend({ data }: { data: ShareholdingData }) {
  const quarters = [...data.quarters].reverse().filter((q) => q.promoter_pct != null)
  if (quarters.length < 2) return null

  const values = quarters.map((q) => q.promoter_pct as number)
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  // A flat promoter stake is the common case, and a zero-based axis would render it
  // as a wall of identical bars. Padding a narrow band makes real drift visible --
  // the y-axis is explicitly labelled so this cannot be misread as volatility.
  const floor = hi - lo < 0.005 ? lo - 0.01 : lo - (hi - lo) * 0.4
  const span = Math.max(hi - floor, 0.001)

  return (
    <div>
      <div className="flex h-24 items-end gap-1">
        {quarters.map((q) => (
          <div key={q.period} className="group relative flex-1"
               title={`${periodLabel(q.period)}: ${pct(q.promoter_pct, 2)}`}>
            <div
              className="w-full rounded-t-sm transition-opacity group-hover:opacity-80"
              style={{
                height: `${Math.max((((q.promoter_pct as number) - floor) / span) * 96, 3)}px`,
                background: 'var(--series-1)',
              }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px]" style={{ color: 'var(--text-muted)' }}>
        <span>{periodLabel(quarters[0].period)}</span>
        <span>
          axis {pct(floor, 1)}–{pct(hi, 1)}
        </span>
        <span>{periodLabel(quarters[quarters.length - 1].period)}</span>
      </div>
    </div>
  )
}

export function Shareholding({ stockId }: { stockId: number }) {
  const [data, setData] = useState<ShareholdingData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.shareholding(stockId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [stockId])

  if (loading) return <Skeleton className="h-72 w-full" />

  if (!data?.latest) {
    return (
      <Card>
        <p className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          No shareholding pattern filed for this stock on the exchange feed.
        </p>
      </Card>
    )
  }

  const { latest, promoter_change_qoq: change, institutions } = data

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardTitle aside={`as of ${periodLabel(latest.period)}`}>Shareholding pattern</CardTitle>

        <StackedBar promoter={latest.promoter_pct} publicPct={latest.public_pct} />

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3">
          <div>
            <dt className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              <span className="inline-block size-2.5 rounded-sm" style={{ background: 'var(--series-1)' }} />
              Promoters
            </dt>
            <dd className="tnum mt-0.5 text-lg font-semibold">{pct(latest.promoter_pct, 2)}</dd>
            {change != null && (
              <dd className="tnum text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {change === 0
                  ? 'unchanged from previous quarter'
                  : `${change > 0 ? '+' : '−'}${Math.abs(change * 100).toFixed(2)} pts QoQ`}
              </dd>
            )}
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              <span className="inline-block size-2.5 rounded-sm" style={{ background: 'var(--series-3)' }} />
              Public
            </dt>
            <dd className="tnum mt-0.5 text-lg font-semibold">{pct(latest.public_pct, 2)}</dd>
          </div>
        </dl>

        {latest.employee_trusts_pct ? (
          <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
            Employee trusts hold {pct(latest.employee_trusts_pct, 2)}.
          </p>
        ) : null}

        <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
          Filed with {data.source}. {data.quarters.length} quarters on record.
        </p>
      </Card>

      <Card>
        <CardTitle>Promoter stake over time</CardTitle>
        <PromoterTrend data={data} />

        {institutions && (
          <div className="mt-5 border-t pt-4" style={{ borderColor: 'var(--border)' }}>
            <h3 className="text-xs font-semibold">Institutional holding</h3>
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2">
              {institutions.institutions_pct != null && (
                <div>
                  <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Held by institutions</dt>
                  <dd className="tnum mt-0.5 text-sm font-medium">
                    {pct(institutions.institutions_pct, 2)}
                  </dd>
                </div>
              )}
              {institutions.institutions_count != null && (
                <div>
                  <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Institutional holders</dt>
                  <dd className="tnum mt-0.5 text-sm font-medium">
                    {count(institutions.institutions_count)}
                  </dd>
                </div>
              )}
            </dl>
            {data.institutions_note && (
              <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                {data.institutions_note}
              </p>
            )}
          </div>
        )}
      </Card>
    </div>
  )
}
