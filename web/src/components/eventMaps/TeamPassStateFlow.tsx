import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchTeamPassState } from '../../lib/eventMaps/stateAnalysisApi'
import type { StateLensRequest } from '../../lib/eventMaps/stateLensApi'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import {
  buildDeltaCell,
  buildDeltaGrid,
  type StateDeltaMapContract,
} from '../../lib/eventMaps/deltaMap'
import type {
  PassStateCategory,
  StateLensEvidence,
  StateLensMetadata,
  TeamPassFlow,
  TeamPassStateEvidence,
} from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import { EventMapCard, EventMapNotice, EventPitchStage } from './EventMapUi'
import { StateDeltaMap } from './StateDeltaMap'
import { statePresentation } from '../../lib/eventMaps/statePresentation'

function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function metres(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}m`
}

function comparisonGameState(value: string): TeamPassFlow['gameState'] {
  return value === 'winning' || value === 'drawing' || value === 'losing'
    ? value
    : undefined
}

function labelForState(value: string) {
  return value === 'all'
    ? 'All states'
    : value.replace(/^./, character => character.toUpperCase())
}

function lensScopeLabel(scope: StateLensMetadata['selected'] | null | undefined) {
  if (!scope) return null
  const label = labelForState(scope.state)
  const qualifiers = [
    scope.goalDifference == null ? null : `GD ${scope.goalDifference > 0 ? '+' : ''}${scope.goalDifference}`,
    scope.phase?.replaceAll('_', ' '),
    scope.drawProvenance && scope.drawProvenance !== 'none' ? scope.drawProvenance : null,
  ].filter(Boolean)
  return qualifiers.length ? `${label} · ${qualifiers.join(' · ')}` : label
}

function passReliability(evidence: TeamPassStateEvidence, lensEvidence?: StateLensEvidence) {
  if (evidence.evidence.empty || lensEvidence?.empty) return 'unavailable' as const
  if (evidence.evidence.sparse) return 'sparse' as const
  if (lensEvidence?.matchesExcluded) return 'partial' as const
  return 'verified' as const
}

function passCohortEvidence(
  label: string,
  evidence: TeamPassStateEvidence,
  lensEvidence?: StateLensEvidence,
) {
  const excludedCoordinates = evidence.evidence.excludedMissingCoordinates
  return {
    label,
    exposureMinutes: lensEvidence?.exposureMinutes ?? evidence.exposureMinutes,
    matchCount: lensEvidence?.matchCount ?? null,
    episodeCount: lensEvidence?.episodeCount ?? null,
    eventCount: evidence.evidence.sourcePassEvents,
    locatedEventCount: Math.max(0, evidence.evidence.sourcePassEvents - excludedCoordinates),
    excludedEventCount: excludedCoordinates,
    excludedMatchCount: lensEvidence?.matchesExcluded ?? null,
    exclusions: {
      missing_coordinates: excludedCoordinates,
      ...(lensEvidence?.exclusionReasons ?? {}),
    },
    reliability: passReliability(evidence, lensEvidence),
  }
}

function passDeltaContract(
  teamId: number,
  teamName: string,
  selected: TeamPassStateEvidence,
  baseline: TeamPassStateEvidence,
  stateLens: StateLensRequest,
  stateLensMetadata?: StateLensMetadata,
): StateDeltaMapContract {
  const selectedFlows = new Map(selected.flows.map(flow => [`${flow.bin.column}:${flow.bin.row}`, flow]))
  const baselineFlows = new Map(baseline.flows.map(flow => [`${flow.bin.column}:${flow.bin.row}`, flow]))
  const selectedLabel = lensScopeLabel(stateLensMetadata?.selected) ?? labelForState(stateLens.state ?? 'all')
  const baselineLabel = lensScopeLabel(stateLensMetadata?.comparison.baseline) ?? labelForState(stateLens.baseline_state ?? 'all')
  const cells = []
  const rates: number[] = []
  for (let row = 0; row < 4; row += 1) {
    for (let column = 0; column < 6; column += 1) {
      const key = `${column}:${row}`
      const selectedFlow = selectedFlows.get(key)
      const baselineFlow = baselineFlows.get(key)
      const selectedValue = selectedFlow
        ? selectedFlow.attemptsPerStateMinute ?? null
        : selected.exposureMinutes > 0 ? 0 : null
      const baselineValue = baselineFlow
        ? baselineFlow.attemptsPerStateMinute ?? null
        : baseline.exposureMinutes > 0 ? 0 : null
      if (selectedValue != null) rates.push(selectedValue)
      if (baselineValue != null) rates.push(baselineValue)
      cells.push(buildDeltaCell({
        column,
        row,
        selectedValue,
        baselineValue,
        selectedRawCount: selectedFlow?.attemptedCount ?? 0,
        baselineRawCount: baselineFlow?.attemptedCount ?? 0,
        selectedSupported: selectedValue != null,
        baselineSupported: baselineValue != null,
        selectedSparse: selected.evidence.sparse,
        baselineSparse: baseline.evidence.sparse,
        selectedVector: selectedFlow ? {
          origin: selectedFlow.origin,
          destination: selectedFlow.destination,
          meanLengthMetres: selectedFlow.meanLength,
          eventCount: selectedFlow.attemptedCount,
        } : undefined,
        baselineVector: baselineFlow ? {
          origin: baselineFlow.origin,
          destination: baselineFlow.destination,
          meanLengthMetres: baselineFlow.meanLength,
          eventCount: baselineFlow.attemptedCount,
        } : undefined,
      }))
    }
  }
  const selectedLensEvidence = stateLensMetadata?.evidence
  const baselineLensEvidence = stateLensMetadata?.comparison.baselineEvidence ?? undefined
  return {
    contractVersion: 'state-delta-map/team-pass-flow/v1',
    subject: { type: 'team', id: teamId, name: teamName },
    metric: {
      label: 'Pass origin-volume delta',
      unit: 'passes / state min',
      mode: 'absolute-rate',
      smoothing: 'none',
      description: 'Origin volume is compared per eligible State Lens minute. Arrows retain each cohort’s own mean direction and length; vectors are never subtracted.',
      domain: Math.max(0.01, ...rates),
    },
    selected: passCohortEvidence(selectedLabel, selected, selectedLensEvidence),
    baseline: passCohortEvidence(baselineLabel, baseline, baselineLensEvidence),
    grid: buildDeltaGrid({ columns: 6, rows: 4, cells }),
    notes: [
      'A missing origin bin is a zero-rate bin when the cohort has supplied exposure; it is not a missing event total.',
      'Raw attempted and located event counts stay visible beside the normalised rate.',
    ],
  }
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
            <p className="font-mono text-[11px] leading-snug text-ink-dim">{percent(row.completionRate)} completion</p>
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
  stateLensMetadata,
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
  stateLensMetadata?: StateLensMetadata
  exportContext: EventMapExportContext
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
}) {
  const [selectedFlowBin, setSelectedFlowBin] = useState<string | null>(null)
  const comparisonEnabled = Object.keys(stateLens).some(key => key.startsWith('baseline_'))
  const query = useQuery({
    queryKey: ['team-pass-state', teamId, competition, season, matchRef, stateLens],
    queryFn: () => fetchTeamPassState(teamId, competition, season, matchRef, stateLens),
    staleTime: 10 * 60 * 1000,
  })
  const payload = query.data
  const evidence = payload?.selected

  if (query.isLoading) return <EventMapNotice kind="loading" title="Loading state passing evidence" />
  if (query.isError || !payload || !evidence) {
    return <EventMapNotice kind="error" title="State passing evidence failed to load" onRetry={() => query.refetch()}>
      {query.error?.message ?? 'The pass-state service returned no data.'}
    </EventMapNotice>
  }

  const summary = evidence.summary
  const selectedState = stateLens.state ?? 'all'
  const baselineState = stateLens.baseline_state ?? 'all'
  const comparisons = [
    { key: 'selected', state: selectedState, label: labelForState(selectedState), color: statePresentation(selectedState).color, lane: -1, evidence },
    { key: 'baseline', state: baselineState, label: labelForState(baselineState), color: statePresentation(baselineState).color, lane: 1, evidence: payload.baseline },
  ]
  const comparisonFlows = comparisons.flatMap(cohort => (
    cohort.evidence?.flows.map(flow => ({
      ...flow,
      id: `${cohort.key}-${flow.id}`,
      gameState: comparisonGameState(cohort.state),
      color: cohort.color,
      comparisonLane: cohort.lane,
    })) ?? []
  ))
  const hasComparison = comparisonEnabled && comparisonFlows.length > 0
  const visibleFlows = hasComparison ? comparisonFlows : evidence.flows
  const deltaContract = comparisonEnabled && payload.baseline
    ? passDeltaContract(teamId, teamName, evidence, payload.baseline, stateLens, stateLensMetadata)
    : null
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
        ? `${labelForState(selectedState)} and ${labelForState(baselineState)} routes in their actual direction, using verified state exposure.`
        : 'Attempt volume and mean pass shape in each origin zone for the selected State Lens.'}
      exportContext={{
        ...exportContext,
        filters: [
          ...exportContext.filters,
          comparisonEnabled
            ? { label: 'Pitch comparison', value: `${labelForState(selectedState)} · ${labelForState(baselineState)} baseline` }
            : { label: 'Pitch view', value: 'Selected state only' },
        ],
      }}
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        <div className="w-full space-y-5">
          <div className="mx-auto w-full max-w-[1120px]">
            {comparisonEnabled && !payload.baseline ? (
              <EventMapNotice kind="unavailable" title="Baseline evidence unavailable">
                Select a valid baseline cohort with verified State Lens exposure before interpreting pass movement.
              </EventMapNotice>
            ) : visibleFlows.length ? (
              <PortraitPitch
                flows={visibleFlows}
                selectedFlowBin={selectedFlowBin}
                onSelectedFlowBinChange={setSelectedFlowBin}
                flowCohorts={comparisons.filter(cohort => comparisonEnabled || cohort.key === 'selected').map(cohort => ({ state: comparisonGameState(cohort.state), label: cohort.label, color: cohort.color }))}
                ariaLabel={comparisonEnabled
                  ? `${teamName} pass flow comparison. State-coloured arrows show actual ${labelForState(selectedState)} and ${labelForState(baselineState)} routes; arrowheads show direction.`
                  : `${teamName} selected-state pass flow. Origin shade shows attempted pass volume; arrows show attempted mean direction and length.`}
              />
            ) : <EventMapNotice kind="empty" title="No located passes in this state scope" />}
            {comparisonEnabled ? <div className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-2" aria-label="Pass-flow game-state legend">
              {comparisons.map(cohort => (
                <span key={cohort.key} className="inline-flex items-center gap-2 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">
                  <span className="relative h-2 w-5" style={{ color: cohort.color }} aria-hidden="true">
                    <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-current" />
                    <span className="absolute right-0 top-1/2 size-1.5 -translate-y-1/2 rotate-45 border-r border-t border-current" />
                  </span>
                  {cohort.label}{cohort.key === 'baseline' ? ' baseline' : ''}
                </span>
              ))}
            </div> : null}
            {deltaContract ? <details className="mt-3 border border-line-bright px-3 py-2 text-[9px] text-ink-dim"><summary className="cursor-pointer text-control-fg">Change evidence</summary><div className="mt-2"><StateDeltaMap contract={deltaContract} compact /></div></details> : null}
          </div>
          <aside className="space-y-4 border-t border-line-bright pt-5" aria-label="Passing evidence">
            {comparisonEnabled ? <>
              <div>
                <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">Game-state comparison</p>
                <div className="grid gap-3 xl:grid-cols-2">
                  {comparisons.map(cohort => (
                    <div key={cohort.key} className="border border-line/60 bg-paper/40 px-2 py-2" style={{ borderTopColor: cohort.color }}>
                      <p className="text-[9px] font-bold uppercase tracking-[0.08em]" style={{ color: cohort.color }}>{cohort.label}{cohort.key === 'baseline' ? ' baseline' : ''}</p>
                      <p className="mt-1 font-mono text-[13px] text-ink">{cohort.evidence?.summary.attemptsPerStateMinute?.toFixed(2) ?? '—'}<span className="ml-1 text-[9px] text-ink-dim">passes/min</span></p>
                      <div className="mt-1 grid gap-1 text-[9px] text-ink-dim sm:grid-cols-2">
                        <span>{cohort.evidence ? percent(cohort.evidence.summary.completionRate) : '—'} complete</span>
                        <span>{cohort.evidence ? metres(cohort.evidence.summary.meanLengthMetres) : '—'} avg length</span>
                      </div>
                      <p className="mt-1 text-[9px] text-ink-muted">{cohort.evidence ? `${cohort.evidence.exposureMinutes.toFixed(0)} min · ${cohort.evidence.summary.attempts.toLocaleString()} attempted` : '—'}</p>
                      {cohort.evidence ? <div className="mt-3 space-y-3 border-t border-line-bright pt-2">
                        <EvidenceBands title="Direction" rows={cohort.evidence.directions} />
                        <EvidenceBands title="Length" rows={cohort.evidence.lengthBands} />
                      </div> : null}
                    </div>
                  ))}
                </div>
              </div>
            </> : <>
              <p className="text-[10px] leading-relaxed text-ink-dim">Each arrow shows attempted mean direction and length. Brighter origin zones represent more attempted passes in the selected state.</p>
              <div className="grid grid-cols-3 gap-3 text-[12px] leading-relaxed">
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
            </>}
          </aside>
        </div>
      </EventPitchStage>
    </EventMapCard>
  )
}
