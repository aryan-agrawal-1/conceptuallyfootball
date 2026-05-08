import { useEffect, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle } from 'lucide-react'
import { fetchTeamDetail, fetchTeamSquad } from '../lib/api'
import type { TeamDetailResponse, TeamSquadPlayer } from '../types/api'
import { useScope } from '../context/ScopeContext'
import { resolveEntityScope, useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import type { ProfileRateMode } from '../lib/profileMetrics'
import { TeamKeyStats } from '../components/team/TeamKeyStats'
import { TeamStatSections } from '../components/team/TeamStatSections'
import { TeamSquadList } from '../components/team/TeamSquadList'
import { ProfileScopeSelector } from '../components/profile/ProfileScopeSelector'
import type { SearchTeamMembership } from '../types/api'

export function TeamProfile() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()
  const { globalTeams } = useSearchPaletteIndex(true)
  const teamId = Number(id)
  const teamEntity = globalTeams.find(t => t.canonical_team_id === teamId)

  useEffect(() => {
    if (!Number.isFinite(teamId) || !teamEntity) return
    const hasCurrent = teamEntity.memberships.some(
      m => m.competition === scope.competition && m.season === scope.season,
    )
    if (hasCurrent) return
    const nextScope = resolveEntityScope(teamEntity.memberships, scope)
    if (nextScope) {
      navigate(buildScopedPath(`/team/${teamId}`, nextScope), { replace: true })
    }
  }, [buildScopedPath, navigate, scope, teamEntity, teamId])

  const detailQuery = useQuery({
    queryKey: ['team-detail', id, scope.competition, scope.season],
    queryFn: () =>
      fetchTeamDetail(teamId, {
        competition: scope.competition,
        season: scope.season,
        include: 'meta',
      }),
    enabled: Number.isFinite(teamId) && teamId > 0,
  })

  const squadQuery = useQuery({
    queryKey: ['team-squad', id, scope.competition, scope.season],
    queryFn: () =>
      fetchTeamSquad(teamId, {
        competition: scope.competition,
        season: scope.season,
      }),
    enabled: Number.isFinite(teamId) && teamId > 0,
  })

  if (!Number.isFinite(teamId) || teamId <= 0) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4 px-6">
        <p className="text-[13px] text-ink-muted">Invalid team id</p>
        <button
          type="button"
          onClick={() => navigate(buildScopedPath('/'))}
          className="text-[12px] text-electric hover:underline"
        >
          Back to matrix
        </button>
      </div>
    )
  }

  if (detailQuery.isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 size={28} className="text-electric animate-spin" />
      </div>
    )
  }

  if (detailQuery.isError || !detailQuery.data) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4 px-6">
        <AlertCircle size={28} className="text-ember" />
        <p className="text-[13px] text-ink-muted text-center">
          {detailQuery.error?.message ?? 'Team not found'}
        </p>
        <button
          type="button"
          onClick={() => navigate(buildScopedPath('/'))}
          className="text-[12px] text-electric hover:underline"
        >
          Back to matrix
        </button>
      </div>
    )
  }

  return (
    <TeamLayout
      team={detailQuery.data}
      squad={squadQuery.data?.results}
      squadLoading={squadQuery.isLoading}
      memberships={teamEntity?.memberships ?? []}
    />
  )
}

function TeamLayout({
  team,
  squad,
  squadLoading,
  memberships,
}: {
  team: TeamDetailResponse
  squad: TeamSquadPlayer[] | undefined
  squadLoading: boolean
  memberships: SearchTeamMembership[]
}) {
  const meta = team.meta
  const [rateMode, setRateMode] = useState<ProfileRateMode>('full')
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()

  return (
    <div className="max-w-[1400px] mx-auto px-6 lg:px-10 py-8 pb-20">
      <nav
        className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.28em] text-electric/75 mb-8"
        aria-label="Breadcrumb"
      >
        <Link to={buildScopedPath('/')} className="hover:text-electric transition-colors">
          Matrix
        </Link>
        <span className="text-electric/25">//</span>
        <span className="text-ink-dim">Team</span>
        <span className="text-electric/25">//</span>
        <span className="text-ink-dim truncate max-w-[min(560px,60vw)]" title={team.canonical_team_name}>
          {team.canonical_team_name}
        </span>
      </nav>

      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-8">
        <div className="min-w-0">
          <h1 className="text-[34px] sm:text-[40px] font-black tracking-tight text-ink leading-none mb-2 truncate">
            {team.canonical_team_name}
          </h1>
          <p className="text-[12px] text-ink-muted font-mono tabular-nums">
            {team.season_label} · {team.competition_code}
          </p>
          <p className="mt-2 text-[11px] text-ink-dim leading-relaxed max-w-xl">
            <span className="text-electric/80 font-mono uppercase tracking-[0.15em] mr-2">
              Note
            </span>
            Per 90 scales volume stats by matches. xG / xA use Sofascore team totals when the feed
            includes them; otherwise they are the sum of squad players&apos; Understat xG/xA. Rank
            chips follow the toggle (season vs per-match leaderboard).
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end shrink-0">
          <ProfileScopeSelector
            label="team-profile-scope"
            currentScope={scope}
            memberships={memberships}
            onChange={nextScope => {
              navigate(buildScopedPath(`/team/${team.canonical_team_id}`, nextScope))
            }}
          />
          <ProfileRateToggle value={rateMode} onChange={setRateMode} />
        </div>
      </div>

      <div className="flex flex-col gap-8">
        <TeamKeyStats team={team} meta={meta} rateMode={rateMode} />
        <TeamStatSections team={team} rateMode={rateMode} />
        {squadLoading && (
          <div className="flex items-center gap-2 text-[11px] text-ink-muted">
            <Loader2 size={14} className="animate-spin text-electric" />
            Loading squad…
          </div>
        )}
        {!squadLoading && squad && <TeamSquadList squad={squad} />}
      </div>
    </div>
  )
}
