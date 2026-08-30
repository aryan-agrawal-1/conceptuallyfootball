import { useState } from 'react'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import { buildDeltaCell, buildDeltaGrid, type StateDeltaMapContract } from '../../lib/eventMaps/deltaMap'
import type { ShotPressureMetric, TeamShotPressurePayload } from '../../types/eventMaps'
import { EventMapCard, EventMapNotice, EventPitchStage } from './EventMapUi'
import { StateDeltaMap } from './StateDeltaMap'
import { PairedStatePitch } from './PairedStatePitch'
import type { ActionGridCell, PitchCoordinate, ShotPressureCohort } from '../../types/eventMaps'
import { statePresentation } from '../../lib/eventMaps/statePresentation'

const BREAKDOWNS = [
  ['open_play', 'Open play'],
  ['set_piece', 'Set piece'],
  ['penalty', 'Penalties'],
  ['provider_tagged_fast_break', 'Provider-tagged fast break'],
  ['big_chance', 'Big chance'],
  ['box', 'Box'],
  ['on_target', 'On target'],
] as const
const OUTCOMES = [
  ['goal', 'Goals'], ['saved', 'Saved'], ['blocked', 'Blocked'],
  ['off_target', 'Off target'], ['woodwork', 'Woodwork'],
] as const

type ShotDisplayMode = 'per90' | 'total'

function rate(value: number | null) {
  return value == null ? '—' : value.toFixed(2)
}

function metricValue(metric: ShotPressureMetric | undefined, mode: ShotDisplayMode) {
  if (mode === 'total') return metric?.count.toLocaleString() ?? '0'
  return rate(metric?.per90 ?? null)
}

function shotReliability(
  locatedShots: number,
  evidence: TeamShotPressurePayload['selected']['evidence'],
) {
  if (evidence.empty || !evidence.exposureMinutes) return 'unavailable' as const
  if (locatedShots < 5) return 'sparse' as const
  if (evidence.matchesExcluded) return 'partial' as const
  return 'verified' as const
}

