import { ChevronDown, SlidersHorizontal } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { StateLensMetadata } from '../../types/eventMaps'

const STATE_FIELDS = [
  'state', 'goal_difference', 'phase', 'draw_provenance',
  'minimum_state_age_seconds', 'maximum_state_age_seconds',
] as const

function displayLabel(value: string) {
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function withCurrent<T extends string | number>(values: T[] | undefined, current: string) {
  const result: Array<string | number> = [...(values ?? [])]
  if (current !== '' && !result.some(value => String(value) === current)) result.push(current)
  return result
}

export function StateLensControls({ metadata, searchParams, onChange, compact = false, controls }: {
  metadata?: StateLensMetadata
  searchParams: URLSearchParams
  onChange: (next: URLSearchParams) => void
  compact?: boolean
  controls?: ReactNode
}) {
  const [panelOpen, setPanelOpen] = useState(false)
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const refinements = metadata?.eligibleRefinements
  const selectedState = searchParams.get('state') ?? 'all'
  const selectedDifference = searchParams.get('goal_difference') ?? ''
  const selectedPhase = searchParams.get('phase') ?? ''
  const selectedProvenance = searchParams.get('draw_provenance') ?? ''
  const comparisonEnabled = STATE_FIELDS.some(field => searchParams.has(`baseline_${field}`))
  const baselineState = searchParams.get('baseline_state') ?? 'all'
  const contextLabel = `${selectedState === 'all' ? 'All states' : displayLabel(selectedState)}${comparisonEnabled ? ` vs ${displayLabel(baselineState)}` : ''}`

  const update = (field: string, value: string) => {
    const next = new URLSearchParams(searchParams)
    if (value === '' || (field === 'state' && value === 'all')) next.delete(field)
    else next.set(field, value)
    onChange(next)
  }
  return (
    <div className={`border border-line-bright bg-panel ${compact ? 'shadow-2xl' : ''}`}>
      <div className="flex min-h-10 flex-wrap items-center gap-2 px-2 py-1.5">
        <button type="button" aria-expanded={panelOpen} onClick={() => setPanelOpen(open => !open)} className="inline-flex h-8 items-center gap-2 px-2 text-[9px] font-bold uppercase tracking-[0.12em] text-control-fg transition-colors hover:bg-raised hover:text-ink">
          <SlidersHorizontal size={13} aria-hidden="true" /> Context
          <ChevronDown size={12} className={`transition-transform ${panelOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
        <span className={`border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.08em] ${selectedState === 'all' && !comparisonEnabled ? 'border-line-bright text-ink-dim' : 'border-electric/45 bg-electric/10 text-electric'}`}>
          {contextLabel}
        </span>
        {controls ? <div className="order-3 flex w-full min-w-0 items-center gap-2 sm:order-none sm:ml-auto sm:w-auto">{controls}</div> : null}
        {metadata ? <span className={controls ? 'text-[9px] text-ink-muted sm:ml-0' : 'ml-auto text-[9px] text-ink-muted'}>{metadata.evidence.exposureMinutes.toLocaleString()} min · {metadata.evidence.matchCount.toLocaleString()} matches</span> : null}
      </div>
      {panelOpen ? <fieldset className="border-t border-line-bright px-3 pb-3 pt-2">
        <legend className="sr-only">Game-state context</legend>
        <div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(260px,0.9fr)_minmax(360px,1.1fr)] lg:items-end">
        <Control text="State">
          <select aria-label="Game state" value={selectedState} onChange={event => update('state', event.target.value)} className="event-lens-control">
            <option value="all">All states</option>
            {(['drawing', 'winning', 'losing'] as const).map(value => (
              <option key={value} value={value} disabled={Boolean(refinements && !refinements.states.includes(value) && selectedState !== value)}>{displayLabel(value)}</option>
            ))}
          </select>
        </Control>
        <div className="grid min-w-0 grid-cols-[auto_minmax(0,1fr)] items-center gap-3">
          <button type="button" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen(open => !open)} className="event-lens-control w-auto shrink-0 whitespace-nowrap">
            {advancedOpen ? 'Hide refinements' : 'Refine state'}
          </button>
          {metadata ? (
            <div className="min-w-0 flex-1 text-right text-[10px] leading-relaxed text-ink-dim" aria-live="polite">
              <span className="block text-[11px] font-normal text-ink">{metadata.evidence.exposureMinutes.toLocaleString()} minutes · {metadata.evidence.episodeCount.toLocaleString()} episodes · {metadata.evidence.matchCount.toLocaleString()} matches</span>
              <span className={`block ${metadata.evidence.matchesExcluded ? 'text-gold' : ''}`}>{metadata.evidence.matchesExcluded.toLocaleString()} excluded · {metadata.evidence.formulaVersion}</span>
              {metadata.evidence.empty ? <span className="text-amber-300">No eligible state data. Rebuild the match state foundations.</span> : null}
            </div>
          ) : <span className="text-[10px] text-ink-dim">Loading state evidence…</span>}
        </div>
        </div>
      {advancedOpen ? <div className="mt-3 grid gap-3 bg-raised/45 p-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        <p className="text-[10px] leading-relaxed text-ink-dim sm:col-span-2 lg:col-span-3 xl:col-span-6">Time in state limits events to a window after the score last changed.</p>
        <Control text="Exact goal difference">
          <select aria-label="Exact goal difference" value={selectedDifference} onChange={event => update('goal_difference', event.target.value)} className="event-lens-control">
            <option value="">Any</option>
            {withCurrent(refinements?.goalDifferences, selectedDifference).sort((a, b) => Number(a) - Number(b)).map(value => <option key={value} value={value}>{Number(value) > 0 ? `+${value}` : value}</option>)}
          </select>
        </Control>
        <Control text="Match phase">
          <select aria-label="Match phase" value={selectedPhase} onChange={event => update('phase', event.target.value)} className="event-lens-control">
            <option value="">Any phase</option>
            {withCurrent(refinements?.phases, selectedPhase).map(value => <option key={value} value={value}>{displayLabel(String(value))}</option>)}
          </select>
        </Control>
        <Control text="State provenance">
          <select aria-label="State provenance" value={selectedProvenance} onChange={event => update('draw_provenance', event.target.value)} className="event-lens-control">
            <option value="">Any provenance</option>
            {withCurrent(refinements?.drawProvenances, selectedProvenance).map(value => <option key={value} value={value}>{displayLabel(String(value))}</option>)}
          </select>
        </Control>
        <Control text="At least this long (seconds)">
          <input aria-label="At least this many seconds in the state" inputMode="numeric" type="number" min={0} value={searchParams.get('minimum_state_age_seconds') ?? ''} onChange={event => update('minimum_state_age_seconds', event.target.value)} className="event-lens-control" placeholder="From state change" />
        </Control>
        <Control text="At most this long (seconds)">
          <input aria-label="At most this many seconds in the state" inputMode="numeric" type="number" min={0} value={searchParams.get('maximum_state_age_seconds') ?? ''} onChange={event => update('maximum_state_age_seconds', event.target.value)} className="event-lens-control" placeholder={refinements?.stateAgeSeconds.maximum?.toString() ?? 'No limit'} />
        </Control>
        <Control text="Comparison baseline">
          <div className="flex gap-1">
            <button type="button" aria-pressed={comparisonEnabled} onClick={() => {
              const next = new URLSearchParams(searchParams)
              if (comparisonEnabled) STATE_FIELDS.forEach(field => next.delete(`baseline_${field}`))
              else next.set('baseline_state', 'all')
              onChange(next)
            }} className="event-lens-control flex-1 text-left">{comparisonEnabled ? 'On' : 'Off'}</button>
            {comparisonEnabled ? (
              <select aria-label="Baseline game state" value={searchParams.get('baseline_state') ?? 'all'} onChange={event => update('baseline_state', event.target.value)} className="event-lens-control flex-[2]">
                {['all', 'drawing', 'winning', 'losing'].map(value => <option key={value} value={value}>{displayLabel(value)}</option>)}
              </select>
            ) : null}
          </div>
        </Control>
      </div> : null}
      </fieldset> : null}
    </div>
  )
}

function Control({ text, children }: { text: string; children: ReactNode }) {
  return <label className="min-w-0 text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim"><span className="mb-1 block">{text}</span>{children}</label>
}
