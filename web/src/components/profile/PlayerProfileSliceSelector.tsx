import type { SearchPlayerMembership } from '../../types/api'
import type { ProfileSlice } from '../../lib/profileSlice'

export function PlayerProfileSliceSelector({
  memberships,
  value,
  onSeasonChange,
  onCompetitionChange,
}: {
  memberships: SearchPlayerMembership[]
  value: ProfileSlice
  onSeasonChange: (season: string) => void
  onCompetitionChange: (competition: string) => void
}) {
  const seasons = [...new Set(memberships.map(membership => membership.season))]
  const competitions = memberships
    .filter(membership => membership.season === value.season)
    .toSorted((a, b) => {
      const aDomestic = a.competition_type === 'domestic_league'
      const bDomestic = b.competition_type === 'domestic_league'
      if (aDomestic !== bDomestic) return aDomestic ? -1 : 1
      return a.competition.localeCompare(b.competition) || a.competition_season_id - b.competition_season_id
    })

  if (!seasons.length) return null

  return (
    <div className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:justify-end">
      <label className="flex h-8 max-w-full items-center gap-1.5 border border-electric/30 bg-mat/60 px-2">
        <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-ink-dim">Season</span>
        <select
          aria-label="Profile season"
          value={value.season}
          onChange={event => onSeasonChange(event.target.value)}
          className="max-w-[8rem] bg-transparent text-[10px] font-mono uppercase tracking-[0.08em] text-electric/90 outline-none"
        >
          {seasons.map(season => <option key={season} value={season}>{season}</option>)}
        </select>
      </label>
      <label className="flex h-8 max-w-full items-center gap-1.5 border border-electric/30 bg-mat/60 px-2">
        <span className="text-[9px] font-mono uppercase tracking-[0.18em] text-ink-dim">Competition</span>
        <select
          aria-label="Profile competition"
          value={value.competition}
          onChange={event => onCompetitionChange(event.target.value)}
          className="max-w-[9.5rem] bg-transparent text-[10px] font-mono uppercase tracking-[0.08em] text-electric/90 outline-none sm:max-w-[11rem]"
        >
          {competitions.map(membership => (
            <option key={`${membership.competition}:${membership.competition_season_id}`} value={membership.competition}>
              {membership.competition}
            </option>
          ))}
        </select>
      </label>
    </div>
  )
}
