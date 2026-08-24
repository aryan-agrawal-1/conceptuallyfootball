import { useState } from 'react'
import type {
  ShotPressurePenaltyMode,
  ShotPressureSurfaceCell,
  TeamShotPressurePayload,
} from '../../types/eventMaps'
import { EventMapNotice } from './EventMapUi'

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
    <div className="flex flex-wrap gap-x-3 gap-y-1 font-mono text-[8px] text-ink-dim">
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
          return <div key={`${cell.column}-${cell.row}`} className="flex items-center justify-center font-mono text-[8px] text-white/80" title={value == null ? 'No exposure' : `${value.toFixed(2)} shots/90${delta ? ' delta' : ''}`} style={{ backgroundColor: colour }}>{value == null ? '—' : Math.abs(value) >= 0.05 ? value.toFixed(1) : ''}</div>
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
    <article className="border-y border-line-bright py-3" aria-label="State-conditioned shot pressure">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-3">
        <div><h3 className="text-xs font-bold uppercase tracking-[0.14em] text-ink">Shot tempo & territory</h3><p className="mt-1 max-w-3xl text-[9px] leading-relaxed text-ink-dim">How often shots happen in this state, where they originate, and what happened to them.</p></div>
        <select className="event-lens-control w-auto min-w-44" aria-label="Shot pressure penalty treatment" value={penaltyMode} onChange={event => onPenaltyModeChange(event.target.value as ShotPressurePenaltyMode)}><option value="exclude">Excluding penalties</option><option value="include">Including penalties</option><option value="only">Penalties only</option></select>
      </div>
      <div className="mb-2 flex flex-wrap items-baseline gap-x-6 gap-y-1 border-y border-line-bright py-2">
        {[['Shots for / 90', cohort.frequency.for.shots.per90], ['Shots against / 90', cohort.frequency.against.shots.per90], ['Combined shots / 90', cohort.frequency.openness.shotsPer90]].map(([label, value]) => <p key={label as string} className="text-[8px] uppercase tracking-[0.1em] text-ink-dim">{label} <strong className="ml-1 font-mono text-[13px] font-normal text-ink">{rate(value as number | null)}</strong></p>)}
        <div className="ml-auto"><Evidence payload={payload} /></div>
      </div>
      <div className="mb-2 flex gap-4 border-b border-line-bright" role="group" aria-label="Shot pressure perspective">{(['for', 'against'] as const).map(value => <button key={value} type="button" aria-pressed={perspective === value} onClick={() => setPerspective(value)} className={`border-b-2 px-1 py-2 text-[9px] uppercase tracking-[0.12em] ${perspective === value ? 'border-electric text-electric' : 'border-transparent text-ink-dim hover:text-ink'}`}>Shots {value}</button>)}</div>
      <div className="grid gap-3 lg:grid-cols-[minmax(260px,0.8fr)_minmax(300px,1.2fr)]">
        <div><RateSurface cells={cohort.location[perspective].cells} /><p className="mt-1 font-mono text-[8px] text-ink-dim">Each cell shows shots per 90 state minutes · brighter gold means more frequent · {cohort.location[perspective].unlocatedShots} unlocated</p>{payload.comparison.locationDelta ? <div className="mt-3"><RateSurface cells={payload.comparison.locationDelta[perspective]} delta /><p className="mt-1 font-mono text-[8px] text-ink-dim">State Delta Map: gold higher, blue lower than baseline. Zone-rate subtraction only.</p></div> : null}</div>
        <div className="space-y-3"><BreakdownTable payload={payload} perspective={perspective} /><div className="border-t border-line-bright pt-2 text-[9px] text-ink-dim"><strong className="text-ink">Time to first shot:</strong> mean {first.meanSecondsFromStateEntry == null ? '—' : `${first.meanSecondsFromStateEntry}s`}, median {first.medianSecondsFromStateEntry == null ? '—' : `${first.medianSecondsFromStateEntry}s`} · {first.zeroShotEpisodes} state episodes had no shot.</div><details className="border-t border-line-bright pt-2 text-[8px] leading-relaxed text-ink-dim"><summary className="text-control-fg hover:text-ink">Method & evidence notes</summary><div className="mt-2 space-y-1"><p>{payload.penaltyNote}</p><p>{payload.fastBreakNote}</p><p>{payload.measurementNote}</p><p>{cohort.evidence.zeroShotEpisodesFor} zero-shot-for episodes · {cohort.evidence.zeroShotEpisodesAgainst} zero-shot-against episodes</p></div></details></div>
      </div>
    </article>
  )
}
