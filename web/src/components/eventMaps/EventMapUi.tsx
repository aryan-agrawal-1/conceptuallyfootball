import { AlertCircle, Loader2, Maximize2, Minimize2, RotateCcw } from 'lucide-react'
import type { ReactNode } from 'react'
import type {
  EventMatchLookup,
  EventPass,
  EventProfileCoverage,
  EventShot,
} from '../../types/eventMaps'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import { goalZone, goalZoneLabel } from '../../lib/eventMaps/goalMouth'
import { cn } from '../../lib/utils'

export type EventMapViewOption<T extends string> = {
  value: T
  label: string
  disabled?: boolean
}

export function EventMatchFilter({
  matches,
  value,
  onChange,
}: {
  matches: EventMatchLookup
  value: string | null
  onChange: (value: string | null) => void
}) {
  const rows = Object.values(matches).sort((left, right) =>
    left.matchDate.localeCompare(right.matchDate) || left.matchId.localeCompare(right.matchId),
  )
  return (
    <label className="flex min-w-0 items-center justify-between gap-2 border border-line-bright bg-panel px-3 text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim sm:justify-start">
      Match
      <select
        aria-label="Match"
        value={value ?? ''}
        onChange={event => onChange(event.target.value || null)}
        className="h-9 min-w-48 max-w-full border border-control-border bg-panel px-3 text-[10px] normal-case tracking-normal text-control-fg outline-none hover:border-electric focus:border-electric"
      >
        <option value="">All season matches</option>
        {rows.map(match => (
          <option key={match.matchId} value={match.matchId}>
            {match.opponent} ({match.venue === 'home' ? 'H' : match.venue === 'away' ? 'A' : 'N'})
          </option>
        ))}
      </select>
    </label>
  )
}

