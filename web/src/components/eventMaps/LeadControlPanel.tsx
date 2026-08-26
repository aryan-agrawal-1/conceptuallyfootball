import { useMemo, useState } from 'react'
import type {
  LeadControlEpisode,
  LeadControlMetric,
  LeadControlPayload,
  LeadControlSurface,
} from '../../types/leadControl'
import { EventMapNotice } from './EventMapUi'

type ViewMode = 'rate' | 'count'
type SurfaceMode = 'gravity' | 'ownership'
type LeadBandMode = 'all' | 'oneGoal' | 'multiGoal'

const GRAVITY_ROWS: Array<{ key: keyof LeadControlSurface['gravity']['components']; label: string }> = [
  { key: 'touchOriginHeight', label: 'Touch origin height' },
  { key: 'passOriginHeight', label: 'Pass origin height' },
  { key: 'defensiveActionHeight', label: 'Defensive-action height' },
  { key: 'boxEntries', label: 'Own box entries' },
  { key: 'shots', label: 'Own shots' },
  { key: 'clearances', label: 'Clearances' },
  { key: 'opponentTerritoryHeight', label: 'Opponent territorial height' },
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

function metricValue(metric: LeadControlMetric, mode: ViewMode) {
  if (metric.value == null) return '—'
  if (metric.kind === 'time') return seconds(metric.value)
  if (mode === 'count') return metric.count.toLocaleString()
  if (metric.kind === 'share') return `${(metric.value * 100).toFixed(1)}%`
  if (metric.kind === 'height') return `${metric.value.toFixed(1)}%`
  return metric.per90 == null ? '—' : metric.per90.toFixed(2)
}

function deltaValue(metric: LeadControlMetric) {
  if (metric.delta == null) return '—'
  const sign = metric.delta > 0 ? '+' : ''
  if (metric.kind === 'share') return `${sign}${(metric.delta * 100).toFixed(1)}pp`
  if (metric.kind === 'height') return `${sign}${metric.delta.toFixed(1)}pp`
  if (metric.kind === 'time') return `${sign}${metric.delta.toFixed(0)}s`
  return metric.deltaPer90 == null ? '—' : `${metric.deltaPer90 > 0 ? '+' : ''}${metric.deltaPer90.toFixed(2)}`
}

function scopeName(value: string | null | undefined) {
  if (!value) return 'All phases'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function EvidenceStrip({ payload, surface }: { payload: LeadControlPayload; surface: LeadControlSurface }) {
  const coverage = payload.coverage
  const reliability = surface.reliability
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-line-bright py-2 font-mono text-[10px] text-ink-dim">
      <span>{surface.exposureMinutes.toLocaleString()} lead minutes</span>
      <span>{surface.episodeCount.toLocaleString()} lead episodes</span>
      <span>{surface.matchCount.toLocaleString()} matches</span>
      <span>{payload.comparison.matchedWindows.toLocaleString()} matched baseline windows</span>
      <span className={reliability.status === 'verified' ? 'text-mint' : 'text-gold'}>{reliability.status}</span>
      {coverage.episodeEvidenceTruncated ? <span className="text-gold">episode list capped at {coverage.episodeEvidenceLimit}</span> : null}
    </div>
  )
}

function AxisCard({ label, axis, accent }: {
  label: string
  axis: LeadControlSurface['axes']['behavioralRetreat']
  accent: 'electric' | 'mint'
}) {
  return (
    <div className="border border-line-bright bg-panel px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[9px] font-bold uppercase tracking-[0.16em] text-ink-dim">{label}</p>
          <p className="mt-1 text-[10px] leading-relaxed text-ink-muted">{axis.higherMeans}</p>
        </div>
        <strong className={`font-mono text-2xl font-normal tabular-nums ${accent === 'mint' ? 'text-mint' : 'text-electric'}`}>
          {axis.value == null ? '—' : axis.value.toFixed(0)}
        </strong>
      </div>
      <p className="mt-2 text-[9px] text-ink-muted">{axis.availableComponents} component deltas available · descriptive 0–100 axis</p>
    </div>
  )
}

function quadrantPlacement(surface: LeadControlSurface) {
  const retreat = surface.axes.behavioralRetreat.value
  const control = surface.axes.processControl.value
  if (!surface.reliability.labelEligible || retreat == null || control == null) {
    return {
      label: null,
      shortLabel: 'Insufficient evidence',
      available: false,
      note: 'A quadrant label is withheld until this refinement has sufficient lead episodes and matched baseline evidence.',
    }
  }
  const label = retreat < 50
    ? control >= 50 ? 'assertive controllers' : 'vulnerable high teams'
    : control >= 50 ? 'controlled deep defenders' : 'retreat and suffer'
  return {
    label,
    shortLabel: label.replace(/^./, character => character.toUpperCase()),
    available: true,
    note: 'Descriptive placement from component deltas; it is not a causal or team-strength judgement.',
  }
}

function Quadrant({ surface }: { surface: LeadControlSurface }) {
  const retreat = surface.axes.behavioralRetreat.value
  const control = surface.axes.processControl.value
  const placement = quadrantPlacement(surface)
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Lead control quadrant">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h4 className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink">Two-dimensional readout</h4>
          <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-ink-dim">Horizontal = observed retreat; vertical = opposition restriction and viable outlets. The placement is descriptive, not causal.</p>
        </div>
        <span className={placement.available ? 'border border-electric/40 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-electric' : 'border border-gold/40 px-2 py-1 text-[9px] font-bold uppercase tracking-[0.12em] text-gold'}>
          {placement.shortLabel}
        </span>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-[minmax(0,1fr)_180px]">
        <div className="relative h-52 overflow-hidden border border-line bg-mat" role="img" aria-label={`Lead control quadrant: ${placement.available ? placement.shortLabel : 'insufficient evidence'}`}>
          <span className="absolute inset-x-0 top-1/2 border-t border-dashed border-line-bright" aria-hidden="true" />
          <span className="absolute inset-y-0 left-1/2 border-l border-dashed border-line-bright" aria-hidden="true" />
          <span className="absolute left-2 top-2 text-[8px] uppercase tracking-[0.11em] text-ink-muted">Assertive controllers</span>
          <span className="absolute right-2 top-2 text-right text-[8px] uppercase tracking-[0.11em] text-ink-muted">Controlled deep defenders</span>
          <span className="absolute bottom-2 left-2 text-[8px] uppercase tracking-[0.11em] text-ink-muted">Vulnerable high teams</span>
          <span className="absolute bottom-2 right-2 text-right text-[8px] uppercase tracking-[0.11em] text-ink-muted">Retreat and suffer</span>
          {retreat != null && control != null && placement.available ? (
            <span
              className="absolute size-3 -translate-x-1/2 translate-y-1/2 rounded-full border-2 border-ink bg-electric shadow-[0_0_0_4px_rgba(74,158,245,0.2)]"
              style={{ left: `${retreat}%`, bottom: `${control}%` }}
              aria-hidden="true"
            />
          ) : (
            <span className="absolute inset-0 flex items-center justify-center px-6 text-center text-[10px] text-gold">A label is withheld until lead episodes and clock-matched drawing evidence meet the reliability threshold.</span>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-px border border-line-bright bg-line text-[9px] sm:grid-cols-1">
          <div className="bg-panel px-2 py-2"><dt className="uppercase tracking-[0.12em] text-ink-muted">More retreat →</dt><dd className="mt-1 font-mono text-ink">{retreat == null ? '—' : retreat.toFixed(0)}</dd></div>
          <div className="bg-panel px-2 py-2"><dt className="uppercase tracking-[0.12em] text-ink-muted">More control ↑</dt><dd className="mt-1 font-mono text-ink">{control == null ? '—' : control.toFixed(0)}</dd></div>
          <div className="col-span-2 bg-panel px-2 py-2 sm:col-span-1"><dt className="uppercase tracking-[0.12em] text-ink-muted">Placement note</dt><dd className="mt-1 leading-relaxed text-ink-dim">{placement.note}</dd></div>
        </dl>
      </div>
    </section>
  )
}

function MetricRow({ metric, mode }: { metric: LeadControlMetric; mode: ViewMode }) {
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-2 border-b border-line/70 py-2 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_72px_72px_64px]">
      <div className="min-w-0">
        <p className="truncate text-[10px] text-ink">{metric.label}</p>
        <p className="mt-0.5 truncate text-[9px] text-ink-muted">{metric.unit} · {metric.count.toLocaleString()} raw</p>
      </div>
      <span className="font-mono text-[10px] tabular-nums text-ink">{metricValue(metric, mode)}</span>
      <span className="hidden font-mono text-[10px] tabular-nums text-ink-dim sm:block">{metric.baselineValue == null ? '—' : metric.kind === 'share' ? `${(metric.baselineValue * 100).toFixed(1)}%` : metric.kind === 'height' ? `${metric.baselineValue.toFixed(1)}%` : metric.kind === 'time' ? seconds(metric.baselineValue) : metric.baselinePer90?.toFixed(2) ?? '—'}</span>
      <span className={`font-mono text-[10px] tabular-nums ${metric.delta == null ? 'text-ink-muted' : metric.delta < 0 ? 'text-ember' : 'text-mint'}`}>{deltaValue(metric)}</span>
    </div>
  )
}

