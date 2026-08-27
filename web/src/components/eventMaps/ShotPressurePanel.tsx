import { useState } from 'react'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import { buildDeltaCell, buildDeltaGrid, type StateDeltaMapContract } from '../../lib/eventMaps/deltaMap'
import type { ShotPressureMetric, TeamShotPressurePayload } from '../../types/eventMaps'
import { EventMapCard, EventMapNotice, EventPitchStage } from './EventMapUi'
import { StateDeltaMap } from './StateDeltaMap'

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
      unit: 'shots / 90 state min',
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
  const frequency = payload.selected.frequency[perspective]
  const outcomes = payload.selected.outcomes[perspective]
  return (
    <div className="grid gap-y-4 sm:grid-cols-2 sm:gap-x-12">
      <div>
        <h4 className="mb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-ink">Frequency</h4>
        <div className="space-y-1.5 font-mono text-[11px] text-ink-dim">
          {BREAKDOWNS.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><span>{label}</span><span>{metricValue(frequency[key], displayMode)}</span></div>)}
        </div>
      </div>
      <div>
        <h4 className="mb-1 text-[10px] font-bold uppercase tracking-[0.14em] text-ink">Observed outcomes</h4>
        <div className="space-y-1.5 font-mono text-[11px] text-ink-dim">
          {OUTCOMES.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><span>{label}</span><span>{metricValue(outcomes[key], displayMode)}</span></div>)}
        </div>
      </div>
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
        {deltaContract ? (
          <EventMapCard
            title={`Shots ${perspective} territory delta`}
            description="Compare state-minute shot territory without subtracting individual shot markers."
            expanded={expanded}
            onExpandedChange={onExpandedChange}
            exportContext={{
              ...exportContext,
              filters: [
                ...exportContext.filters,
                { label: 'Shot perspective', value: perspective === 'for' ? 'Shots for' : 'Shots against' },
                { label: 'Display', value: displayMode === 'per90' ? 'Per 90 state minutes' : 'Total supporting statistics' },
              ],
            }}
          >
            <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
              <StateDeltaMap contract={deltaContract} compact />
            </EventPitchStage>
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