function stateLabel(value: string | undefined) {
  if (!value || value === 'all') return 'All states'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function scopeLabel(scope: TeamShotPressurePayload['stateLens']['selected'] | null | undefined) {
  if (!scope) return 'All states'
  const qualifiers = [
    scope.goalDifference == null ? null : `GD ${scope.goalDifference > 0 ? '+' : ''}${scope.goalDifference}`,
    scope.phase?.replaceAll('_', ' '),
    scope.drawProvenance && scope.drawProvenance !== 'none' ? scope.drawProvenance : null,
  ].filter(Boolean)
  const label = stateLabel(scope.state)
  return qualifiers.length ? `${label} · ${qualifiers.join(' · ')}` : label
}

function shotDeltaContract(
  payload: TeamShotPressurePayload,
  perspective: 'for' | 'against',
): StateDeltaMapContract | null {
  const baseline = payload.comparison.baseline
  if (!payload.comparison.enabled || !baseline) return null
  const selectedSurface = payload.selected.location[perspective]
  const baselineSurface = baseline.location[perspective]
  const selectedLocated = selectedSurface.locatedShots
  const baselineLocated = baselineSurface.locatedShots
  const selectedExposure = payload.selected.evidence.exposureMinutes
  const baselineExposure = baseline.evidence.exposureMinutes
  const cells = []
  const rates: number[] = []
  for (let row = 0; row < selectedSurface.rows; row += 1) {
    for (let column = 0; column < selectedSurface.columns; column += 1) {
      // API rows use provider bottom-left order; the Delta Map uses display
      // top-down order shared by PortraitPitch and the other map surfaces.
      const selectedCell = selectedSurface.cells.find(value => value.column === column && value.row === selectedSurface.rows - 1 - row)
      const baselineCell = baselineSurface.cells.find(value => value.column === column && value.row === baselineSurface.rows - 1 - row)
      const selectedValue = selectedCell?.shotsPer90 ?? (selectedExposure > 0 ? 0 : null)
      const baselineValue = baselineCell?.shotsPer90 ?? (baselineExposure > 0 ? 0 : null)
      if (selectedValue != null) rates.push(selectedValue)
      if (baselineValue != null) rates.push(baselineValue)
      cells.push(buildDeltaCell({
        column,
        row,
        selectedValue,
        baselineValue,
        selectedRawCount: selectedCell?.shotCount ?? 0,
        baselineRawCount: baselineCell?.shotCount ?? 0,
        selectedSupported: selectedValue != null,
        baselineSupported: baselineValue != null,
        selectedSparse: selectedLocated < 5,
        baselineSparse: baselineLocated < 5,
      }))
    }
  }
  return {
    contractVersion: 'state-delta-map/team-shot-territory/v1',
    subject: { type: 'team', id: payload.teamId, name: payload.teamName },
    metric: {
      label: `Shots ${perspective} territory delta`,
      unit: 'normalized shot rate',
      mode: 'absolute-rate',
      smoothing: 'none',
      description: 'Zone rates compare the supplied exposure-normalised shot surface. Individual shot dots are intentionally not subtracted.',
      domain: Math.max(0.01, ...rates),
    },
    selected: {
      label: scopeLabel(payload.stateLens.selected),
      exposureMinutes: payload.selected.evidence.exposureMinutes,
      matchCount: payload.selected.evidence.matchCount,
      episodeCount: payload.selected.evidence.episodeCount,
      eventCount: payload.selected.frequency[perspective].shots.count,
      locatedEventCount: selectedLocated,
      excludedEventCount: selectedSurface.unlocatedShots,
      excludedMatchCount: payload.selected.evidence.matchesExcluded,
      exclusions: {
        ...payload.selected.evidence.exclusionReasons,
        missing_coordinates: selectedSurface.unlocatedShots,
      },
      reliability: shotReliability(selectedLocated, payload.selected.evidence),
    },
    baseline: {
      label: scopeLabel(payload.stateLens.comparison.baseline),
      exposureMinutes: baseline.evidence.exposureMinutes,
      matchCount: baseline.evidence.matchCount,
      episodeCount: baseline.evidence.episodeCount,
      eventCount: baseline.frequency[perspective].shots.count,
      locatedEventCount: baselineLocated,
      excludedEventCount: baselineSurface.unlocatedShots,
      excludedMatchCount: baseline.evidence.matchesExcluded,
      exclusions: {
        ...baseline.evidence.exclusionReasons,
        missing_coordinates: baselineSurface.unlocatedShots,
      },
      reliability: shotReliability(baselineLocated, baseline.evidence),
    },
    grid: buildDeltaGrid({ columns: selectedSurface.columns, rows: selectedSurface.rows, cells }),
    notes: [
      'Positive and negative cells compare shot rates for this perspective only; no individual shot marker is treated as a subtractable event.',
      payload.measurementNote,
    ],
  }
}

function shotPitchCohort(cohort: ShotPressureCohort, perspective: 'for' | 'against') {
  const surface = cohort.location[perspective]
  const cells: ActionGridCell[] = surface.cells.map(cell => ({
    column: cell.column,
    row: cell.row,
    rawCount: cell.shotCount,
    per90Count: cell.shotsPer90 ?? 0,
    share: cell.locationShare ?? 0,
  }))
  const total = cells.reduce((sum, cell) => sum + cell.rawCount, 0)
  const average: (PitchCoordinate & { sampleSize: number }) | null = total ? {
    x: cells.reduce((sum, cell) => sum + ((cell.column + 0.5) / surface.columns) * 100 * cell.rawCount, 0) / total,
    y: cells.reduce((sum, cell) => sum + ((cell.row + 0.5) / surface.rows) * 100 * cell.rawCount, 0) / total,
    sampleSize: total,
  } : null
  return { cells, average }
}

function Evidence({ payload }: { payload: TeamShotPressurePayload }) {
  const evidence = payload.selected.evidence
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-ink-dim">
      <span>{evidence.exposureMinutes.toLocaleString()} evidence min</span>
      <span>{evidence.episodeCount.toLocaleString()} episodes</span>
      <span>{evidence.matchCount.toLocaleString()} matches</span>
      {evidence.matchesExcluded ? <span className="text-gold">{evidence.matchesExcluded.toLocaleString()} excluded</span> : null}
      {Object.entries(evidence.exclusionReasons).map(([reason, count]) => (
        <span key={reason}>{reason.replaceAll('_', ' ')}: {count}</span>
      ))}
    </div>
  )
}

