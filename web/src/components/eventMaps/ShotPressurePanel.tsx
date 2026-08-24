import { useState } from 'react'
import type {
  ShotPressurePenaltyMode,
  ShotPressureSurfaceCell,
  TeamShotPressurePayload,
} from '../../types/eventMaps'
import { EventMapNotice, EventMetricStrip } from './EventMapUi'

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

function rate(value: number | null) {
  return value == null ? '—' : value.toFixed(2)
}

function Evidence({ payload }: { payload: TeamShotPressurePayload }) {
  const evidence = payload.selected.evidence
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 border-y border-line-bright py-2 font-mono text-[9px] text-ink-dim">
      <span>{evidence.exposureMinutes.toLocaleString()} evidence min</span>
      <span>{evidence.episodeCount.toLocaleString()} episodes</span>
      <span>{evidence.matchCount.toLocaleString()} matches</span>
      <span>{evidence.zeroShotEpisodesFor.toLocaleString()} zero-shot-for episodes</span>
      <span>{evidence.zeroShotEpisodesAgainst.toLocaleString()} zero-shot-against episodes</span>
      <span>{evidence.matchesExcluded.toLocaleString()} excluded matches</span>
      {Object.entries(evidence.exclusionReasons).map(([reason, count]) => (
        <span key={reason}>{reason.replaceAll('_', ' ')}: {count}</span>
      ))}
    </div>
  )
}

type DeltaCell = { column: number; row: number; shotsPer90Delta: number | null }

function RateSurface({ cells, delta = false }: {
  cells: Array<ShotPressureSurfaceCell | DeltaCell>
  delta?: boolean
}) {
  const cellValue = (cell: ShotPressureSurfaceCell | DeltaCell) =>
    delta && 'shotsPer90Delta' in cell ? cell.shotsPer90Delta : 'shotsPer90' in cell ? cell.shotsPer90 : null
  const maximum = Math.max(0.01, ...cells.map(cell => Math.abs(cellValue(cell) ?? 0)))
  return (
    <div className="relative aspect-[1.5/1] overflow-hidden border border-line-bright bg-[#07140f] p-2" aria-label={delta ? 'Shot rate State Delta Map' : 'Shot rate pitch-zone surface'}>
      <div className="pointer-events-none absolute inset-x-1/2 top-0 h-full w-px bg-white/20" />
      <div className="pointer-events-none absolute right-0 top-1/4 h-1/2 w-[16%] border border-white/20" />
      <div className="relative grid h-full grid-cols-6 grid-rows-4 gap-px">
        {cells.map(cell => {
          const value = cellValue(cell)
          const intensity = value == null ? 0 : Math.min(0.85, 0.12 + Math.abs(value) / maximum * 0.73)
          const colour = delta && (value ?? 0) < 0 ? `rgba(56, 189, 248, ${intensity})` : `rgba(250, 204, 21, ${intensity})`
          return <div key={`${cell.column}-${cell.row}`} title={value == null ? 'No exposure' : `${value.toFixed(2)} shots/90${delta ? ' delta' : ''}`} style={{ backgroundColor: colour }} />
        })}
      </div>
    </div>
  )
}

function BreakdownTable({ payload, perspective }: { payload: TeamShotPressurePayload; perspective: 'for' | 'against' }) {
  const frequency = payload.selected.frequency[perspective]
  const outcomes = payload.selected.outcomes[perspective]
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <div><h4 className="mb-1 text-[9px] font-bold uppercase tracking-[0.14em] text-ink">Frequency</h4><div className="space-y-1 font-mono text-[9px] text-ink-dim">
        {BREAKDOWNS.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><span>{label}</span><span>{frequency[key]?.count ?? 0} · {rate(frequency[key]?.per90 ?? null)}/90</span></div>)}
      </div></div>
      <div><h4 className="mb-1 text-[9px] font-bold uppercase tracking-[0.14em] text-ink">Observed outcomes</h4><div className="space-y-1 font-mono text-[9px] text-ink-dim">
        {OUTCOMES.map(([key, label]) => <div key={key} className="flex justify-between gap-3"><span>{label}</span><span>{outcomes[key]?.count ?? 0} · {rate(outcomes[key]?.per90 ?? null)}/90</span></div>)}
      </div></div>
    </div>
  )
}

