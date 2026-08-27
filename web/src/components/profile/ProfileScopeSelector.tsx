import type { Scope } from '../../context/ScopeContext'
import type {
  SearchPlayerMembership,
  SearchTeamMembership,
} from '../../types/api'
import { resolveProfileSlice } from '../../lib/profileSlice'
import { cn } from '../../lib/utils'

type ProfileScopeMembership = SearchPlayerMembership | SearchTeamMembership

export function ProfileSelectControl({
  label,
  ariaLabel,
  value,
  options,
  onChange,
  className,
}: {
  label: string
  ariaLabel: string
  value: string
  options: Array<{ value: string; label: string }>
  onChange: (value: string) => void
  className?: string
}) {
  return (
    <label className={cn('flex h-8 max-w-full items-center gap-1.5 border border-electric/30 bg-mat/60 px-2', className)}>
      <span className="shrink-0 text-[9px] font-mono uppercase tracking-[0.18em] text-ink-dim">{label}</span>
      <select aria-label={ariaLabel} value={value} onChange={event => onChange(event.target.value)} className="min-w-0 flex-1 bg-transparent text-[10px] font-mono uppercase tracking-[0.08em] text-electric/90 outline-none">
        {options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
    </label>
  )
}

export function ProfileScopeSelector({
  label,
  currentScope,
  memberships,
  onChange,
}: {
  label: string
  currentScope: Scope
  memberships: ProfileScopeMembership[]
  onChange: (scope: Scope) => void
}) {
  const seasons = [...new Set(memberships.map(membership => membership.season))]
  const competitions = memberships
    .filter(membership => membership.season === currentScope.season)
    .toSorted((a, b) => {
      const aDomestic = a.competition_type === 'domestic_league'
      const bDomestic = b.competition_type === 'domestic_league'
      if (aDomestic !== bDomestic) return aDomestic ? -1 : 1
      return a.competition.localeCompare(b.competition) || a.competition_season_id - b.competition_season_id
    })

  if (!seasons.length) return null

  return (
    <div aria-label={label} className="flex w-full flex-wrap items-center gap-2 lg:w-auto lg:justify-end">
      <ProfileSelectControl label="Season" ariaLabel="Profile season" value={currentScope.season} options={seasons.map(season => ({ value: season, label: season }))} onChange={season => {
        const next = resolveProfileSlice(memberships, currentScope, { season })
        if (next) onChange(next)
      }} className="w-36" />
      <ProfileSelectControl label="Competition" ariaLabel="Profile competition" value={currentScope.competition} options={competitions.map(membership => ({ value: membership.competition, label: membership.competition }))} onChange={competition => onChange({ competition, season: currentScope.season })} className="w-44" />
    </div>
  )
}