export function EventMapCard({
  title,
  description,
  controls,
  children,
  footer,
  expanded,
  onExpandedChange,
  className,
}: {
  title: string
  description: string
  controls?: ReactNode
  children: ReactNode
  footer?: ReactNode
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  className?: string
}) {
  return (
    <article className={cn('flex min-w-0 flex-col border border-line-bright bg-panel', className)}>
      <header className="flex min-h-16 flex-col gap-2 border-b border-line-bright px-3 py-2.5 sm:flex-row sm:items-center sm:gap-3">
        <div className="min-w-0 sm:max-w-[42%] sm:shrink-0">
          <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">{title}</h3>
          <p className="mt-1 text-[9px] leading-relaxed text-ink-dim">{description}</p>
        </div>
        <div className="flex w-full min-w-24 flex-1 flex-col items-center justify-center px-2 text-electric sm:px-4" aria-label="Attacking direction is left to right">
          <span className="font-mono text-[8px] font-bold uppercase tracking-[0.2em]">Attack</span>
          <span className="relative mt-0.5 h-2 w-full" aria-hidden="true">
            <span className="absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-current" />
            <span className="absolute right-0 top-1/2 size-1.5 -translate-y-1/2 rotate-45 border-r border-t border-current" />
          </span>
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2">
          {controls}
          <button type="button" onClick={() => onExpandedChange(!expanded)} className="flex size-8 items-center justify-center border border-control-border bg-raised text-control-fg transition-colors hover:border-electric hover:text-ink" aria-label={expanded ? 'Exit full-screen event map' : `Expand ${title.toLowerCase()}`}>
            {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          </button>
        </div>
      </header>
      <div className="flex min-h-0 flex-1 items-center justify-center bg-mat p-2 sm:p-2.5">
        {children}
      </div>
      {footer ? <footer className="border-t border-line-bright px-3 py-2.5">{footer}</footer> : null}
    </article>
  )
}

const SHOT_OUTCOMES = [
  { label: 'Goal', color: '#1FD17C' },
  { label: 'Saved', color: '#4A9EF5' },
  { label: 'Blocked', color: '#F0A832' },
  { label: 'Off target', color: '#8A95B8' },
  { label: 'Woodwork', color: '#EF5C66' },
] as const

export function ShotMapLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim" aria-label="Shot map legend">
      {SHOT_OUTCOMES.map(item => (
        <span key={item.label} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-full border border-ink/35" style={{ backgroundColor: item.color }} aria-hidden />
          {item.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5 border-l border-line-bright pl-3">
        <span className="size-2 rounded-full bg-ink-dim" aria-hidden /> Standard chance
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="size-3.5 rounded-full bg-ink-dim" aria-hidden /> Big chance
      </span>
      <span className="basis-full font-normal normal-case tracking-normal text-ink-muted">Marker size represents chance classification; colour represents outcome.</span>
    </div>
  )
}

export function EventMapViewTabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T
  options: EventMapViewOption<T>[]
  onChange: (value: T) => void
  label: string
}) {
  return (
    <div
      className="flex max-w-full gap-px overflow-x-auto border border-line-bright bg-line"
      role="tablist"
      aria-label={label}
    >
      {options.map(option => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          disabled={option.disabled}
          onClick={() => onChange(option.value)}
          className={cn(
            'min-h-9 shrink-0 bg-panel px-3 text-[10px] font-bold uppercase tracking-[0.14em] transition-colors',
            option.value === value
              ? 'bg-electric/15 text-electric shadow-[inset_0_-2px_0_#4A9EF5]'
              : 'text-control-fg hover:bg-raised hover:text-control-fg-hover',
            option.disabled && 'text-control-disabled opacity-50',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function EventMapNotice({
  kind,
  title,
  children,
  onRetry,
}: {
  kind: 'loading' | 'error' | 'empty' | 'unavailable' | 'sparse' | 'truncated'
  title: string
  children?: ReactNode
  onRetry?: () => void
}) {
  const accent =
    kind === 'error'
      ? 'border-ember/40 bg-ember/8 text-ember'
      : kind === 'truncated' || kind === 'sparse'
        ? 'border-gold/40 bg-gold/8 text-gold'
        : 'border-line-bright bg-raised/60 text-electric'
  return (
    <div className={cn('flex min-h-16 items-start gap-3 border px-4 py-3', accent)} role="status">
      {kind === 'loading' ? (
        <Loader2 size={15} className="mt-0.5 shrink-0 animate-spin" />
      ) : (
        <AlertCircle size={15} className="mt-0.5 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em]">{title}</p>
        {children ? <div className="mt-1 text-[11px] leading-relaxed text-ink-dim">{children}</div> : null}
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="flex shrink-0 items-center gap-1 text-[10px] font-bold uppercase tracking-[0.12em] text-control-fg hover:text-ink"
        >
          <RotateCcw size={12} /> Retry
        </button>
      ) : null}
    </div>
  )
}

export function EventCoverage({ coverage }: { coverage: EventProfileCoverage }) {
  const ratio = coverage.matchesExpected
    ? Math.min(1, coverage.matchesIncluded / coverage.matchesExpected)
    : 0
  return (
    <div className="border border-line-bright bg-panel px-3 py-2.5">
      <div className="mb-2 flex items-center justify-between gap-3 text-[9px] font-mono uppercase tracking-[0.14em]">
        <span className="text-ink-dim">Observed coverage</span>
        <span className={coverage.complete ? 'text-mint' : 'text-gold'}>
          {coverage.matchesIncluded}/{coverage.matchesExpected || '—'} matches
        </span>
      </div>
      <div className="h-1 overflow-hidden bg-line" aria-hidden="true">
        <div
          className={cn('h-full', coverage.complete ? 'bg-mint' : 'bg-gold')}
          style={{ width: `${ratio * 100}%` }}
        />
      </div>
    </div>
  )
}

export function EventMetricStrip({
  metrics,
}: {
  metrics: Array<{ label: string; value: string | number }>
}) {
  return (
    <dl className="grid grid-cols-3 border border-line-bright bg-line">
      {metrics.map(metric => (
        <div key={metric.label} className="bg-panel px-3 py-2.5 text-center">
          <dt className="text-[8px] font-bold uppercase tracking-[0.15em] text-ink-dim">
            {metric.label}
          </dt>
          <dd className="mt-1 font-mono text-[15px] tabular-nums text-ink">{metric.value}</dd>
        </div>
      ))}
    </dl>
  )
}

function displayLabel(value: string) {
  return value.replaceAll('_', ' ')
}

function passTags(pass: EventPass) {
  return [
    pass.progressive ? 'Progressive' : null,
    pass.keyPass ? 'Key pass' : null,
    pass.cross ? 'Cross' : null,
    pass.longBall ? 'Long ball' : null,
    pass.finalThirdEntry ? 'Final-third entry' : null,
    pass.boxEntry ? 'Box entry' : null,
  ].filter((tag): tag is string => tag != null)
}

export function EventSelectionDetails({
  selection,
  matches,
}: {
  selection: SelectablePitchEvent | null
  matches: EventMatchLookup
}) {
  if (!selection) {
    return (
      <div className="border border-dashed border-line-bright bg-panel/60 px-4 py-4 text-[10px] leading-relaxed text-ink-dim">
        Hover or tap an event. Keyboard users can focus the pitch and use arrow keys; Escape clears selection.
      </div>
    )
  }

  const event = selection.event
  const match = matches[event.matchRef]
  const isPass = selection.kind === 'pass'
  const pass = isPass ? (event as EventPass) : null
  const shot = !isPass ? (event as EventShot) : null
  const tags = pass ? passTags(pass) : []

  const outcome = pass
    ? pass.outcome === 'successful' ? 'Completed' : 'Incomplete'
    : displayLabel(shot!.outcome)
  const context = pass ? `${pass.length.toFixed(1)} m` : displayLabel(shot!.situation)

  return (
    <div className="border border-electric/45 bg-[linear-gradient(135deg,rgba(74,158,245,0.12),rgba(13,15,26,0.96)_58%)] px-3 py-2 shadow-[0_12px_30px_rgba(0,0,0,0.2)]">
      <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <p className="text-[11px] font-bold text-ink">
          {match?.opponent ?? 'Unknown opponent'} · {event.minute}&prime;
        </p>
        <span className="text-[9px] font-bold uppercase tracking-[0.12em] text-electric">{outcome}</span>
        <span className="text-[9px] uppercase tracking-[0.12em] text-ink-dim">{context}</span>
        <span className="ml-auto font-mono text-[8px] text-ink-dim">{match?.matchDate ?? '—'}</span>
      </div>
      {shot ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          <span className="border border-line-bright bg-raised px-2 py-1 text-[8px] uppercase tracking-[0.13em] text-ink-dim">
            {displayLabel(shot.bodyPart)}
          </span>
          {shot.goalMouth && goalZone(shot.goalMouth) ? (
            <EventTag>Target: {goalZoneLabel(goalZone(shot.goalMouth)!)}</EventTag>
          ) : null}
          {shot.bigChance ? <EventTag>Big chance</EventTag> : null}
          {shot.assisted ? <EventTag>Assisted</EventTag> : null}
        </div>
      ) : null}
      {tags.length ? (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tags.map(tag => <EventTag key={tag}>{tag}</EventTag>)}
        </div>
      ) : null}
    </div>
  )
}

function EventTag({ children }: { children: ReactNode }) {
  return (
    <span className="border border-electric/30 bg-electric/10 px-2 py-1 text-[8px] font-bold uppercase tracking-[0.13em] text-electric">
      {children}
    </span>
  )
}

export function EventPitchStage({
  expanded,
  onExpandedChange,
  children,
}: {
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'relative w-full bg-mat',
        expanded && 'fixed inset-0 z-[80] overflow-y-auto bg-mat px-3 py-4 sm:px-8',
      )}
    >
      {expanded ? <button type="button" onClick={() => onExpandedChange(false)} className="fixed right-4 top-4 z-[90] flex size-10 items-center justify-center border border-control-border bg-panel/90 text-control-fg backdrop-blur hover:border-electric hover:text-ink" aria-label="Exit full-screen event map"><Minimize2 size={16} /></button> : null}
      <div className={cn('mx-auto w-full', expanded && 'flex min-h-[calc(100svh-2rem)] max-w-[1200px] items-center')}>{children}</div>
    </div>
  )
}
