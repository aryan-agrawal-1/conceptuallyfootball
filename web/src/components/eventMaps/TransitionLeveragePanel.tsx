import { useState } from 'react'
import type {
  TransitionDirection,
  TransitionDirectionStats,
  TransitionLeveragePayload,
  TransitionObservation,
  TransitionPlayerRow,
} from '../../types/transitionLeverage'
import { EventMapNotice, EventMapViewTabs } from './EventMapUi'

type DisplayMode = 'rate' | 'count'

function label(value: string) {
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function rate(value: number | null, mode: DisplayMode) {
  if (mode === 'count') return value == null ? '0' : value.toLocaleString()
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function seconds(value: number | null) {
  if (value == null) return '—'
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, '0')}`
}

function ScopeEvidence({ payload }: { payload: TransitionLeveragePayload }) {
  const coverage = payload.selected.coverage
  const stateEvidence = payload.stateLens.evidence
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[10px] text-ink-dim">
      <span>{coverage.matchesIncluded.toLocaleString()} matches</span>
      <span>{coverage.possessionCount.toLocaleString()} possessions</span>
      <span>{stateEvidence.exposureMinutes.toLocaleString()} state min</span>
      {coverage.matchesExcluded ? <span className="text-gold">{coverage.matchesExcluded.toLocaleString()} excluded</span> : null}
      {coverage.ambiguousPossessionCount ? <span className="text-gold">{coverage.ambiguousPossessionCount.toLocaleString()} ambiguous</span> : null}
      {coverage.sparse ? <span className="text-gold">sparse sample (&lt;{coverage.sparseThreshold})</span> : null}
      {coverage.evidenceTruncated ? <span className="text-gold">showing first {coverage.evidenceLimit}</span> : null}
    </div>
  )
}

function Ladder({ stats, mode, direction }: {
  stats: TransitionDirectionStats
  mode: DisplayMode
  direction: TransitionDirection
}) {
  return (
    <div className="border border-line-bright bg-panel">
      <div className="flex items-baseline justify-between gap-3 border-b border-line-bright px-3 py-2">
        <div>
          <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">
            {direction === 'attacking' ? 'Creation ladder' : 'Concession vulnerability'}
          </h4>
          <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">
            {stats.opportunities.toLocaleString()} {stats.opportunityBasis.replaceAll('_', ' ')}
          </p>
        </div>
        <span className="font-mono text-[10px] text-ink-dim">{stats.stateTransitions.count} state changes</span>
      </div>
      <div className="divide-y divide-line px-3">
        {stats.outcomeLadder.map(row => (
          <div key={row.key} className="flex items-center gap-3 py-2">
            <span className="w-32 shrink-0 text-[10px] uppercase tracking-[0.08em] text-ink-dim">{row.label}</span>
            <div className="h-1.5 min-w-0 flex-1 overflow-hidden bg-line" aria-hidden="true">
              <div className={`h-full ${direction === 'attacking' ? 'bg-electric' : 'bg-ember'}`} style={{ width: `${Math.min(100, (row.ratePerOpportunity ?? 0) * 100)}%` }} />
            </div>
            <span className="w-16 text-right font-mono text-[11px] tabular-nums text-ink">{rate(mode === 'count' ? row.count : row.ratePerOpportunity, mode)}</span>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 border-t border-line-bright px-3 py-2 text-[10px] text-ink-dim">
        <span>Goals <strong className="ml-1 font-mono font-normal text-ink">{stats.scores.goals}</strong></span>
        <span>Own goals <strong className="ml-1 font-mono font-normal text-ink">{stats.scores.ownGoals}</strong></span>
        <span>Transition rate <strong className="ml-1 font-mono font-normal text-ink">{rate(stats.stateTransitions.ratePerOpportunity, mode)}</strong></span>
      </div>
    </div>
  )
}

function TransitionSummary({ observation }: { observation: TransitionObservation }) {
  const transition = observation.stateTransition
  if (!transition.actual) return <span className="text-ink-muted">No score-state change</span>
  const before = transition.before ?? 'unknown'
  const after = transition.after ?? 'unknown'
  return <span className={transition.perspective === 'against' ? 'text-ember' : 'text-mint'}>{label(transition.classification)} · {before} → {after}</span>
}

function Trace({ observation }: { observation: TransitionObservation }) {
  return (
    <ol className="mt-2 space-y-1 border-l border-line-bright pl-3">
      {observation.possessionTrace.map(action => (
        <li key={`${observation.possessionId}-${action.sequence}`} className="relative text-[10px] leading-relaxed text-ink-dim">
          <span className="mr-2 font-mono text-ink-muted">{action.sequence + 1}.</span>
          <strong className="font-medium text-ink">{action.playerName ?? 'Unresolved player'}</strong>
          <span className="mx-1">·</span>
          <span>{action.eventType.replaceAll('_', ' ')}</span>
          <span className="mx-1">·</span>
          <span className="text-electric">{action.roleLabel}</span>
          <span className="mx-1">·</span>
          <span>{seconds(action.matchSeconds)}</span>
          {action.roleEvidence.length ? <span className="ml-1 text-ink-muted">[{action.roleEvidence.join(', ')}]</span> : null}
        </li>
      ))}
    </ol>
  )
}

function ObservationList({ observations }: { observations: TransitionObservation[] }) {
  return (
    <div className="space-y-1">
      {observations.length ? observations.map(observation => (
        <details key={observation.possessionId} className="border border-line bg-panel px-3 py-2 open:border-line-bright">
          <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-ink-dim">
            <span className="font-mono text-ink-muted">#{observation.matchRef} · {seconds(observation.startSecond)}</span>
            <strong className="font-medium text-ink">{label(observation.outcomeTier)}</strong>
            <span>{observation.possessionTrace.length} actions</span>
            <TransitionSummary observation={observation} />
          </summary>
          <div className="mt-2 border-t border-line pt-2">
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-dim">
              <span>{observation.direction === 'for' ? 'Attacking' : 'Opponent'} possession</span>
              <span>{observation.launchType.replaceAll('_', ' ')}</span>
              <span>{observation.terminationReason.replaceAll('_', ' ')}</span>
              {observation.rapidTransition.isCounterLaunch ? <span className="text-electric">Rapid turnover launch{observation.rapidTransition.elapsedSeconds != null ? ` · ${observation.rapidTransition.elapsedSeconds}s` : ''}</span> : null}
              {observation.score.situation ? <span className="text-gold">Penalty</span> : null}
              {observation.score.goalType === 'own_goal' ? <span className="text-ember">Own goal</span> : null}
            </div>
            <Trace observation={observation} />
          </div>
        </details>
      )) : <EventMapNotice kind="empty" title="No possession observations in this scope" />}
    </div>
  )
}

function PlayerList({ players }: { players: TransitionPlayerRow[] }) {
  const [expanded, setExpanded] = useState<number | null>(null)
  return (
    <div className="space-y-1">
      {players.length ? players.map(player => {
        const id = player.canonicalPlayerId ?? -1
        const isExpanded = expanded === id
        return (
          <div key={`${id}-${player.canonicalTeamId}`} className="border border-line bg-panel">
            <button type="button" className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-raised" aria-expanded={isExpanded} onClick={() => setExpanded(isExpanded ? null : id)}>
              <span className="min-w-0 flex-1 truncate text-[11px] text-ink">{player.canonicalPlayerName ?? 'Unresolved player'}</span>
              <span className="font-mono text-[10px] text-ink-dim">{player.involvedPossessions}/{player.opportunities} possessions</span>
              <span className="w-12 text-right font-mono text-[11px] text-electric">{rate(player.involvementRate, 'rate')}</span>
            </button>
            {isExpanded ? (
              <div className="space-y-2 border-t border-line px-3 py-2">
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-dim">
                  <span>{player.coverage.selectedVerifiedMinutes.toLocaleString()} verified state min</span>
                  <span>{player.coverage.includedMatchCount} matches</span>
                  {player.coverage.excludedMatchCount ? <span className="text-gold">{player.coverage.excludedMatchCount} excluded</span> : null}
                  <span className={player.coverage.confidence === 'verified' ? 'text-mint' : 'text-gold'}>{player.coverage.confidence}</span>
                </div>
                <div className="grid gap-1 sm:grid-cols-2">
                  {Object.entries(player.sequenceStages).filter(([, stage]) => stage.actions > 0).map(([role, stage]) => (
                    <div key={role} className="flex justify-between bg-raised px-2 py-1 text-[10px] text-ink-dim"><span>{label(role)}</span><span className="font-mono text-ink">{stage.actions} actions</span></div>
                  ))}
                </div>
                {player.evidence.length ? <ObservationList observations={player.evidence.map(item => ({
                  possessionId: item.possessionId,
                  matchRef: item.matchRef,
                  teamId: player.canonicalTeamId,
                  teamName: player.canonicalTeamName,
                  direction: 'for',
                  period: null,
                  startSecond: null,
                  endSecond: null,
                  durationSeconds: null,
                  start: { x: null, y: null },
                  end: { x: null, y: null },
                  launchType: 'evidence',
                  terminationReason: item.outcomeTier,
                  isAmbiguous: false,
                  rapidTransition: { isCounterLaunch: false, qualifiesForwardProgress: false, elapsedSeconds: null, forwardMetres: null, speedMps: null, outcome: null },
                  outcomeTier: item.outcomeTier,
                  outcomeLadder: {} as TransitionObservation['outcomeLadder'],
                  directionLadder: {} as TransitionObservation['directionLadder'],
                  score: { isGoal: false, goalType: null, scoringTeamId: null, perspective: null, beforeGoalDifference: null, afterGoalDifference: null, situation: null },
                  state: item.state,
                  stateTransition: item.stateTransition,
                  possessionTrace: item.possessionTrace,
                  actionEvidence: item.possessionTrace,
                }))} /> : null}
              </div>
            ) : null}
          </div>
        )
      }) : <EventMapNotice kind="empty" title="No verified player opportunities in this scope" />}
    </div>
  )
}

export function TransitionLeveragePanel({ payload, loading, error, onRetry }: {
  payload?: TransitionLeveragePayload
  loading: boolean
  error?: string
  onRetry: () => void
}) {
  const [direction, setDirection] = useState<TransitionDirection>('attacking')
  const [mode, setMode] = useState<DisplayMode>('rate')
  if (loading) return <EventMapNotice kind="loading" title="Loading transition leverage" />
  if (error || !payload) return <EventMapNotice kind="error" title="Transition leverage failed to load" onRetry={onRetry}>{error}</EventMapNotice>
  const stats = payload.selected[direction]
  const transitionRows = Object.entries(stats.stateTransitions.byClassification)
  return (
    <article className="space-y-3 py-3" aria-label="Inspectable transition leverage">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-[0.15em] text-ink">Transition leverage</h3>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-ink-dim">A possession-backed outcome ladder. Each action is shown in sequence; proximity to a goal is not treated as causation.</p>
        </div>
        <EventMapViewTabs
          value={mode}
          onChange={setMode}
          label="Transition leverage display"
          options={[{ value: 'rate', label: 'Rate' }, { value: 'count', label: 'Count' }]}
        />
      </div>
      <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-y border-line-bright py-2">
        <p className="text-[10px] uppercase tracking-[0.1em] text-ink-dim">Possession opportunities <strong className="ml-1 font-mono text-[15px] font-normal text-ink">{stats.opportunities.toLocaleString()}</strong></p>
        <p className="text-[10px] uppercase tracking-[0.1em] text-ink-dim">State changes <strong className="ml-1 font-mono text-[15px] font-normal text-ink">{stats.stateTransitions.count.toLocaleString()}</strong></p>
        <div className="ml-auto"><ScopeEvidence payload={payload} /></div>
      </div>
      <div className="flex gap-4 border-b border-line-bright" role="group" aria-label="Transition leverage perspective">
        {(['attacking', 'concession'] as const).map(value => <button key={value} type="button" aria-pressed={direction === value} onClick={() => setDirection(value)} className={`border-b-2 px-1 py-2 text-[10px] uppercase tracking-[0.12em] ${direction === value ? (value === 'attacking' ? 'border-electric text-electric' : 'border-ember text-ember') : 'border-transparent text-ink-dim hover:text-ink'}`}>{value === 'attacking' ? 'Creation for' : 'Vulnerability against'}</button>)}
      </div>
      <Ladder stats={stats} mode={mode} direction={direction} />
      {transitionRows.length ? <div className="flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-dim">{transitionRows.map(([name, count]) => <span key={name}>{label(name)} <strong className="ml-1 font-mono font-normal text-ink">{count}</strong></span>)}</div> : null}
      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">Verified player involvement</summary>
        <div className="mt-2 space-y-2"><p>Rates use only team possession opportunities with an event inside that player’s verified on-pitch interval. Transfer/team spells stay separate; excluded or ambiguous intervals remain visible.</p><PlayerList players={payload.selected.playerInvolvement} /></div>
      </details>
      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">Inspect possession traces ({payload.selected.observations.length})</summary>
        <div className="mt-2"><ObservationList observations={payload.selected.observations} /></div>
      </details>
      {payload.comparison.enabled ? <p className="text-[10px] text-ink-dim">Comparison baseline is available; ladder deltas remain component-level and do not form a composite score.</p> : null}
    </article>
  )
}
