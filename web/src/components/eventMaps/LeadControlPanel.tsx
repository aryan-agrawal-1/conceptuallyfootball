import { useMemo, useState } from 'react'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import type { LeadControlMetric, LeadControlPayload, LeadControlSurface } from '../../types/leadControl'
import { EventMapNotice } from './EventMapUi'

type LeadBandMode = 'all' | 'oneGoal' | 'multiGoal'
type ComponentGroup = 'gravity' | 'ownership'

const GRAVITY_ROWS: Array<{ key: keyof LeadControlSurface['gravity']['components']; label: string }> = [
  { key: 'touchOriginHeight', label: 'Average touch position' },
  { key: 'passOriginHeight', label: 'Average pass position' },
  { key: 'defensiveActionHeight', label: 'Average defensive-action position' },
  { key: 'boxEntries', label: 'Own box entries' },
  { key: 'shots', label: 'Own shots' },
  { key: 'clearances', label: 'Clearances' },
  { key: 'opponentTerritoryHeight', label: 'Opponent average field position' },
  { key: 'opponentFinalThirdShare', label: 'Opponent final-third share' },
]

const OWNERSHIP_ROWS: Array<{ key: keyof LeadControlSurface['ownership']['components']; label: string }> = [
  { key: 'opponentBoxEntries', label: 'Opponent box entries' },
  { key: 'opponentShots', label: 'Opponent shots' },
  { key: 'opponentBigChances', label: 'Opponent big chances' },
  { key: 'ownTerritorialExits', label: 'Own territorial exits' },
  { key: 'ownCounters', label: 'Own counters' },
  { key: 'ownShots', label: 'Own shots' },
  { key: 'timeToFirstMeaningfulOpponentAttack', label: 'Time to first meaningful opponent attack' },
]

function seconds(value: number | null | undefined) {
  if (value == null) return '—'
  const minutes = Math.floor(value / 60)
  return `${minutes}:${String(Math.floor(value % 60)).padStart(2, '0')}`
}

function metricValue(metric: LeadControlMetric, rateMode: ProfileRateMode) {
  if (metric.value == null) return '—'
  if (metric.kind === 'time') return seconds(metric.value)
  if (metric.kind === 'share') return `${(metric.value * 100).toFixed(1)}%`
  if (metric.kind === 'height') return metric.value.toFixed(1)
  if (rateMode === 'full') return metric.count.toLocaleString()
  return metric.per90 == null ? '—' : metric.per90.toFixed(2)
}

function baselineValue(metric: LeadControlMetric, rateMode: ProfileRateMode) {
  if (metric.baselineValue == null) return '—'
  if (metric.kind === 'share') return `${(metric.baselineValue * 100).toFixed(1)}%`
  if (metric.kind === 'height') return metric.baselineValue.toFixed(1)
  if (metric.kind === 'time') return seconds(metric.baselineValue)
  if (rateMode === 'full') return metric.baselineCount?.toLocaleString() ?? '—'
  return metric.baselinePer90?.toFixed(2) ?? '—'
}

function deltaValue(metric: LeadControlMetric, rateMode: ProfileRateMode) {
  if (metric.delta == null) return '—'
  const sign = metric.delta > 0 ? '+' : ''
  if (metric.kind === 'share') return `${sign}${(metric.delta * 100).toFixed(1)}pp`
  if (metric.kind === 'height') return `${sign}${metric.delta.toFixed(1)}`
  if (metric.kind === 'time') return `${sign}${metric.delta.toFixed(0)}s`
  if (rateMode === 'full') {
    if (metric.baselineCount == null) return '—'
    const countDelta = metric.count - metric.baselineCount
    return `${countDelta > 0 ? '+' : ''}${countDelta.toLocaleString()}`
  }
  return metric.deltaPer90 == null ? '—' : `${metric.deltaPer90 > 0 ? '+' : ''}${metric.deltaPer90.toFixed(2)}`
}

function unitLabel(metric: LeadControlMetric, rateMode: ProfileRateMode) {
  if (metric.kind === 'height') return '0 own goal – 100 opposition goal'
  if (metric.kind === 'share') return 'Share of actions'
  if (metric.kind === 'time') return 'Minutes:seconds'
  return rateMode === 'full' ? 'Total actions' : 'Per 90 lead minutes'
}

function scopeName(value: string | null | undefined) {
  if (!value) return 'All phases'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function EvidenceStrip({ payload, surface }: { payload: LeadControlPayload; surface: LeadControlSurface }) {
  const reliability = surface.reliability
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-line-bright py-2 font-mono text-[10px] text-ink-dim">
      <span>{surface.exposureMinutes.toLocaleString()} lead minutes</span>
      <span>{surface.episodeCount.toLocaleString()} lead periods</span>
      <span>{surface.matchCount.toLocaleString()} matches</span>
      <span>{payload.comparison.matchedWindows.toLocaleString()} comparable draw periods</span>
      <span className={reliability.status === 'verified' ? 'text-mint' : 'text-gold'}>{reliability.status}</span>
    </div>
  )
}

function MetricRow({ metric, rateMode }: { metric: LeadControlMetric; rateMode: ProfileRateMode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-2 border-b border-line/70 py-2 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_72px_72px_72px]">
      <div className="min-w-0">
        <p className="truncate text-[10px] text-ink">{metric.label}</p>
        <p className="mt-0.5 truncate text-[9px] text-ink-muted">{unitLabel(metric, rateMode)} · {metric.count.toLocaleString()} recorded</p>
      </div>
      <span className="font-mono text-[10px] tabular-nums text-ink">{metricValue(metric, rateMode)}</span>
      <span className="hidden font-mono text-[10px] tabular-nums text-ink-dim sm:block">{baselineValue(metric, rateMode)}</span>
      <span className={`font-mono text-[10px] tabular-nums ${metric.delta == null ? 'text-ink-muted' : metric.delta < 0 ? 'text-ember' : 'text-mint'}`}>{deltaValue(metric, rateMode)}</span>
    </div>
  )
}

