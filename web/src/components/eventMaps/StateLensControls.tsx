import { ChevronDown, Info, SlidersHorizontal } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import type { StateLensMetadata } from '../../types/eventMaps'
import { ProfileSelectControl } from '../profile/ProfileScopeSelector'
import { HudActionButton } from '../hud/Hud'
import { HudTooltip } from '../hud/HudTooltip'

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
          <ProfileSelectControl compact label="State" ariaLabel="Game state" value={selectedState} onChange={value => update('state', value)} options={[
            { value: 'all', label: 'All states' },
            ...(['drawing', 'winning', 'losing'] as const)
              .filter(value => !refinements || refinements.states.includes(value) || selectedState === value)
              .map(value => ({ value, label: displayLabel(value) })),
          ]} className="w-48" />
          <ProfileSelectControl compact label="Compare to" ariaLabel="Select a state to compare to" value={baselineState} onChange={value => {
              setDraft(current => {
                const next = new URLSearchParams(current)
                STATE_FIELDS.forEach(field => next.delete(`baseline_${field}`))
                if (value) next.set('baseline_state', value)
                return next
              })
            }} className="w-56" options={[
              { value: '', label: 'No comparison' },
              ...['all', 'drawing', 'winning', 'losing'].filter(value => value !== selectedState).map(value => ({ value, label: value === 'all' ? 'All states' : displayLabel(value) })),
            ]} />
          <button type="button" aria-expanded={advancedOpen} onClick={() => setAdvancedOpen(open => !open)} className="relative flex h-8 items-center whitespace-nowrap border border-control-border px-3 text-[9px] font-medium uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10">{advancedOpen ? 'Hide advanced controls' : 'Advanced controls'}</button>
        </div>

        {advancedOpen ? <div className="mt-3 grid gap-3 border-t border-line-bright pt-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-[repeat(3,minmax(0,1fr))_minmax(150px,0.72fr)_minmax(150px,0.72fr)_auto]">
          <ProfileSelectControl compact label="Goal difference" ariaLabel="Exact goal difference" value={selectedDifference} onChange={value => update('goal_difference', value)} options={[
            { value: '', label: 'Any' },
            ...withCurrent(refinements?.goalDifferences, selectedDifference).sort((a, b) => Number(a) - Number(b)).map(value => ({ value: String(value), label: Number(value) > 0 ? `+${value}` : String(value) })),
          ]} />
          <ProfileSelectControl compact label="Phase" ariaLabel="Match phase" value={selectedPhase} onChange={value => update('phase', value)} options={[
            { value: '', label: 'Any phase' },
            ...withCurrent(refinements?.phases, selectedPhase).map(value => ({ value: String(value), label: displayLabel(String(value)) })),
          ]} />
          <ProfileSelectControl compact label="Provenance" ariaLabel="State provenance" value={selectedProvenance} onChange={value => update('draw_provenance', value)} options={[
            { value: '', label: 'Any provenance' },
            ...withCurrent(refinements?.drawProvenances, selectedProvenance).map(value => ({ value: String(value), label: displayLabel(String(value)) })),
          ]} />
          <input aria-label="From this many seconds after the state began" inputMode="numeric" type="number" min={0} value={draft.get('minimum_state_age_seconds') ?? ''} onChange={event => update('minimum_state_age_seconds', event.target.value)} className="event-lens-control" placeholder="At least (sec)" />
          <input aria-label="Until this many seconds after the state began" inputMode="numeric" type="number" min={0} value={draft.get('maximum_state_age_seconds') ?? ''} onChange={event => update('maximum_state_age_seconds', event.target.value)} className="event-lens-control" placeholder={refinements?.stateAgeSeconds.maximum == null ? 'At most (sec)' : `At most · ${refinements.stateAgeSeconds.maximum}s`} />
          <HudTooltip label="Explain state elapsed-time limits" title="Elapsed time in state" description="These limits select events by seconds elapsed since the score entered this state. They do not filter by the state episode’s eventual total duration." className="flex size-8 items-center justify-center self-center border border-control-border text-control-fg hover:border-electric hover:text-ink">
            <Info size={12} aria-hidden="true" />
          </HudTooltip>
        </div> : null}

        <div className="mt-4 flex items-center justify-end gap-2 border-t border-line-bright pt-3">
          <button type="button" onClick={() => {
            const next = clearContext(searchParams)
            setDraft(next)
            onChange(next)
            setPanelOpen(false)
            setAdvancedOpen(false)
          }} className="relative flex h-9 items-center border border-control-border px-3 text-[9px] font-medium uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10">Reset</button>
          <HudActionButton disabled={!dirty} onClick={apply} className="h-9 px-4 py-0 text-[9px] sm:min-w-32">Apply</HudActionButton>
        </div>
      </fieldset> : null}
    </div>
  )
}