function ComponentTable({ surface, mode, panel }: { surface: LeadControlSurface; mode: ViewMode; panel: SurfaceMode }) {
  const rows = panel === 'gravity' ? GRAVITY_ROWS : OWNERSHIP_ROWS
  const components = panel === 'gravity'
    ? surface.gravity.components as unknown as Record<string, LeadControlMetric>
    : surface.ownership.components as unknown as Record<string, LeadControlMetric>
  const direction = panel === 'gravity' ? surface.gravity.components.passDirection : null
  return (
    <section className="border border-line-bright bg-panel" aria-label={panel === 'gravity' ? 'Lead Gravity components' : 'Lead Ownership components'}>
      <header className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-2 border-b border-line-bright px-3 py-2 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted sm:grid-cols-[minmax(0,1fr)_72px_72px_64px]">
        <span>Raw component</span><span>Lead</span><span className="hidden sm:block">Matched draw</span><span>Δ</span>
      </header>
      <div className="px-3">
        {rows.map(row => <MetricRow key={row.key} metric={components[row.key]} mode={mode} />)}
        {direction ? (
          <div className="border-t border-line-bright py-2">
            <p className="mb-1 text-[9px] uppercase tracking-[0.12em] text-ink-dim">Pass direction · located pass share</p>
            <div className="grid gap-x-4 gap-y-1 sm:grid-cols-3">
              {(['forward', 'lateral', 'backward'] as const).map(value => <MetricRow key={value} metric={direction[value]} mode={mode} />)}
            </div>
          </div>
        ) : null}
      </div>
      <footer className="border-t border-line-bright px-3 py-2 text-[9px] leading-relaxed text-ink-muted">
        Lead values are shown with raw counts and state-minute rates. Δ is lead minus the same-phase, clock/goal-difference-matched drawing baseline; a dash means no comparable baseline.
      </footer>
    </section>
  )
}

