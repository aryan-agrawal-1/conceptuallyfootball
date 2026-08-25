import type { EventMatchLookup } from '../../types/eventMaps'

export type EventMapExportContext = {
  subjectName: string
  subjectType: 'Player' | 'Team'
  competition: string
  season: string
  filters: Array<{ label: string; value: string }>
}

export function eventMatchExportLabel(matches: EventMatchLookup, matchRef: string | null) {
  if (!matchRef) return 'All season matches'
  const match = matches[matchRef]
  if (!match) return `Match ${matchRef}`
  const venue = match.venue === 'home' ? 'H' : match.venue === 'away' ? 'A' : 'N'
  return `${match.opponent} (${venue}) · ${match.matchDate}`
}
