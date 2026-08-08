import { AlertCircle, Loader2, Maximize2, Minimize2, RotateCcw } from 'lucide-react'
import type { ReactNode } from 'react'
import type {
  EventMatchLookup,
  EventPass,
  EventProfileCoverage,
  EventShot,
} from '../../types/eventMaps'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import { cn } from '../../lib/utils'

export type EventMapViewOption<T extends string> = {
  value: T
  label: string
  disabled?: boolean
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

  return (
    <div className="border border-electric/45 bg-[linear-gradient(135deg,rgba(74,158,245,0.12),rgba(13,15,26,0.96)_58%)] px-4 py-3 shadow-[0_16px_40px_rgba(0,0,0,0.25)]">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-electric">
            {isPass ? 'Pass inspection' : 'Shot inspection'}
          </p>
          <p className="mt-1 text-[13px] font-bold text-ink">
            {match?.opponent ?? 'Unknown opponent'} · {event.minute}&prime;
          </p>
        </div>
        <span className="font-mono text-[9px] text-ink-dim">{match?.matchDate ?? '—'}</span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line-bright pt-3 text-[9px] uppercase tracking-[0.12em]">
        <div>
          <dt className="text-ink-dim">Outcome</dt>
          <dd className="mt-0.5 text-ink">
            {pass ? (pass.outcome === 'successful' ? 'Completed' : 'Incomplete') : displayLabel(shot!.outcome)}
          </dd>
        </div>
        <div>
          <dt className="text-ink-dim">{pass ? 'Length' : 'Context'}</dt>
          <dd className="mt-0.5 text-ink">
            {pass ? `${pass.length.toFixed(1)} m` : displayLabel(shot!.situation)}
          </dd>
        </div>
      </dl>
      {shot ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          <span className="border border-line-bright bg-raised px-2 py-1 text-[8px] uppercase tracking-[0.13em] text-ink-dim">
            {displayLabel(shot.bodyPart)}
          </span>
          {shot.bigChance ? <EventTag>Big chance</EventTag> : null}
          {shot.assisted ? <EventTag>Assisted</EventTag> : null}
        </div>
      ) : null}
      {tags.length ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
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
        'relative bg-mat',
        expanded && 'fixed inset-0 z-[80] overflow-y-auto bg-mat px-3 py-4 sm:px-8',
      )}
    >
      <button
        type="button"
        onClick={() => onExpandedChange(!expanded)}
        className="absolute right-2 top-2 z-20 flex size-9 items-center justify-center border border-control-border bg-panel/90 text-control-fg backdrop-blur hover:border-electric hover:text-ink"
        aria-label={expanded ? 'Exit full-screen event map' : 'Expand event map'}
      >
        {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
      </button>
      <div className={cn('mx-auto', expanded && 'max-w-[min(72vh,560px)]')}>{children}</div>
    </div>
  )
}
