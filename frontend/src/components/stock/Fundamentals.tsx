import { useEffect, useState } from 'react'
import { api, type Fundamentals as FundamentalsData, type StatementPeriod } from '../../lib/api'
import { count, croreMoney, money, pct, periodLabel, ratio } from '../../lib/format'
import { Card, CardTitle, Skeleton } from '../ui'

/** Field label, formatter, and the unit convention each value follows. */
const STAT_ROWS: Array<[key: string, label: string, fmt: (v: number) => string]> = [
  ['market_cap', 'Market cap', (v) => croreMoney(v)],
  ['pe', 'P/E ratio', (v) => ratio(v)],
  ['pb', 'P/B ratio', (v) => ratio(v)],
  ['eps', 'EPS (TTM)', (v) => money(v, true)],
  ['book_value', 'Book value', (v) => money(v, true)],
  ['roe', 'Return on equity', (v) => pct(v, 1)],
  ['operating_margin', 'Operating margin', (v) => pct(v, 1)],
  ['net_margin', 'Net margin', (v) => pct(v, 1)],
  ['dividend_yield', 'Dividend yield', (v) => pct(v, 2)],
  ['debt_to_equity', 'Debt to equity', (v) => ratio(v)],
  ['high_52w', '52-week high', (v) => money(v, true)],
  ['low_52w', '52-week low', (v) => money(v, true)],
  ['beta', 'Beta', (v) => ratio(v)],
]

/**
 * Revenue and profit as paired bars per period.
 *
 * Bars, not a line: these are discrete reporting periods, not a continuous series,
 * and revenue starts at zero so the bar length is meaningful. Both measures share one
 * scale -- profit is a component of revenue, so a second axis would exaggerate it.
 */
function StatementChart({ periods, currency }: { periods: StatementPeriod[]; currency: string }) {
  const rows = [...periods].reverse()
  const peak = Math.max(...rows.flatMap((p) => [p.revenue ?? 0, p.net_income ?? 0]), 1)

  return (
    <div>
      <div className="mb-3 flex gap-4 text-[11px]" style={{ color: 'var(--text-secondary)' }}>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm" style={{ background: 'var(--series-1)' }} />
          Revenue
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block size-2.5 rounded-sm" style={{ background: 'var(--series-2)' }} />
          Net profit
        </span>
      </div>

      <div className="space-y-2.5">
        {rows.map((p) => (
          <div key={p.period}>
            <div className="mb-1 flex items-baseline justify-between text-[11px]">
              <span style={{ color: 'var(--text-secondary)' }}>{periodLabel(p.period)}</span>
              <span className="tnum" style={{ color: 'var(--text-muted)' }}>
                {croreMoney(p.revenue)}
                {p.net_margin != null && ` · ${pct(p.net_margin, 1)} margin`}
              </span>
            </div>
            <div className="space-y-1">
              <div className="h-2.5 overflow-hidden rounded-sm"
                   style={{ background: 'color-mix(in srgb, var(--text-primary) 6%, transparent)' }}>
                <div className="h-full rounded-sm"
                     style={{ width: `${Math.max(((p.revenue ?? 0) / peak) * 100, 0)}%`,
                              background: 'var(--series-1)' }} />
              </div>
              <div className="h-2.5 overflow-hidden rounded-sm"
                   style={{ background: 'color-mix(in srgb, var(--text-primary) 6%, transparent)' }}>
                <div className="h-full rounded-sm"
                     style={{ width: `${Math.max(((p.net_income ?? 0) / peak) * 100, 0)}%`,
                              background: 'var(--series-2)' }} />
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
        Amounts in {currency}, as reported.
      </p>
    </div>
  )
}

export function Fundamentals({ stockId }: { stockId: number }) {
  const [data, setData] = useState<FundamentalsData | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'annual' | 'quarterly'>('annual')

  useEffect(() => {
    setLoading(true)
    api.fundamentals(stockId)
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false))
  }, [stockId])

  if (loading) {
    return (
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-72 w-full" />
        <Skeleton className="h-72 w-full" />
      </div>
    )
  }

  const stats = data?.key_stats
  const financials = data?.financials
  const profile = data?.profile
  const periods = tab === 'annual' ? financials?.annual ?? [] : financials?.quarterly ?? []

  if (!stats && !financials && !profile) {
    return (
      <Card>
        <p className="py-8 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          No fundamentals available for this stock. Reference data comes from the
          exchange and yfinance, and neither carries every listed name.
        </p>
      </Card>
    )
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {stats && (
        <Card>
          <CardTitle aside={stats.stale ? 'cached' : undefined}>Key statistics</CardTitle>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
            {STAT_ROWS.filter(([k]) => stats.stats[k] != null).map(([k, label, fmt]) => (
              <div key={k}>
                <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {label}
                  {/* Provenance inline: BSE and yfinance disagree on these, and a
                      number you cannot attribute is a number you cannot check. */}
                  {stats.sources[k] && (
                    <span className="ml-1 opacity-60">· {stats.sources[k]}</span>
                  )}
                </dt>
                <dd className="tnum mt-0.5 text-sm font-medium">
                  {fmt(stats.stats[k] as number)}
                </dd>
              </div>
            ))}
          </dl>
          {stats.meta?.index_membership && (
            <p className="mt-4 text-[11px]" style={{ color: 'var(--text-muted)' }}>
              Index membership: {String(stats.meta.index_membership)}
            </p>
          )}
        </Card>
      )}

      {financials && (financials.annual.length > 0 || financials.quarterly.length > 0) && (
        <Card>
          <CardTitle
            aside={
              <div className="flex gap-1">
                {(['annual', 'quarterly'] as const).map((k) => (
                  <button
                    key={k}
                    onClick={() => setTab(k)}
                    className="rounded px-2 py-0.5 text-[11px] font-medium capitalize"
                    style={{
                      background: tab === k
                        ? 'color-mix(in srgb, var(--text-primary) 8%, transparent)' : 'transparent',
                      color: tab === k ? 'var(--text-primary)' : 'var(--text-muted)',
                    }}
                  >
                    {k}
                  </button>
                ))}
              </div>
            }
          >
            Revenue and profit
          </CardTitle>
          {periods.length === 0 ? (
            <p className="py-6 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
              No {tab} statements reported.
            </p>
          ) : (
            <StatementChart periods={periods} currency={financials.currency} />
          )}
        </Card>
      )}

      {profile && (
        <Card className="lg:col-span-2">
          <CardTitle aside={profile.source}>About the company</CardTitle>
          {profile.summary && (
            <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
              {profile.summary}
            </p>
          )}
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            {([
              ['Industry', profile.industry],
              ['Sector', profile.sector],
              ['Employees', profile.employees != null ? count(profile.employees) : null],
              ['Listed since', profile.listing_date],
              ['ISIN', profile.isin],
              ['Exchanges', profile.exchanges],
              ['BSE group', profile.bse_group],
              ['Head office', profile.city],
            ] as Array<[string, string | null]>)
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{k}</dt>
                  <dd className="mt-0.5 text-sm font-medium break-words">{v}</dd>
                </div>
              ))}
          </dl>
          {profile.website && (
            <a
              href={profile.website}
              target="_blank"
              rel="noreferrer noopener"
              className="mt-4 inline-block text-sm font-medium underline underline-offset-2"
              style={{ color: 'var(--series-1)' }}
            >
              {profile.website.replace(/^https?:\/\//, '')}
            </a>
          )}
        </Card>
      )}
    </div>
  )
}