function ComponentTable({ surface, rateMode, panel }: { surface: LeadControlSurface; rateMode: ProfileRateMode; panel: ComponentGroup }) {
  const rows = panel === 'gravity' ? GRAVITY_ROWS : OWNERSHIP_ROWS
  const components = panel === 'gravity'
    ? surface.gravity.components as unknown as Record<string, LeadControlMetric>
    : surface.ownership.components as unknown as Record<string, LeadControlMetric>
  const direction = panel === 'gravity' ? surface.gravity.components.passDirection : null
  return (
    <section className="border border-line-bright bg-panel" aria-label={panel === 'gravity' ? 'Lead Gravity components' : 'Lead Ownership components'}>
      <div className="border-b border-line-bright px-3 py-3">
        <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">{panel === 'gravity' ? 'Lead Gravity' : 'Lead Ownership'}</h4>
        <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">{panel === 'gravity' ? 'How the team’s behaviour changes after taking a lead.' : 'How well the team controls play while ahead.'}</p>
      </div>
      <header className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-2 border-b border-line-bright px-3 py-2 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted sm:grid-cols-[minmax(0,1fr)_72px_72px_72px]">
        <span>Metric</span><span>Lead</span><span className="hidden sm:block">Draw period</span><span>Change</span>
      </header>
      <div className="px-3">
        {rows.map(row => <MetricRow key={row.key} metric={{ ...components[row.key], label: row.label }} rateMode={rateMode} />)}
        {direction ? (
          <div className="border-t border-line-bright py-2">
            <p className="mb-1 text-[9px] uppercase tracking-[0.12em] text-ink-dim">Pass direction · located pass share</p>
            <div className="grid gap-x-4 gap-y-1 sm:grid-cols-3">
              {(['forward', 'lateral', 'backward'] as const).map(value => <MetricRow key={value} metric={direction[value]} rateMode={rateMode} />)}
            </div>
          </div>
        ) : null}
      </div>
      <footer className="border-t border-line-bright px-3 py-2 text-[9px] leading-relaxed text-ink-muted">
        Change is the lead period minus comparable drawing periods from similar stages of matches. A dash means no reliable comparison is available.
      </footer>
    </section>
  )
}

function selectSurface(payload: LeadControlPayload, band: LeadBandMode, phase: string) {
  if (band !== 'all') return payload.selected.leadBandBreakdown[band]
  if (phase !== 'all') return payload.selected.phaseBreakdown[phase] ?? payload.selected
  return payload.selected
}

export function LeadControlPanel({ payload, loading, error, onRetry, rateMode }: {
  payload?: LeadControlPayload
  loading: boolean
  error?: string
  onRetry: () => void
  rateMode: ProfileRateMode
}) {
  const [band, setBand] = useState<LeadBandMode>('all')
  const [phase, setPhase] = useState('all')
  const phases = useMemo(() => payload ? Object.keys(payload.selected.phaseBreakdown).sort() : [], [payload])

  if (loading) return <EventMapNotice kind="loading" title="Loading lead control" />
  if (error || !payload) return <EventMapNotice kind="error" title="Lead control failed to load" onRetry={onRetry}>{error ?? 'The lead-control service returned no data.'}</EventMapNotice>

  const surface = selectSurface(payload, band, phase)
  const phaseDisabled = band !== 'all'
  return (
    <article className="space-y-3 py-3" aria-label="Lead Gravity and Lead Ownership">
      <header className="max-w-3xl">
        <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-electric/80">Lead control · team surface</p>
        <h3 className="mt-1 text-sm font-black uppercase tracking-[0.14em] text-ink">How this team plays with a lead</h3>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">Compare what the team does while ahead with similar periods when the score is level.</p>
      </header>

      <div className="flex flex-wrap items-center gap-2 border-b border-line-bright pb-2">
        <label className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim">
          <span>Lead margin</span>
          <select aria-label="Lead margin" value={band} onChange={event => setBand(event.target.value as LeadBandMode)} className="event-lens-control w-auto min-w-36"><option value="all">All leads</option><option value="oneGoal">One-goal leads</option><option value="multiGoal">Multi-goal leads</option></select>
        </label>
        <label className={`flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.12em] ${phaseDisabled ? 'text-ink-muted' : 'text-ink-dim'}`}>
          <span>Phase</span>
          <select aria-label="Match phase" disabled={phaseDisabled} value={phase} onChange={event => setPhase(event.target.value)} className="event-lens-control w-auto min-w-36"><option value="all">All phases</option>{phases.map(value => <option key={value} value={value}>{scopeName(value)}</option>)}</select>
        </label>
        {phaseDisabled ? <span className="text-[9px] text-ink-muted">Phase refinement is unavailable while a lead margin is selected.</span> : null}
      </div>

      <EvidenceStrip payload={payload} surface={surface} />
      <div className="grid items-start gap-3 lg:grid-cols-2">
        <ComponentTable surface={surface} rateMode={rateMode} panel="gravity" />
        <ComponentTable surface={surface} rateMode={rateMode} panel="ownership" />
      </div>
      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">How this is calculated</summary>
        <p className="mt-2">Lead periods are compared with drawing periods from similar match times. Field position runs from 0 at the team’s own goal to 100 at the opposition goal. The figures describe behaviour; they do not grade whether defending a lead was good or bad.</p>
      </details>
    </article>
  )
}
