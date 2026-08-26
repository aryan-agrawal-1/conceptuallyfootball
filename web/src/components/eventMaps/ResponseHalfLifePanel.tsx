import { useState } from 'react'
import type {
  ResponseHalfLifeAggregate,
  ResponseHalfLifeCohort,
  ResponseHalfLifeEpisode,
  ResponseHalfLifePayload,
  ResponseHalfLifeSignal,
  ResponseHalfLifeWindow,
} from '../../types/responseHalfLife'
import { EventMapNotice, EventMapViewTabs } from './EventMapUi'

type DisplayGroup = 'attacking' | 'structural'

function label(value: string) {
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function seconds(value: number | null) {
  if (value == null) return '—'
  if (value === 0) return '0s'
  const minutes = Math.floor(value / 60)
  const remainder = value % 60
  return minutes ? `${minutes}m ${remainder}s` : `${remainder}s`
}

function decimal(value: number | null, places = 2) {
  return value == null ? '—' : value.toFixed(places)
}

function reliabilityTone(value: ResponseHalfLifeCohort['reliability']) {
  return value === 'verified' ? 'text-mint' : value === 'unavailable' ? 'text-ember' : 'text-gold'
}

function HalfLifeValue({ value, aggregate }: { value: number | null; aggregate: ResponseHalfLifeAggregate }) {
  return (
    <div>
      <p className="font-mono text-[20px] tabular-nums text-ink">{seconds(value)}</p>
      <p className="mt-1 text-[9px] text-ink-muted">
        {aggregate.status === 'recovered' ? 'first supported half reduction' : label(aggregate.status)}
      </p>
    </div>
  )
}

function SummaryCard({ label: title, aggregate, summary, colour }: {
  label: string
  aggregate: ResponseHalfLifeAggregate
  summary: ResponseHalfLifeCohort['attacking']['halfLifeSeconds']
  colour: string
}) {
  return (
    <div className="border border-line-bright bg-panel px-3 py-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim">{title} response half-life</p>
        <span className={`font-mono text-[9px] uppercase ${colour}`}>{summary.sampleSize} episodes</span>
      </div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <HalfLifeValue value={summary.medianSeconds} aggregate={aggregate} />
        <dl className="text-right text-[9px] text-ink-muted">
          <dt>Mean</dt>
          <dd className="font-mono text-ink">{seconds(summary.meanSeconds)}</dd>
        </dl>
      </div>
      <p className="mt-2 text-[9px] leading-relaxed text-ink-muted">
        Initial deviation {decimal(aggregate.initialDeviation, 3)} · half threshold {decimal(aggregate.halfThreshold, 3)} · {aggregate.recovered ? 'recovery observed' : 'no crossing observed'}
      </p>
    </div>
  )
}

function EvidenceStrip({ cohort }: { cohort: ResponseHalfLifeCohort }) {
  return (
    <dl className="grid border border-line-bright bg-line sm:grid-cols-4">
      {[
        ['Qualifying concessions', cohort.qualifyingConcessions.toLocaleString()],
        ['Rolling windows', cohort.qualifyingWindows.toLocaleString()],
        ['Matches', cohort.qualifyingMatches.toLocaleString()],
        ['Censored episodes', cohort.censoredEpisodes.toLocaleString()],
      ].map(([title, value]) => (
        <div key={title} className="bg-panel px-3 py-2.5">
          <dt className="text-[8px] font-bold uppercase tracking-[0.14em] text-ink-dim">{title}</dt>
          <dd className="mt-1 font-mono text-[15px] tabular-nums text-ink">{value}</dd>
        </div>
      ))}
    </dl>
  )
}

function SignalSummary({ signal, group }: { signal: ResponseHalfLifeSignal | null; group: DisplayGroup }) {
  if (!signal) return <span className="text-ink-muted">Unavailable for this window</span>
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[9px] uppercase tracking-[0.12em] text-ink-dim">{label(group)} deviation</span>
        <strong className="font-mono text-[12px] text-ink">{decimal(signal.signal, 3)}</strong>
      </div>
      <div className="grid gap-1 sm:grid-cols-2">
        {Object.entries(signal.components).map(([key, component]) => (
          <div key={key} className="flex min-w-0 justify-between gap-2 bg-raised px-2 py-1 text-[9px]">
            <span className="truncate text-ink-dim">{label(key)}</span>
            <span className="shrink-0 font-mono text-ink">{decimal(component.normalisedDeviation, 3)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function WindowRow({ window, group }: { window: ResponseHalfLifeWindow; group: DisplayGroup }) {
  const signal = window[group]
  return (
    <tr className={window.censored ? 'text-ink-muted' : 'text-ink'}>
      <td className="whitespace-nowrap px-2 py-2 font-mono">+{seconds(window.offsetSeconds)}</td>
      <td className="px-2 py-2">{window.censored ? <span className="text-gold">{label(window.censorReason ?? 'censored')}</span> : decimal(signal?.signal ?? null, 3)}</td>
      <td className="px-2 py-2">{signal ? `${signal.supportedComponents} components` : '—'}</td>
      <td className="px-2 py-2">{window.isAddedTime ? 'Added time' : label(window.phase)}</td>
    </tr>
  )
}

function EpisodeTrace({ episode, group }: { episode: ResponseHalfLifeEpisode; group: DisplayGroup }) {
  const aggregate = episode[group]
  const [open, setOpen] = useState(false)
  return (
    <details className="border border-line bg-panel open:border-line-bright" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-[10px] text-ink-dim">
        <span className="font-mono text-ink-muted">#{episode.matchRef ?? '—'} · {seconds(episode.concessionSecond)}</span>
        <strong className="font-medium text-ink">{episode.state.before ?? 'unknown'} → {episode.state.after ?? 'unknown'}</strong>
        <span>GD {episode.score.after.focalGoalDifference == null ? '—' : episode.score.after.focalGoalDifference > 0 ? `+${episode.score.after.focalGoalDifference}` : episode.score.after.focalGoalDifference}</span>
        <span className={episode.qualifies ? 'text-mint' : 'text-gold'}>{episode.qualifies ? 'qualifying' : label(episode.censorReason ?? 'unavailable')}</span>
        {episode.qualifies ? <span className="font-mono text-electric">{seconds(aggregate.halfLifeSeconds)}</span> : null}
      </summary>
      {open ? (
        <div className="space-y-3 border-t border-line px-3 py-3">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-ink-dim">
            <span>Destination: {episode.destination.available ? label(episode.destination.matchBasis ?? 'matched') : 'unavailable'}</span>
            <span>{episode.destination.matchCount} stable matches</span>
            <span>{episode.destination.exposureMinutes.toLocaleString()} stable min</span>
            {episode.destination.goalDifference != null ? <span>Destination GD {episode.destination.goalDifference > 0 ? `+${episode.destination.goalDifference}` : episode.destination.goalDifference}</span> : null}
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            <SignalSummary signal={episode.firstFiveMinuteResponse[group]} group={group} />
            <div className="text-[9px] leading-relaxed text-ink-dim">
              <p>Initial deviation <strong className="font-mono font-normal text-ink">{decimal(aggregate.initialDeviation, 3)}</strong>; half threshold <strong className="font-mono font-normal text-ink">{decimal(aggregate.halfThreshold, 3)}</strong>.</p>
              <p className="mt-1">{aggregate.status === 'no_recovery' ? 'No later supported window reached the half threshold.' : aggregate.status === 'unavailable' ? 'There is not enough supported evidence to calculate a half-life.' : `First supported reduction: ${seconds(aggregate.halfLifeSeconds)}.`}</p>
            </div>
          </div>
          <div className="overflow-x-auto border border-line-bright">
            <table className="w-full min-w-[440px] border-collapse text-left text-[9px]">
              <caption className="sr-only">{label(group)} response windows for concession at {seconds(episode.concessionSecond)}</caption>
              <thead className="bg-raised text-[8px] uppercase tracking-[0.12em] text-ink-dim"><tr><th scope="col" className="px-2 py-2">Offset</th><th scope="col" className="px-2 py-2">Signal</th><th scope="col" className="px-2 py-2">Support</th><th scope="col" className="px-2 py-2">Phase</th></tr></thead>
              <tbody className="divide-y divide-line">{episode.windows.map(window => <WindowRow key={`${window.index}-${window.startSecond}`} window={window} group={group} />)}</tbody>
            </table>
          </div>
        </div>
      ) : null}
    </details>
  )
}

function CohortContent({ cohort, group }: { cohort: ResponseHalfLifeCohort; group: DisplayGroup }) {
  return (
    <>
      <EvidenceStrip cohort={cohort} />
      <div className="grid gap-2 sm:grid-cols-2">
        <SummaryCard label="Attacking" aggregate={cohort.episodes[0]?.attacking ?? { initialDeviation: null, halfThreshold: null, halfLifeSeconds: null, recovered: false, supportedWindowCount: 0, status: 'unavailable' }} summary={cohort.attacking.halfLifeSeconds} colour="text-electric" />
        <SummaryCard label="Structural" aggregate={cohort.episodes[0]?.structural ?? { initialDeviation: null, halfThreshold: null, halfLifeSeconds: null, recovered: false, supportedWindowCount: 0, status: 'unavailable' }} summary={cohort.structural.halfLifeSeconds} colour="text-mint" />
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-[9px] text-ink-dim">
        {Object.entries(cohort.censorReasons).map(([reason, count]) => <span key={reason}>{label(reason)}: <strong className="font-mono font-normal text-ink">{count}</strong></span>)}
        {cohort.uncertainConcessionEvents ? <span className="text-gold">uncertain timestamps: <strong className="font-mono font-normal">{cohort.uncertainConcessionEvents}</strong></span> : null}
        {cohort.traceTruncated ? <span className="text-gold">showing first {cohort.traceLimit} of {cohort.episodeCount} traces</span> : null}
      </div>
      <div className="space-y-1">
        {cohort.episodes.length ? cohort.episodes.map(episode => <EpisodeTrace key={`${episode.providerMatchId}-${episode.eventIndex}`} episode={episode} group={group} />) : <EventMapNotice kind="unavailable" title="No qualifying concession trace" />}
      </div>
    </>
  )
}

export function ResponseHalfLifePanel({ payload, loading, error, onRetry }: {
  payload?: ResponseHalfLifePayload
  loading: boolean
  error?: string
  onRetry: () => void
}) {
  const [group, setGroup] = useState<DisplayGroup>('attacking')
  if (loading) return <EventMapNotice kind="loading" title="Loading response half-life" />
  if (error || !payload) return <EventMapNotice kind="error" title="Response half-life failed to load" onRetry={onRetry}>{error}</EventMapNotice>
  const cohort = payload.selected
  return (
    <article className="space-y-3 py-3" aria-label="Inspectable post-concession response half-life">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-xs font-bold uppercase tracking-[0.15em] text-ink">Response half-life</h3>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed text-ink-dim">How quickly observed post-concession behaviour moves towards the team's established behaviour for the resulting state, phase and goal difference.</p>
        </div>
        <EventMapViewTabs value={group} onChange={setGroup} label="Response half-life signal" options={[{ value: 'attacking', label: 'Attacking' }, { value: 'structural', label: 'Structural' }]} />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-y border-line-bright py-2 text-[10px] text-ink-dim">
        <span className={`font-bold uppercase tracking-[0.12em] ${reliabilityTone(cohort.reliability)}`}>{cohort.reliability}</span>
        <span>{cohort.reliabilityNote ?? 'Evidence supports the displayed aggregate.'}</span>
        <span className="ml-auto">{cohort.attacking.recoveredConcessions} attacking · {cohort.structural.recoveredConcessions} structural recoveries</span>
      </div>
      <CohortContent cohort={cohort} group={group} />
      <details className="border border-line-bright bg-raised/40 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
        <summary className="cursor-pointer text-control-fg hover:text-ink">Definitions and censor rules</summary>
        <div className="mt-2 space-y-2">
          <p>{payload.definitions.windowSeconds / 60}-minute windows start every {payload.definitions.stepSeconds / 60} minute(s) ({payload.definitions.overlapSeconds / 60} minutes overlap). Intervals are half-open and must fit inside one played period.</p>
          <p>Attacking uses shots, box entries, progressive actions and action height. Structural uses pass direction, length, completion, territory and defensive height. Both compare fixed-scale component deviations; no composite quality or causal claim is made.</p>
          <p>{payload.definitions.periodBoundary} {payload.definitions.subsequentGoal} {payload.definitions.redCard}</p>
          <p>Destination: {payload.definitions.destination.priority}. A missing stable destination returns unavailable.</p>
        </div>
      </details>
      {payload.baseline ? <p className="text-[10px] text-ink-dim">Baseline cohort is available; attacking and structural half-lives remain separate descriptive aggregates.</p> : null}
    </article>
  )
}
