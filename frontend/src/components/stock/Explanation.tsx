import { useEffect, useState } from 'react'
import { api, type StockDetail } from '../../lib/api'
import { longDate, OUTCOME_HELP } from '../../lib/format'
import { Card, CardTitle, ConfidenceBadge, OutcomeChip, Skeleton } from '../ui'

/**
 * "Why did this move?" -- the reason this app exists.
 *
 * The engine's rendered sentence is shown verbatim, never paraphrased: the renderer
 * already guarantees every clause traces to a verified, cited claim, and rewording it
 * here would quietly break that guarantee.
 *
 * NOISE, MARKET and NO_DRIVER are first-class answers, not empty states. Most trading
 * days genuinely have nothing to explain, and presenting that as a failure would push
 * the product toward inventing narratives -- exactly what it is built not to do.
 */
export function Explanation({ stockId, gateResult, gateDate }: {
  stockId: number
  gateResult: string | null
  gateDate: string | null
}) {
  const [detail, setDetail] = useState<StockDetail | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.attribution(stockId)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [stockId])

  if (loading) return <Skeleton className="h-56 w-full" />

  const outcome = detail?.outcome_display ?? gateResult
  const drivers = detail?.drivers ?? []
  const evidence = detail?.evidence ?? []

  return (
    <div className="space-y-4">
      <Card>
        <CardTitle aside={gateDate ? longDate(gateDate) : undefined}>
          <span className="flex items-center gap-2">
            Why it moved
            <OutcomeChip outcome={outcome} />
          </span>
        </CardTitle>

        {detail?.rendered_text ? (
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {detail.rendered_text}
          </p>
        ) : outcome ? (
          <p className="text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {OUTCOME_HELP[outcome] ?? outcome}
          </p>
        ) : (
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            No assessment recorded for this stock yet.
          </p>
        )}

        {(outcome === 'NOISE' || outcome === 'MARKET' || outcome === 'NO_DRIVER') && (
          <p className="mt-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
            “Nothing to explain” is a real answer — most trading days are exactly this.
          </p>
        )}
      </Card>

      {drivers.length > 0 && (
        <Card>
          <CardTitle>Drivers</CardTitle>
          <ol className="space-y-4">
            {drivers.map((d) => (
              <li key={d.rank} className="border-l-2 pl-3" style={{ borderColor: 'var(--series-1)' }}>
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold">
                    {d.factor_id?.replace(/_/g, ' ') ?? 'Unnamed factor'}
                  </span>
                  <ConfidenceBadge level={d.confidence} />
                </div>
                {d.chain_text && (
                  <p className="mt-1 text-sm leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                    {d.chain_text}
                  </p>
                )}
                {d.confidence_reason && (
                  <p className="mt-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    {d.confidence_reason}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </Card>
      )}

      {evidence.length > 0 && (
        <Card>
          <CardTitle aside={`${evidence.length} item${evidence.length === 1 ? '' : 's'}`}>
            Cited evidence
          </CardTitle>
          <ul className="space-y-2.5">
            {evidence.map((e) => (
              <li key={e.id} className="flex items-start gap-2 text-sm">
                <span
                  className="mt-0.5 shrink-0 rounded px-1.5 py-px text-[10px] font-medium"
                  style={{
                    border: '1px solid var(--border)',
                    color: 'var(--text-muted)',
                  }}
                >
                  T{e.tier}
                </span>
                <div className="min-w-0">
                  {e.url ? (
                    <a
                      href={e.url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="underline underline-offset-2"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {e.headline ?? e.source}
                    </a>
                  ) : (
                    <span>{e.headline ?? e.source}</span>
                  )}
                  <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    {e.source}
                    {e.suspect_reactive && ' · published after the move — may be reporting it, not causing it'}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}

      <p className="text-center text-xs" style={{ color: 'var(--text-muted)' }}>
        Explanation only — not investment advice.
      </p>
    </div>
  )
}
