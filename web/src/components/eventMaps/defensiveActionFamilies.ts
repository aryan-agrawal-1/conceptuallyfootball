import type { DefensiveActionFamily } from '../../types/eventMaps'

export const DEFENSIVE_ACTION_FAMILIES: ReadonlyArray<{
  value: DefensiveActionFamily
  label: string
}> = [
  { value: 'recovery', label: 'Recoveries' },
  { value: 'tackle', label: 'Tackles' },
  { value: 'interception', label: 'Interceptions' },
  { value: 'blocked_pass', label: 'Blocked passes' },
  { value: 'defensive_aerial', label: 'Defensive aerials' },
  { value: 'defensive_challenge', label: 'Defensive challenges' },
  { value: 'clearance', label: 'Clearances' },
]

export const ALL_DEFENSIVE_ACTION_FAMILIES: DefensiveActionFamily[] =
  DEFENSIVE_ACTION_FAMILIES.map(option => option.value)

const ACTION_FAMILY_LABELS = new Map(
  DEFENSIVE_ACTION_FAMILIES.map(({ value, label }) => [value, label]),
)

export function defensiveActionFamilyLabel(value: DefensiveActionFamily) {
  return ACTION_FAMILY_LABELS.get(value) ?? value
}

export function defensiveActionSelectionLabel(selected: DefensiveActionFamily[]) {
  if (selected.length === ALL_DEFENSIVE_ACTION_FAMILIES.length) return 'All defensive actions'
  if (selected.length === 1) return defensiveActionFamilyLabel(selected[0])
  return `${selected.length} action types`
}