function EpisodeRow({ episode }: { episode: LeadControlEpisode }) {
  return (
    <details className="border border-line bg-panel px-3 py-2 open:border-line-bright">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-ink-dim">
        <span className="font-mono text-ink-muted">#{episode.matchRef ?? '—'} · {seconds(episode.stateEntrySecond)}</span>
        <strong className="text-ink">{episode.leadBand === 'multi_goal' ? 'Multi-goal lead' : 'One-goal lead'}</strong>
        <span>{scopeName(episode.phase)}</span>
        <span>{Math.round(episode.durationSeconds / 60)} lead min</span>
        <span className={episode.coverage.matchedBaseline ? 'text-mint' : 'text-gold'}>{episode.matchedBaselineWindows} matched windows</span>
      </summary>
      <div className="mt-2 grid gap-2 border-t border-line pt-2 text-[10px] sm:grid-cols-2">
        <div className="space-y-1 text-ink-dim">
          <p>Goal difference <strong className="ml-1 font-mono font-normal text-ink">+{episode.goalDifference ?? '—'}</strong></p>
          <p>First meaningful opponent attack <strong className="ml-1 font-mono font-normal text-ink">{seconds(episode.timeToFirstMeaningfulOpponentAttackSeconds)}</strong></p>
          <p>Lead window <strong className="ml-1 font-mono font-normal text-ink">{seconds(episode.startSecond)}–{seconds(episode.endSecond)}</strong></p>
        </div>
        <div className="space-y-1 text-ink-dim">
          <p>Lead survived to match end <strong className="ml-1 font-mono font-normal text-ink">{episode.secondaryOutcomes.leadSurvivedToMatchEnd == null ? '—' : episode.secondaryOutcomes.leadSurvivedToMatchEnd ? 'Yes' : 'No'}</strong></p>
          <p>Final result <strong className="ml-1 font-mono font-normal text-ink">{episode.secondaryOutcomes.finalResult ?? '—'}</strong></p>
          <p className="leading-relaxed text-ink-muted">{episode.secondaryOutcomes.note}</p>
        </div>
      </div>
    </details>
  )
}

function selectSurface(payload: LeadControlPayload, band: LeadBandMode, phase: string) {
  if (band !== 'all') return payload.selected.leadBandBreakdown[band]
  if (phase !== 'all') return payload.selected.phaseBreakdown[phase] ?? payload.selected
  return payload.selected
}

