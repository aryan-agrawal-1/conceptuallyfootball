import { useState } from 'react'
import type { TransitionDirection, TransitionDirectionStats, TransitionLeveragePayload } from '../../types/transitionLeverage'
import { EventMapNotice } from './EventMapUi'

function rate(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function stateLabel(value: string | null | undefined) {
  if (!value || value === 'all') return 'All states'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function ScopeEvidence({ payload }: { payload: TransitionLeveragePayload }) {
  const coverage = payload.selected.coverage
  const stateEvidence = payload.stateLens.evidence
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-ink-dim">
      <span>{coverage.matchesIncluded.toLocaleString()} matches</span>
      <span>{coverage.possessionCount.toLocaleString()} possessions across both directions</span>
      <span>{stateEvidence.exposureMinutes.toLocaleString()} state min</span>
      {coverage.matchesExcluded ? <span className="text-gold">{coverage.matchesExcluded.toLocaleString()} excluded</span> : null}
      {coverage.ambiguousPossessionCount ? <span className="text-gold">{coverage.ambiguousPossessionCount.toLocaleString()} ambiguous</span> : null}
      {coverage.sparse ? <span className="text-gold">sparse sample (&lt;{coverage.sparseThreshold})</span> : null}
    </div>
  )
}

function ComparisonTable({ stats, baseline, delta, direction, selectedState, comparisonState }: {
  stats: TransitionDirectionStats
  baseline: TransitionDirectionStats
  delta: Record<string, number | null>
  direction: TransitionDirection
  selectedState: string
  comparisonState: string
}) {
  const baselineRows = new Map(baseline.outcomeLadder.map(row => [row.key, row]))
  const opportunityOwner = direction === 'attacking' ? 'team' : 'opponent'
  const grid = 'grid-cols-[minmax(150px,1fr)_96px_88px_88px_80px]'
  return (
    <section className="overflow-hidden border border-line-bright bg-panel" aria-label={direction === 'attacking' ? 'Transition creation comparison' : 'Transition vulnerability comparison'}>
      <div className="flex flex-wrap items-baseline justify-between gap-3 border-b border-line-bright px-3 py-2">
        <div>
          <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">
            {direction === 'attacking' ? 'Transition creation' : 'Transition vulnerability'}
          </h4>
          <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">The share of qualifying transition possessions that reach each outcome.</p>
        </div>
        <span className="font-mono text-[10px] text-ink-dim">{stats.opportunities.toLocaleString()} {opportunityOwner} transition possessions</span>
      </div>
      <p className="px-3 pt-2 text-[9px] leading-relaxed text-ink-muted">These counts cover qualifying transition possessions in {selectedState}; they are not the team’s season totals.</p>
      <div className="overflow-x-auto">
        <div className="min-w-[570px]">
          <div className={`grid ${grid} border-b border-line-bright px-3 py-2 text-[8px] font-bold uppercase tracking-[0.11em] text-ink-muted`}>
            <span>Outcome reached</span>
            <span className="text-right">Transition possessions</span>
            <span className="text-right">{selectedState}</span>
            <span className="text-right">{comparisonState}</span>
            <span className="text-right">Change</span>
          </div>
          <div className="divide-y divide-line px-3">
            {stats.outcomeLadder.map(row => {
              const comparisonRow = baselineRows.get(row.key)
              const change = delta[row.key] ?? null
              return (
                <div key={row.key} className={`grid ${grid} items-center py-2.5 text-[10px]`}>
                  <span className="min-w-0 pr-3 text-ink">{row.label}</span>
                  <span className="text-right font-mono tabular-nums text-ink-muted">{row.count.toLocaleString()}</span>
                  <span className="text-right font-mono tabular-nums text-ink">{rate(row.ratePerOpportunity)}</span>
                  <span className="text-right font-mono tabular-nums text-ink-dim">{rate(comparisonRow?.ratePerOpportunity ?? null)}</span>
                  <span className={`text-right font-mono tabular-nums ${change == null ? 'text-ink-muted' : change > 0 ? (direction === 'attacking' ? 'text-mint' : 'text-ember') : change < 0 ? (direction === 'attacking' ? 'text-ember' : 'text-mint') : 'text-ink-dim'}`}>
                    {change == null ? '—' : `${change > 0 ? '+' : ''}${(change * 100).toFixed(1)}pp`}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      </div>
      <p className="border-t border-line-bright px-3 py-2 text-[9px] leading-relaxed text-ink-muted">Each percentage is the share of transition possessions that reached that outcome. Change is {selectedState} minus {comparisonState}.</p>
    </section>
  )
}

export function TransitionLeveragePanel({ payload, loading, error, onRetry }: {
  payload?: TransitionLeveragePayload
  loading: boolean
  error?: string
  onRetry: () => void
}) {
  const [direction, setDirection] = useState<TransitionDirection>('attacking')
  if (loading) return <EventMapNotice kind="loading" title="Loading transition leverage" />
  if (error || !payload) return <EventMapNotice kind="error" title="Transition leverage failed to load" onRetry={onRetry}>{error}</EventMapNotice>

  const stats = payload.selected[direction]
  const baseline = payload.comparison.baseline?.[direction] ?? null
  const delta = payload.comparison.delta?.[direction] ?? null
  const selectedState = stateLabel(payload.stateLens.selected.state)
  const comparisonState = stateLabel(payload.stateLens.comparison.baseline?.state)

  return (
    <article className="space-y-3 py-3" aria-label="Transition leverage">
      <header className="max-w-3xl">
        <h3 className="text-xs font-bold uppercase tracking-[0.15em] text-ink">Transition leverage</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">How often the team’s transition possessions become dangerous attacks, compared with the selected baseline.</p>
      </header>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
        <p className="text-[10px] uppercase tracking-[0.1em] text-ink-dim">Possession opportunities <strong className="ml-1 font-mono text-[15px] font-normal text-ink">{stats.opportunities.toLocaleString()}</strong></p>
        <div className="ml-auto"><ScopeEvidence payload={payload} /></div>
      </div>
      <div className="flex gap-4 border-b border-line-bright" role="group" aria-label="Transition leverage perspective">
        {(['attacking', 'concession'] as const).map(value => <button key={value} type="button" aria-pressed={direction === value} onClick={() => setDirection(value)} className={`border-b-2 px-1 py-2 text-[10px] uppercase tracking-[0.12em] ${direction === value ? (value === 'attacking' ? 'border-electric text-electric' : 'border-ember text-ember') : 'border-transparent text-ink-dim hover:text-ink'}`}>{value === 'attacking' ? 'Creation for' : 'Vulnerability against'}</button>)}
      </div>
      {baseline && delta ? (
        <ComparisonTable stats={stats} baseline={baseline} delta={delta} direction={direction} selectedState={selectedState} comparisonState={comparisonState} />
      ) : (
        <EventMapNotice kind="unavailable" title="Choose a comparison state">Transition Leverage needs a State Lens comparison to show what is distinctive about this team.</EventMapNotice>
      )}
      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">How this is calculated</summary>
        <p className="mt-2">Each verified transition possession is checked for a territorial entry, box entry, shot, big chance and goal. A possession can reach several outcomes, so the rows are conversion checkpoints rather than separate categories. The comparison uses the baseline selected in the State Lens.</p>
      </details>
    </article>
  )
}
