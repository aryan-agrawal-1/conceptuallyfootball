import { useQueries, useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchTeamPassState, type StateLensRequest } from '../../lib/eventMaps/api'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type { PassStateCategory, TeamPassFlow } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import { EventMapCard, EventMapNotice, EventPitchStage } from './EventMapUi'

const COMPARISON_STATES = [
  { value: 'winning', label: 'Winning', color: '#1FD17C', lane: -1 },
  { value: 'drawing', label: 'Drawing', color: '#4A9EF5', lane: 0 },
  { value: 'losing', label: 'Losing', color: '#EF5C66', lane: 1 },
] as const

function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function metres(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}m`
}

function EvidenceBands({ title, rows }: { title: string; rows: PassStateCategory[] }) {
  return (
    <div>
      <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">{title}</p>
      <div className="grid grid-cols-3 gap-2">
        {rows.map(row => (
          <div key={row.category} className="rounded border border-line/60 bg-paper/40 px-2 py-1.5">
            <p className="text-[10px] font-bold uppercase text-ink-dim">{row.category}</p>
            <p className="font-mono text-[12px] text-ink">{percent(row.attemptShare)} choice</p>
            <p className="whitespace-nowrap font-mono text-[11px] text-ink-dim">{percent(row.completionRate)} completion</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function TeamPassStateFlow({
  teamId,
  teamName,
  competition,
  season,
  matchRef,
  stateLens,
  exportContext,
  expanded,
  onExpandedChange,
}: {
  teamId: number
  teamName: string
  competition: string
  season: string
  matchRef: string | null
  stateLens: StateLensRequest
  exportContext: EventMapExportContext
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
}) {
  const [selectedFlow, setSelectedFlow] = useState<TeamPassFlow | null>(null)
  const [comparisonEnabled, setComparisonEnabled] = useState(false)
  const query = useQuery({
    queryKey: ['team-pass-state', teamId, competition, season, matchRef, stateLens],
    queryFn: () => fetchTeamPassState(teamId, competition, season, matchRef, stateLens),
    staleTime: 10 * 60 * 1000,
  })
  const comparisonLens = Object.fromEntries(
    Object.entries(stateLens).filter(([key]) => (
      key !== 'state'
      && key !== 'goal_difference'
      && key !== 'draw_provenance'
      && !key.startsWith('baseline_')
    )),
  )
  const comparisonQueries = useQueries({
    queries: COMPARISON_STATES.map(state => {
      const lens = { ...comparisonLens, state: state.value }
      return {
        queryKey: ['team-pass-state', teamId, competition, season, matchRef, lens],
        queryFn: () => fetchTeamPassState(teamId, competition, season, matchRef, lens),
        staleTime: 10 * 60 * 1000,
        enabled: comparisonEnabled,
      }
    }),
  })
  const evidence = query.data?.selected

  if (query.isLoading) return <EventMapNotice kind="loading" title="Loading state passing evidence" />
  if (query.isError || !evidence) {
    return <EventMapNotice kind="error" title="State passing evidence failed to load" onRetry={() => query.refetch()}>
      {query.error?.message ?? 'The pass-state service returned no data.'}
    </EventMapNotice>
  }

  const summary = evidence.summary
  const comparisons = COMPARISON_STATES.map((state, index) => ({
    ...state,
    evidence: comparisonQueries[index].data?.selected,
    loading: comparisonQueries[index].isLoading,
    error: comparisonQueries[index].isError,
  }))
  const comparisonFlows = comparisons.flatMap(state => (
    state.evidence?.flows.map(flow => ({
      ...flow,
      id: `${state.value}-${flow.id}`,
      gameState: state.value,
      color: state.color,
      comparisonLane: state.lane,
    })) ?? []
  ))
  const hasComparison = comparisonEnabled && comparisonFlows.length > 0
  const visibleFlows = hasComparison ? comparisonFlows : evidence.flows
  const disclosure = [
    evidence.evidence.sparse ? 'Sparse cohort' : null,
    evidence.evidence.truncated ? `Capped at ${summary.attempts.toLocaleString()} located passes` : null,
    evidence.evidence.excludedMissingCoordinates
      ? `${evidence.evidence.excludedMissingCoordinates.toLocaleString()} passes excluded for missing coordinates`
      : null,
  ].filter(Boolean).join(' · ')

  return (
    <EventMapCard
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      title="Pass flow by game state"
      description={comparisonEnabled
        ? 'Compare winning, drawing and losing pass direction in the same origin zones; selected-state evidence remains separate.'
        : 'Attempt volume and mean pass shape in each origin zone for the selected State Lens.'}
      controls={(
        <button
          type="button"
          aria-pressed={comparisonEnabled}
          onClick={() => {
            setSelectedFlow(null)
            setComparisonEnabled(enabled => !enabled)
          }}
          className={`h-8 whitespace-nowrap border px-2.5 text-[9px] font-bold uppercase tracking-[0.08em] transition-colors ${comparisonEnabled ? 'border-electric bg-electric/10 text-electric' : 'border-control-border bg-raised text-control-fg hover:border-electric hover:text-ink'}`}
        >
          Compare states
        </button>
      )}
      exportContext={{
        ...exportContext,
        filters: [
          ...exportContext.filters,
          comparisonEnabled
            ? { label: 'Pitch comparison', value: 'Winning · Drawing · Losing' }
            : { label: 'Pitch view', value: 'Selected state only' },
        ],
      }}
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        <div className="grid w-full items-start gap-8 lg:grid-cols-[minmax(0,1.45fr)_minmax(400px,0.75fr)]">
          <div>
            {visibleFlows.length ? (
              <PortraitPitch
                flows={visibleFlows}
                selectedFlowId={selectedFlow?.id ?? null}
                onSelectedFlowChange={setSelectedFlow}
                ariaLabel={comparisonEnabled
                  ? `${teamName} pass flow by game state. Green arrows show winning, blue arrows show drawing and red arrows show losing; origin shade shows combined state-minute pass volume.`
                  : `${teamName} selected-state pass flow. Origin shade shows attempted pass volume; arrows show attempted mean direction and length.`}
              />
            ) : <EventMapNotice kind="empty" title="No located passes in this state scope" />}
            {comparisonEnabled ? <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2" aria-label="Pass-flow game-state legend">
              {comparisons.map(state => (
                <span key={state.value} className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">
                  <span className="relative h-2 w-5" style={{ color: state.color }} aria-hidden="true">
                    <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-current" />
                    <span className="absolute right-0 top-1/2 size-1.5 -translate-y-1/2 rotate-45 border-r border-t border-current" />
                  </span>
                  {state.label}
                  {state.loading ? <span className="font-normal normal-case tracking-normal">loading</span> : null}
                  {state.error ? <span className="font-normal normal-case tracking-normal text-gold">unavailable</span> : null}
                </span>
              ))}
            </div> : null}
          </div>
          <aside className="space-y-4 border-t border-line-bright pt-5 lg:border-t-0 lg:pt-0" aria-label="Passing evidence">
            {comparisonEnabled ? <div>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">Game-state comparison</p>
              <div className="grid grid-cols-3 gap-2">
                {comparisons.map(state => (
                  <div key={state.value} className="border border-line/60 bg-paper/40 px-2 py-2" style={{ borderTopColor: state.color }}>
                    <p className="text-[9px] font-bold uppercase tracking-[0.08em]" style={{ color: state.color }}>{state.label}</p>
                    <p className="mt-1 font-mono text-[13px] text-ink">{state.evidence?.summary.attemptsPerStateMinute?.toFixed(2) ?? '—'}</p>
                    <p className="text-[9px] text-ink-dim">passes/min</p>
                    <p className="mt-1 font-mono text-[10px] text-ink-dim">{state.evidence ? percent(state.evidence.summary.completionRate) : '—'}</p>
                    <p className="text-[9px] text-ink-dim">completion</p>
                    <p className="mt-1 text-[9px] text-ink-muted">{state.evidence ? `${state.evidence.exposureMinutes.toFixed(0)} min` : '—'}</p>
                  </div>
                ))}
              </div>
            </div> : null}
            <p className="text-[10px] leading-relaxed text-ink-dim">{comparisonEnabled
              ? 'Each arrow shows the attempted mean direction and length for its state. Zone shading combines passes per eligible state minute, not raw totals.'
              : 'Each arrow shows attempted mean direction and length. Brighter origin zones represent more attempted passes in the selected state.'}</p>
            {comparisonEnabled && (stateLens.goal_difference || stateLens.draw_provenance) ? (
              <p className="text-[10px] leading-relaxed text-gold">Exact score and draw-provenance refinements apply to the selected evidence below; the three-state comparison uses the shared match, phase and state-age scope.</p>
            ) : null}
            <div className="grid grid-cols-3 gap-3 text-[12px] leading-relaxed lg:grid-cols-1">
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Passes per minute</span>{summary.attemptsPerStateMinute?.toFixed(2) ?? '—'}</p>
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Pass completion</span>{percent(summary.completionRate)}</p>
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Mean pass length</span>{metres(summary.meanLengthMetres)}</p>
            </div>
            <EvidenceBands title="Direction" rows={evidence.directions} />
            <EvidenceBands title="Length" rows={evidence.lengthBands} />
            <p className="text-[11px] leading-relaxed text-ink-dim">
              Passes per minute uses only the eligible minutes in the selected game state. {summary.attempts.toLocaleString()} attempted · {summary.completions.toLocaleString()} completed · {evidence.exposureMinutes.toFixed(1)} eligible minutes
              {disclosure ? ` · ${disclosure}` : ''}
            </p>
          </aside>
        </div>
      </EventPitchStage>
    </EventMapCard>
  )
}