export function LeadControlPanel({ payload, loading, error, onRetry }: {
  payload?: LeadControlPayload
  loading: boolean
  error?: string
  onRetry: () => void
}) {
  const [panel, setPanel] = useState<SurfaceMode>('gravity')
  const [mode, setMode] = useState<ViewMode>('rate')
  const [band, setBand] = useState<LeadBandMode>('all')
  const [phase, setPhase] = useState('all')
  const [showAllEpisodes, setShowAllEpisodes] = useState(false)

  const phases = useMemo(() => payload ? Object.keys(payload.selected.phaseBreakdown).sort() : [], [payload])
  if (loading) return <EventMapNotice kind="loading" title="Loading lead control" />
  if (error || !payload) return <EventMapNotice kind="error" title="Lead control failed to load" onRetry={onRetry}>{error ?? 'The lead-control service returned no data.'}</EventMapNotice>

  const surface = selectSurface(payload, band, phase)
  const episodes = band === 'all' ? payload.episodes : payload.episodes.filter(episode => episode.leadBand === (band === 'oneGoal' ? 'one_goal' : 'multi_goal'))
  const visibleEpisodes = showAllEpisodes ? episodes : episodes.slice(0, 12)
  const phaseDisabled = band !== 'all'
  return (
    <article className="space-y-3 py-3" aria-label="Lead Gravity and Lead Ownership">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="max-w-3xl">
          <p className="text-[9px] font-mono uppercase tracking-[0.2em] text-electric/80">Lead control · team surface</p>
          <h3 className="mt-1 text-sm font-black uppercase tracking-[0.14em] text-ink">Gravity ≠ Ownership</h3>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-dim">Lead Gravity measures how behaviour changes after taking a lead. Lead Ownership measures process evidence while ahead: opposition access, viable outlets, and time to the first meaningful attack. The result is never used as a sole definition.</p>
        </div>
        <div className="flex max-w-full flex-wrap gap-2" role="group" aria-label="Lead control display">
          <div className="flex border border-line-bright bg-line">
            {(['gravity', 'ownership'] as const).map(value => <button key={value} type="button" aria-pressed={panel === value} onClick={() => setPanel(value)} className={`min-h-8 bg-panel px-2.5 text-[9px] font-bold uppercase tracking-[0.12em] ${panel === value ? 'bg-electric/15 text-electric' : 'text-control-fg hover:bg-raised'}`}>{value === 'gravity' ? 'Lead Gravity' : 'Lead Ownership'}</button>)}
          </div>
          <div className="flex border border-line-bright bg-line">
            {(['rate', 'count'] as const).map(value => <button key={value} type="button" aria-pressed={mode === value} onClick={() => setMode(value)} className={`min-h-8 bg-panel px-2.5 text-[9px] font-bold uppercase tracking-[0.12em] ${mode === value ? 'bg-electric/15 text-electric' : 'text-control-fg hover:bg-raised'}`}>{value === 'rate' ? 'State rates' : 'Raw counts'}</button>)}
          </div>
        </div>
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
        {phaseDisabled ? <span className="text-[9px] text-ink-muted">Phase refinement is shown separately from lead-margin refinement.</span> : null}
      </div>

      <EvidenceStrip payload={payload} surface={surface} />
      <div className="grid gap-3 lg:grid-cols-2">
        <AxisCard label="Behavioral retreat · Lead Gravity" axis={surface.axes.behavioralRetreat} accent="electric" />
        <AxisCard label="Process control · Lead Ownership" axis={surface.axes.processControl} accent="mint" />
      </div>
      <Quadrant surface={surface} />
      <ComponentTable surface={surface} mode={mode} panel={panel} />

      <section className="border border-line-bright bg-raised/40 px-3 py-2" aria-label="Lead episode drilldown">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h4 className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">Episode drill-down</h4>
            <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">Each row keeps the score margin, match phase, clock-matched baseline exposure, first meaningful opponent attack, and secondary result context inspectable.</p>
          </div>
          {episodes.length > 12 ? <button type="button" className="text-[9px] font-bold uppercase tracking-[0.12em] text-control-fg hover:text-ink" onClick={() => setShowAllEpisodes(value => !value)}>{showAllEpisodes ? 'Show fewer' : `Show all ${episodes.length}`}</button> : null}
        </div>
        <div className="mt-2 space-y-1">{visibleEpisodes.length ? visibleEpisodes.map(episode => <EpisodeRow key={episode.episodeId} episode={episode} />) : <EventMapNotice kind="empty" title="No lead episodes in this refinement" />}</div>
      </section>

      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">Evidence, reliability and limitations</summary>
        <div className="mt-2 space-y-2">
          <p>{surface.reliability.note}</p>
          <p>{payload.comparison.clockMatching.rule}. Baselines require goal difference 0 and the same phase; unmatched drawing time is not added.</p>
          <ul className="list-disc space-y-1 pl-4">{payload.limitations.map(note => <li key={note}>{note}</li>)}</ul>
          <p className="text-gold">Opponent strength is not controlled: {payload.opponentStrength.note}</p>
        </div>
      </details>
    </article>
  )
}