function BreakdownTable({ payload, perspective, displayMode }: {
  payload: TeamShotPressurePayload
  perspective: 'for' | 'against'
  displayMode: ShotDisplayMode
}) {
  const cohorts = [
    { label: scopeLabel(payload.stateLens.selected), state: payload.stateLens.selected.state, cohort: payload.selected },
    ...(payload.comparison.baseline ? [{ label: scopeLabel(payload.stateLens.comparison.baseline), state: payload.stateLens.comparison.baseline?.state ?? 'all', cohort: payload.comparison.baseline }] : []),
  ]
  return (
    <div className={`grid gap-3 ${cohorts.length > 1 ? 'sm:grid-cols-2' : ''}`}>
      {cohorts.map(item => {
        const presentation = statePresentation(item.state)
        const frequency = item.cohort.frequency[perspective]
        const outcomes = item.cohort.outcomes[perspective]
        return <section key={`${item.state}-${item.label}`} className="border border-line/60 bg-paper/40 px-3 py-2" style={{ borderTopColor: presentation.color }}>
          <h4 className="text-[9px] font-bold uppercase tracking-[0.1em]" style={{ color: presentation.color }}>{item.label}</h4>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <div>
              <p className="mb-1 text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim">Frequency</p>
              <div className="space-y-1.5 font-mono text-[10px] text-ink-dim">
                {BREAKDOWNS.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><span>{label}</span><span className="text-ink">{metricValue(frequency[key], displayMode)}</span></div>)}
              </div>
            </div>
            <div>
              <p className="mb-1 text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim">Observed outcomes</p>
              <div className="space-y-1.5 font-mono text-[10px] text-ink-dim">
                {OUTCOMES.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><span>{label}</span><span className="text-ink">{metricValue(outcomes[key], displayMode)}</span></div>)}
              </div>
            </div>
          </div>
        </section>
      })}
    </div>
  )
}

