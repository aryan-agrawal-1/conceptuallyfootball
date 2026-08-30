import type { DefensiveActionFamily } from '../../types/eventMaps'
import {
  ALL_DEFENSIVE_ACTION_FAMILIES,
  DEFENSIVE_ACTION_FAMILIES,
  defensiveActionSelectionLabel,
} from './defensiveActionFamilies'

export function DefensiveActionSelector({
  selected,
  onChange,
}: {
  selected: DefensiveActionFamily[]
  onChange: (selected: DefensiveActionFamily[]) => void
}) {
  const allSelected = selected.length === ALL_DEFENSIVE_ACTION_FAMILIES.length
  const toggle = (family: DefensiveActionFamily) => {
    if (selected.includes(family)) {
      if (selected.length > 1) onChange(selected.filter(value => value !== family))
      return
    }
    onChange(ALL_DEFENSIVE_ACTION_FAMILIES.filter(value => selected.includes(value) || value === family))
  }

  return (
    <details className="relative">
      <summary className="event-lens-control flex min-w-48 list-none items-center justify-between gap-3 whitespace-nowrap text-left marker:hidden">
        <span>{defensiveActionSelectionLabel(selected)}</span><span aria-hidden className="text-electric">▾</span>
      </summary>
      <div className="absolute right-0 z-30 mt-1 min-w-60 border border-control-border bg-overlay p-2 shadow-2xl">
        <label className="flex min-h-9 items-center gap-2 border-b border-line-bright px-2 text-[10px] font-bold text-ink">
          <input type="checkbox" checked={allSelected} onChange={() => onChange(ALL_DEFENSIVE_ACTION_FAMILIES)} />
          All defensive actions
        </label>
        {DEFENSIVE_ACTION_FAMILIES.map(option => (
          <label key={option.value} className="flex min-h-9 items-center gap-2 px-2 text-[10px] text-control-fg hover:bg-raised hover:text-ink">
            <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
            {option.label}
          </label>
        ))}
      </div>
    </details>
  )
}
