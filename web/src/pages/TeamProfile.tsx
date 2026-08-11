import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Loader2, AlertCircle } from 'lucide-react'
import { fetchTeamDetail, fetchTeamSquad } from '../lib/api'
import type { TeamDetailResponse, TeamSquadPlayer } from '../types/api'
import { useScope } from '../context/ScopeContext'
import { useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import type { ProfileRateMode } from '../lib/profileMetrics'
import { TeamKeyStats } from '../components/team/TeamKeyStats'
import { TeamStatSections } from '../components/team/TeamStatSections'
import { TeamSquadList } from '../components/team/TeamSquadList'
import { ProfileScopeSelector } from '../components/profile/ProfileScopeSelector'
import { buildTeamCreateChartsPath } from '../lib/createChartsUrl'
import type { SearchTeamMembership } from '../types/api'
import { profileSliceMatchesParams, resolveProfileSlice, withProfileSliceParams, type ProfileSlice } from '../lib/profileSlice'
import { useSeoMeta } from '../lib/seo'
import { RelatedAnalysisButton } from '../components/editorial/RelatedAnalysisSections'

export function TeamProfile() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()
  const [searchParams, setSearchParams] = useSearchParams()
  const { globalTeams, isLoading: searchIndexLoading } = useSearchPaletteIndex(true)
  const teamId = Number(id)
  const teamEntity = useMemo(
    () => globalTeams.find(t => t.canonical_team_id === teamId),
    [globalTeams, teamId],
  )

  const profileSlice = useMemo(
    () => teamEntity && resolveProfileSlice(teamEntity.memberships, scope, {
      competition: searchParams.get('profileCompetition') ?? undefined,
      season: searchParams.get('profileSeason') ?? undefined,
    }),
    [teamEntity, scope, searchParams],
  )

  useEffect(() => {
    if (!profileSlice || profileSliceMatchesParams(searchParams, profileSlice)) return
    setSearchParams(previous => withProfileSliceParams(previous, profileSlice), { replace: true })
  }, [profileSlice, searchParams, setSearchParams])

  const detailCompetition = profileSlice?.competition
  const detailSeason = profileSlice?.season

  const detailQuery = useQuery({
    queryKey: ['team-detail', id, detailCompetition, detailSeason],
    queryFn: () =>
      fetchTeamDetail(teamId, {
        competition: detailCompetition!,
        season: detailSeason!,
        include: 'meta',
      }),
    enabled: Number.isFinite(teamId) && teamId > 0 && detailCompetition != null && detailSeason != null,
  })

  const squadQuery = useQuery({
    queryKey: ['team-squad', id, detailCompetition, detailSeason],
    queryFn: () =>
      fetchTeamSquad(teamId, {
        competition: detailCompetition!,
        season: detailSeason!,
      }),
    enabled: Number.isFinite(teamId) && teamId > 0 && detailCompetition != null && detailSeason != null,
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

  if (searchIndexLoading || (teamEntity != null && profileSlice != null && detailQuery.isLoading)) {
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
      profileSlice={profileSlice}
    />
  )
}

function TeamLayout({
  team,
  squad,
  squadLoading,
  memberships,
  profileSlice,
}: {
  team: TeamDetailResponse
  squad: TeamSquadPlayer[] | undefined
  squadLoading: boolean
  memberships: SearchTeamMembership[]
  profileSlice: ProfileSlice | undefined
}) {
  const meta = team.meta
  const [rateMode, setRateMode] = useState<ProfileRateMode>('full')
  const { scope, buildScopedPath } = useScope()
  const [, setSearchParams] = useSearchParams()

  const setProfileSlice = (requested: Partial<ProfileSlice>) => {
    const next = resolveProfileSlice(memberships, scope, requested)
    if (!next) return
    setSearchParams(previous => withProfileSliceParams(previous, next))
  }

  useSeoMeta({
    title: `${team.canonical_team_name} Stats | ${team.season_label} Football Data`,
    description: `${team.canonical_team_name} football team stats for ${team.competition_code} ${team.season_label}: squad data, xG, xA, per-match metrics, rankings and chart tools.`,
    canonicalPath: `/team/${team.canonical_team_id}`,
  })

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:px-10 lg:pb-20">
      <nav
        className="mb-6 flex min-w-0 items-center gap-2 overflow-hidden text-[10px] font-mono uppercase tracking-[0.2em] text-electric/75 sm:mb-8 sm:tracking-[0.28em]"
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

      <div className="mb-6 flex flex-col gap-5 sm:mb-8 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
        <div className="min-w-0">
          <h1 className="mb-2 break-words text-[30px] font-black leading-tight tracking-tight text-ink sm:truncate sm:text-[40px] sm:leading-none">
            {team.canonical_team_name}
          </h1>
          <p className="text-[12px] text-ink-muted font-mono tabular-nums">
            {team.season_label} · {team.competition_code}
          </p>
          <p className="mt-2 text-[11px] text-ink-dim leading-relaxed max-w-xl">
            <span className="text-electric/80 font-mono uppercase tracking-[0.15em] mr-2">
              Note
            </span>
            Per 90 scales volume stats by matches. xG / xA use Opta sourced team totals when the feed
            includes them; otherwise they are the sum of squad players&apos; Understat xG/xA. Rank
            chips follow the toggle (season vs per-match leaderboard).
          </p>
        </div>
        <div className="flex w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end sm:shrink-0">
          {profileSlice && (
            <ProfileScopeSelector
              label="team-profile-scope"
              currentScope={profileSlice}
              memberships={memberships}
              onChange={nextScope => setProfileSlice(nextScope)}
            />
          )}
          <Link
            to={buildTeamCreateChartsPath(team, rateMode)}
            className="relative flex items-center gap-1.5 whitespace-nowrap border border-control-border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10"
          >
            <BarChart3 size={13} />
            Create Chart
          </Link>
          <ProfileRateToggle value={rateMode} onChange={setRateMode} />
          <RelatedAnalysisButton kind="team" entityId={team.canonical_team_id} />
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