export function ShotPressurePanel({ payload, loading, error, onRetry, exportContext, expanded, onExpandedChange, rateMode }: {
  payload?: TeamShotPressurePayload
  loading: boolean
  error?: string
  onRetry: () => void
  exportContext: EventMapExportContext
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  rateMode: ProfileRateMode
}) {
  const [perspective, setPerspective] = useState<'for' | 'against'>('for')
  const displayMode: ShotDisplayMode = rateMode === 'per90' ? 'per90' : 'total'
  if (loading) return <EventMapNotice kind="loading" title="Loading state-conditioned shot pressure" />
  if (error || !payload) return <EventMapNotice kind="error" title="Shot pressure failed to load" onRetry={onRetry}>{error}</EventMapNotice>
  const cohort = payload.selected
  const first = cohort.firstShot[perspective]
  const deltaContract = shotDeltaContract(payload, perspective)
  const selectedPitch = shotPitchCohort(payload.selected, perspective)
  const baselinePitch = payload.comparison.baseline ? shotPitchCohort(payload.comparison.baseline, perspective) : null
  return (
    <article className="py-3" aria-label="State-conditioned shot pressure">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-ink">Shot tempo & territory</h3>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-ink-dim">How often shots happen in this state, where they originate, and what happened to them.</p>
        </div>
      </div>
      <div className="mb-3 py-1"><Evidence payload={payload} /></div>
      <div className="mb-2 flex gap-4 border-b border-line-bright" role="group" aria-label="Shot pressure perspective">
        {(['for', 'against'] as const).map(value => <button key={value} type="button" aria-pressed={perspective === value} onClick={() => setPerspective(value)} className={`border-b-2 px-1 py-2 text-[10px] uppercase tracking-[0.12em] ${perspective === value ? 'border-electric text-electric' : 'border-transparent text-ink-dim hover:text-ink'}`}>Shots {value}</button>)}
      </div>
      <div className="space-y-3">
        <BreakdownTable payload={payload} perspective={perspective} displayMode={displayMode} />
        {payload.comparison.baseline && baselinePitch ? (
          <EventMapCard
            title={`Shots ${perspective} territory comparison`}
            description="Paired state density with a shared scale; subtractive change remains secondary evidence."
            expanded={expanded}
            onExpandedChange={onExpandedChange}
            exportContext={{
              ...exportContext,
              filters: [
                ...exportContext.filters,
                { label: 'Shot perspective', value: perspective === 'for' ? 'Shots for' : 'Shots against' },
                { label: 'Display', value: displayMode === 'per90' ? 'Rate view' : 'Total supporting statistics' },
              ],
            }}
          >
            <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
              <PairedStatePitch
                selected={{ state: payload.stateLens.selected.state, label: scopeLabel(payload.stateLens.selected), cells: selectedPitch.cells, average: selectedPitch.average, exposureMinutes: payload.selected.evidence.exposureMinutes, matchCount: payload.selected.evidence.matchCount }}
                comparison={{ state: payload.stateLens.comparison.baseline?.state ?? 'all', label: scopeLabel(payload.stateLens.comparison.baseline), cells: baselinePitch.cells, average: baselinePitch.average, exposureMinutes: payload.comparison.baseline.evidence.exposureMinutes, matchCount: payload.comparison.baseline.evidence.matchCount }}
                unit="share of located shots"
                ariaLabel={`${payload.teamName} paired shots ${perspective} territory comparison`}
              />
            </EventPitchStage>
            {deltaContract ? <details className="border-t border-line-bright px-3 py-2 text-[9px] text-ink-dim"><summary className="cursor-pointer text-control-fg">Change evidence</summary><div className="mt-2"><StateDeltaMap contract={deltaContract} compact /></div></details> : null}
          </EventMapCard>
        ) : payload.comparison.enabled ? (
          <EventMapNotice kind="unavailable" title="Shot territory comparison unavailable">
            Select a valid baseline cohort with verified State Lens exposure before interpreting shot territory change.
          </EventMapNotice>
        ) : null}
        <div className="bg-raised/40 px-3 py-2 text-[11px] leading-relaxed text-ink-dim">
          <strong className="text-ink">Time to first shot:</strong> mean {first.meanSecondsFromStateEntry == null ? '—' : `${first.meanSecondsFromStateEntry}s`}, median {first.medianSecondsFromStateEntry == null ? '—' : `${first.medianSecondsFromStateEntry}s`} · {first.zeroShotEpisodes} state episodes had no shot · {cohort.location[perspective].unlocatedShots} unlocated shots.
        </div>
        <details className="px-1 py-1 text-[10px] leading-relaxed text-ink-dim">
          <summary className="text-control-fg hover:text-ink">Method & evidence notes</summary>
          <div className="mt-2 space-y-1"><p>{payload.penaltyNote}</p><p>{payload.fastBreakNote}</p><p>{payload.measurementNote}</p><p>{cohort.evidence.zeroShotEpisodesFor} zero-shot-for episodes · {cohort.evidence.zeroShotEpisodesAgainst} zero-shot-against episodes</p></div>
        </details>
      </div>
    </article>
  )
}
