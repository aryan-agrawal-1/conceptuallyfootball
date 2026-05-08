import type { Scope } from '../../context/ScopeContext'
import type {
  SearchPlayerMembership,
  SearchTeamMembership,
} from '../../types/api'

type ProfileScopeMembership = SearchPlayerMembership | SearchTeamMembership

function scopeValue(scope: Scope): string {
  return `${scope.competition}::${scope.season}`
}

function labelForMembership(membership: ProfileScopeMembership): string {
  return `${membership.competition} ${membership.season}`
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
  if (!memberships.length) return null

  return (
    <div className="flex min-h-[32px] items-center gap-1.5 border border-electric/30 bg-mat/60 px-2 py-1.5 shrink-0">
      <label
        htmlFor={label}
        className="text-[9px] font-mono uppercase tracking-[0.18em] text-ink-dim"
      >
        Season
      </label>
      <select
        id={label}
        value={scopeValue(currentScope)}
        onChange={event => {
          const next = memberships.find(m => scopeValue(m) === event.target.value)
          if (next) onChange({ competition: next.competition, season: next.season })
        }}
        className="max-w-[11rem] bg-transparent text-[10px] font-mono uppercase tracking-[0.08em] text-electric/90 outline-none"
      >
        {memberships.map(m => (
          <option key={scopeValue(m)} value={scopeValue(m)}>
            {labelForMembership(m)}
          </option>
        ))}
      </select>
    </div>
  )
}