export function ShotPressurePanel({ payload, loading, error, penaltyMode, onPenaltyModeChange, onRetry }: {
  payload?: TeamShotPressurePayload
  loading: boolean
  error?: string
  penaltyMode: ShotPressurePenaltyMode
  onPenaltyModeChange: (mode: ShotPressurePenaltyMode) => void
  onRetry: () => void
}) {
  const [perspective, setPerspective] = useState<'for' | 'against'>('for')
  if (loading) return <EventMapNotice kind="loading" title="Loading state-conditioned shot pressure" />
  if (error || !payload) return <EventMapNotice kind="error" title="Shot pressure failed to load" onRetry={onRetry}>{error}</EventMapNotice>
  const cohort = payload.selected
  const first = cohort.firstShot[perspective]
  return (
    <article className="border border-line-bright bg-panel p-3" aria-label="State-conditioned shot pressure">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div><h3 className="text-xs font-bold uppercase tracking-[0.14em] text-ink">Shot pressure</h3><p className="mt-1 max-w-3xl text-[9px] leading-relaxed text-ink-dim">Shots per state minute, with frequency, location and observed outcome kept separate.</p></div>
        <label className="text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim">Penalties<select className="event-lens-control mt-1 block" aria-label="Shot pressure penalty treatment" value={penaltyMode} onChange={event => onPenaltyModeChange(event.target.value as ShotPressurePenaltyMode)}><option value="exclude">Exclude (tactical default)</option><option value="include">Include</option><option value="only">Penalties only</option></select></label>
      </div>
      <EventMetricStrip metrics={[
        { label: 'Shots for / min', value: rate(cohort.frequency.for.shots.perMinute) },
        { label: 'Shots against / min', value: rate(cohort.frequency.against.shots.perMinute) },
        { label: 'Match openness / 90', value: rate(cohort.frequency.openness.shotsPer90) },
      ]} />
      <div className="my-3"><Evidence payload={payload} /></div>
      <div className="mb-3 flex gap-1" role="group" aria-label="Shot pressure perspective">{(['for', 'against'] as const).map(value => <button key={value} type="button" aria-pressed={perspective === value} onClick={() => setPerspective(value)} className={`event-lens-control ${perspective === value ? 'border-electric text-electric' : ''}`}>Shots {value}</button>)}</div>
      <div className="grid gap-3 lg:grid-cols-[minmax(260px,0.8fr)_minmax(300px,1.2fr)]">
        <div><RateSurface cells={cohort.location[perspective].cells} /><p className="mt-1 font-mono text-[8px] text-ink-dim">Gold = shots/90 in fixed 6×4 zones · {cohort.location[perspective].unlocatedShots} unlocated</p>{payload.comparison.locationDelta ? <div className="mt-3"><RateSurface cells={payload.comparison.locationDelta[perspective]} delta /><p className="mt-1 font-mono text-[8px] text-ink-dim">State Delta Map: gold higher, blue lower than baseline. Zone-rate subtraction only.</p></div> : null}</div>
        <div className="space-y-3"><BreakdownTable payload={payload} perspective={perspective} /><div className="border-t border-line-bright pt-2 text-[9px] text-ink-dim"><strong className="text-ink">First shot from state entry:</strong> mean {first.meanSecondsFromStateEntry == null ? '—' : `${first.meanSecondsFromStateEntry}s`}, median {first.medianSecondsFromStateEntry == null ? '—' : `${first.medianSecondsFromStateEntry}s`} · {first.zeroShotEpisodes} zero-shot episodes.</div><div className="space-y-1 border-t border-line-bright pt-2 text-[8px] leading-relaxed text-ink-dim"><p>{payload.penaltyNote}</p><p>{payload.fastBreakNote}</p><p>{payload.measurementNote}</p></div></div>
      </div>
    </article>
  )
}
