import type { ResponseHalfLifeCohort, ResponseHalfLifePayload, ResponseHalfLifeSummary } from '../../types/responseHalfLife'
import { EventMapNotice } from './EventMapUi'

function seconds(value: number | null) {
  if (value == null) return '—'
  const rounded = Math.round(value)
  if (rounded === 0) return '0s'
  const minutes = Math.floor(rounded / 60)
  const remainder = rounded % 60
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`
}

function reliabilityTone(value: ResponseHalfLifeCohort['reliability']) {
  return value === 'verified' ? 'text-mint' : value === 'unavailable' ? 'text-ember' : 'text-gold'
}

function SummaryCard({ title, description, summary, recovered, colour }: {
  title: string
  description: string
  summary: ResponseHalfLifeSummary
  recovered: number
  colour: string
}) {
  return (
    <section className="border border-line-bright bg-panel px-4 py-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">{title}</h4>
          <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-ink-dim">{description}</p>
        </div>
        <span className={`font-mono text-[9px] uppercase ${colour}`}>{summary.sampleSize} responses</span>
      </div>
      <div className="mt-4 flex items-end justify-between gap-4 border-t border-line pt-3">
        <div>
          <p className={`font-mono text-3xl tabular-nums ${colour}`}>{seconds(summary.medianSeconds)}</p>
          <p className="mt-1 text-[9px] leading-relaxed text-ink-muted">Median time to move halfway back towards usual behaviour</p>
        </div>
        <dl className="shrink-0 text-right text-[9px] text-ink-muted">
          <dt>Average time</dt>
          <dd className="font-mono text-[11px] text-ink">{seconds(summary.meanSeconds)}</dd>
          <dt className="mt-1">Observed responses</dt>
          <dd className="font-mono text-[11px] text-ink">{recovered}</dd>
        </dl>
      </div>
    </section>
  )
}

function EvidenceStrip({ cohort }: { cohort: ResponseHalfLifeCohort }) {
  return (
    <dl className="grid border border-line-bright bg-line sm:grid-cols-4">
      {[
        ['Goals against analysed', cohort.qualifyingConcessions.toLocaleString()],
        ['Response windows', cohort.qualifyingWindows.toLocaleString()],
        ['Matches', cohort.qualifyingMatches.toLocaleString()],
        ['Responses excluded', cohort.censoredEpisodes.toLocaleString()],
      ].map(([title, value]) => (
        <div key={title} className="bg-panel px-3 py-2.5">
          <dt className="text-[8px] font-bold uppercase tracking-[0.14em] text-ink-dim">{title}</dt>
          <dd className="mt-1 font-mono text-[15px] tabular-nums text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ResponseHalfLifePanel({ payload, loading, error, onRetry }: {
  payload?: ResponseHalfLifePayload
  loading: boolean
  error?: string
  onRetry: () => void
}) {
  if (loading) return <EventMapNotice kind="loading" title="Loading response half-life" />
  if (error || !payload) return <EventMapNotice kind="error" title="Response half-life failed to load" onRetry={onRetry}>{error}</EventMapNotice>
  const cohort = payload.selected
  return (
    <article className="space-y-3 py-3" aria-label="Team response half-life">
      <header className="max-w-3xl">
        <h3 className="text-xs font-bold uppercase tracking-[0.15em] text-ink">Response half-life</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">How quickly a team settles into its usual behaviour for the new scoreline after the opposition scores.</p>
      </header>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-ink-dim">
        <span className={`font-bold uppercase tracking-[0.12em] ${reliabilityTone(cohort.reliability)}`}>{cohort.reliability}</span>
        <span>The headline time shows when the team has moved halfway from its immediate reaction towards its usual behaviour in that match situation.</span>
      </div>

      <EvidenceStrip cohort={cohort} />
      <div className="grid items-start gap-3 lg:grid-cols-2">
        <SummaryCard
          title="Attacking response"
          description="Changes in shots, box entries, progressive actions and attacking field position."
          summary={cohort.attacking.halfLifeSeconds}
          recovered={cohort.attacking.recoveredConcessions}
          colour="text-electric"
        />
        <SummaryCard
          title="Structural response"
          description="Changes in passing choices, territory and defensive position."
          summary={cohort.structural.halfLifeSeconds}
          recovered={cohort.structural.recoveredConcessions}
          colour="text-mint"
        />
      </div>

      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">How this is calculated</summary>
        <div className="mt-2 space-y-2">
          <p>Behaviour is measured in {payload.definitions.windowSeconds / 60}-minute windows after each opposition goal and compared with how the team usually plays in the resulting scoreline, match phase and goal difference.</p>
          <p>The half-life is the first supported point where the gap has reduced by half. The headline is the median across qualifying responses; attacking and structural behaviour remain separate because they can settle at different speeds.</p>
          <p>A response is excluded when the comparison is unreliable or an interruption such as another goal, a red card or the end of a period prevents a complete reading.</p>
        </div>
      </details>
    </article>
  )
}
