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

function clearContext(params: URLSearchParams) {
  const next = new URLSearchParams(params)
  STATE_FIELDS.forEach(field => {
    next.delete(field)
    next.delete(`baseline_${field}`)
  })
  return next
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
  const [draft, setDraft] = useState(() => new URLSearchParams(searchParams))

  const refinements = metadata?.eligibleRefinements
  const selectedState = draft.get('state') ?? 'all'
  const selectedDifference = draft.get('goal_difference') ?? ''
  const selectedPhase = draft.get('phase') ?? ''
  const selectedProvenance = draft.get('draw_provenance') ?? ''
  const baselineState = draft.get('baseline_state') ?? ''
  const appliedState = searchParams.get('state') ?? 'all'
  const appliedBaseline = searchParams.get('baseline_state') ?? ''
  const contextLabel = `${appliedState === 'all' ? 'All states' : displayLabel(appliedState)}${appliedBaseline ? ` vs ${displayLabel(appliedBaseline)}` : ''}`
  const dirty = draft.toString() !== searchParams.toString()

  const update = (field: string, value: string) => {
    setDraft(current => {
      const next = new URLSearchParams(current)
      if (value === '' || (field === 'state' && value === 'all')) next.delete(field)
      else next.set(field, value)
      return next
    })
  }

  const close = () => {
    setPanelOpen(false)
    setAdvancedOpen(false)
    setDraft(new URLSearchParams(searchParams))
  }

  const apply = () => {
    if (!dirty) return
    onChange(new URLSearchParams(draft))
    setPanelOpen(false)
    setAdvancedOpen(false)
  }

  return (
    <div className={`border border-line-bright bg-panel ${compact ? 'shadow-2xl' : ''}`}>
      <div className="flex min-h-10 flex-wrap items-center gap-2 px-2 py-1.5">
        <button type="button" aria-expanded={panelOpen} onClick={() => {
          if (panelOpen) close()
          else {
            setDraft(new URLSearchParams(searchParams))
            setPanelOpen(true)
          }
        }} className="inline-flex h-8 items-center gap-2 px-2 text-[9px] font-bold uppercase tracking-[0.12em] text-control-fg transition-colors hover:bg-raised hover:text-ink">
          <SlidersHorizontal size={13} aria-hidden="true" /> Context
          <ChevronDown size={12} className={`transition-transform ${panelOpen ? 'rotate-180' : ''}`} aria-hidden="true" />
        </button>
        <span className={`border px-2 py-1 text-[9px] font-bold uppercase tracking-[0.08em] ${appliedState === 'all' && !appliedBaseline ? 'border-line-bright text-ink-dim' : 'border-electric/45 bg-electric/10 text-electric'}`}>{contextLabel}</span>
        {controls ? <div className="order-3 flex w-full min-w-0 items-center gap-2 sm:order-none sm:ml-auto sm:w-auto">{controls}</div> : null}
      </div>

      {panelOpen ? <fieldset className="border-t border-line-bright p-3">
        <legend className="sr-only">Game-state context</legend>
        <div className="flex flex-wrap items-end gap-3">
          <Control text="State" className="w-40">
            <select aria-label="Game state" value={selectedState} onChange={event => update('state', event.target.value)} className="event-lens-control">
              <option value="all">All states</option>
              {(['drawing', 'winning', 'losing'] as const).map(value => <option key={value} value={value} disabled={Boolean(refinements && !refinements.states.includes(value) && selectedState !== value)}>{displayLabel(value)}</option>)}
            </select>
          </Control>
          <Control text="Compare to" className="w-48">
            <select aria-label="Select a state to compare to" value={baselineState} onChange={event => {
              setDraft(current => {
                const next = new URLSearchParams(current)
                STATE_FIELDS.forEach(field => next.delete(`baseline_${field}`))
                if (event.target.value) next.set('baseline_state', event.target.value)
                return next
              })
            }} className="event-lens-control">
              <option value="">No comparison</option>
              {['all', 'drawing', 'winning', 'losing'].filter(value => value !== selectedState).map(value => <option key={value} value={value}>{value === 'all' ? 'All states' : displayLabel(value)}</option>)}
            </select>
          </Control>
          <button type="button" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen(open => !open)} className="event-lens-control w-auto whitespace-nowrap">{advancedOpen ? 'Hide advanced controls' : 'Advanced controls'}</button>
        </div>

        {advancedOpen ? <div className="mt-3 grid gap-3 border-t border-line-bright pt-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
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
          <Control text="From this time in state">
            <input aria-label="From this many seconds after the state began" inputMode="numeric" type="number" min={0} value={draft.get('minimum_state_age_seconds') ?? ''} onChange={event => update('minimum_state_age_seconds', event.target.value)} className="event-lens-control" placeholder="Seconds after state began" />
          </Control>
          <Control text="Until this time in state">
            <input aria-label="Until this many seconds after the state began" inputMode="numeric" type="number" min={0} value={draft.get('maximum_state_age_seconds') ?? ''} onChange={event => update('maximum_state_age_seconds', event.target.value)} className="event-lens-control" placeholder={refinements?.stateAgeSeconds.maximum?.toString() ?? 'No limit'} />
          </Control>
          <p className="text-[9px] leading-relaxed text-ink-muted sm:col-span-2 lg:col-span-3 xl:col-span-5">These limits select events by time elapsed since the score entered this state; they do not filter by the state episode’s eventual total duration.</p>
        </div> : null}

        <div className="mt-4 flex items-center justify-between gap-3 border-t border-line-bright pt-3">
          <button type="button" onClick={() => setDraft(clearContext(searchParams))} className="text-[9px] font-bold uppercase tracking-[0.12em] text-control-fg hover:text-ink">Reset</button>
          <button type="button" disabled={!dirty} onClick={apply} className="h-9 border border-electric bg-electric/15 px-4 text-[9px] font-bold uppercase tracking-[0.12em] text-electric transition-colors hover:bg-electric/25 disabled:cursor-not-allowed disabled:border-control-border disabled:bg-transparent disabled:text-control-disabled sm:min-w-36">Apply context</button>
        </div>
      </fieldset> : null}
    </div>
  )
}

function Control({ text, children, className }: { text: string; children: ReactNode; className?: string }) {
  return <label className={`min-w-0 text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim ${className ?? ''}`}><span className="mb-1 block">{text}</span>{children}</label>
}
