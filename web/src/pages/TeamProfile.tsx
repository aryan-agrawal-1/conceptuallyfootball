import { useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Loader2, AlertCircle, Layers3 } from 'lucide-react'
import { fetchTeamDetail, fetchTeamSquad } from '../lib/api'
import type { ProfileMode, ProfileModeComponent, TeamDetailResponse, TeamSquadPlayer } from '../types/api'
import { useScope } from '../context/ScopeContext'
import { resolveEntityScope, useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import type { ProfileRateMode } from '../lib/profileMetrics'
import { TeamKeyStats } from '../components/team/TeamKeyStats'
import { TeamStatSections } from '../components/team/TeamStatSections'
import { TeamSquadList } from '../components/team/TeamSquadList'
import { HudFrame } from '../components/hud/Hud'
import { ProfileScopeSelector } from '../components/profile/ProfileScopeSelector'
import { buildTeamCreateChartsPath } from '../lib/createChartsUrl'
import { formatTeamStatMode } from '../lib/teamProfileMetrics'
import type { SearchTeamMembership } from '../types/api'
import { useSeoMeta } from '../lib/seo'

type TeamProfileMode = ProfileMode

const TEAM_MODE_LABELS: Record<TeamProfileMode, string> = {
  domestic: 'Domestic',
  europe: 'Europe',
  combined: 'Combined',
}

function requestedTeamMode(value: string | null): TeamProfileMode {
  return value === 'europe' || value === 'combined' || value === 'domestic' ? value : 'domestic'
}

function withoutCombinedStandings(team: TeamDetailResponse): TeamDetailResponse {
  if (team.mode !== 'combined') return team

  return {
    ...team,
    stats: { ...team.stats, rank: null, points: null },
    ranks: Object.fromEntries(Object.keys(team.ranks).map(key => [key, null])),
    ranks_per_match: Object.fromEntries(Object.keys(team.ranks_per_match).map(key => [key, null])),
    sections: Object.fromEntries(
      Object.entries(team.sections)
        .map(([key, section]) => [
          key,
          {
            ...section,
            metrics: section.metrics
              .filter(metric => metric.key !== 'rank' && metric.key !== 'points')
              .map(metric => ({
                ...metric,
                rank: null,
                rank_per_match: null,
              })),
          },
        ]),
    ),
  }
}

export function TeamProfile() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()
  const [searchParams, setSearchParams] = useSearchParams()
  const { globalTeams } = useSearchPaletteIndex(true)
  const teamId = Number(id)
  const selectedMode = requestedTeamMode(searchParams.get('profileMode'))
  const teamEntity = globalTeams.find(t => t.canonical_team_id === teamId)

  useEffect(() => {
    if (!Number.isFinite(teamId) || !teamEntity) return
    const hasCurrent = teamEntity.memberships.some(
      m => m.competition === scope.competition && m.season === scope.season,
    )
    if (hasCurrent) return
    const nextScope = resolveEntityScope(teamEntity.memberships, scope)
    if (nextScope) {
      setSearchParams(previous => {
        const next = new URLSearchParams(previous)
        next.set('competition', nextScope.competition)
        next.set('season', nextScope.season)
        return next
      }, { replace: true })
    }
  }, [scope, setSearchParams, teamEntity, teamId])

  const detailQuery = useQuery({
    queryKey: ['team-detail', id, scope.competition, scope.season, selectedMode],
    queryFn: () =>
      fetchTeamDetail(teamId, {
        competition: scope.competition,
        season: scope.season,
        include: 'meta',
        mode: selectedMode,
      }),
    enabled: Number.isFinite(teamId) && teamId > 0,
  })

  const activeMode = detailQuery.data?.mode

  useEffect(() => {
    if (!activeMode || searchParams.get('profileMode') === activeMode) return
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      next.set('profileMode', activeMode)
      return next
    }, { replace: true })
  }, [activeMode, searchParams, setSearchParams])

  const squadQuery = useQuery({
    queryKey: ['team-squad', id, scope.competition, scope.season, activeMode],
    queryFn: () =>
      fetchTeamSquad(teamId, {
        competition: scope.competition,
        season: scope.season,
      }),
    enabled: Number.isFinite(teamId) && teamId > 0 && activeMode === 'domestic',
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
      selectedMode={activeMode ?? selectedMode}
      onModeChange={mode => {
        setSearchParams(previous => {
          const next = new URLSearchParams(previous)
          next.set('profileMode', mode)
          return next
        })
      }}
    />
  )
}

function TeamLayout({
  team,
  squad,
  squadLoading,
  memberships,
  selectedMode,
  onModeChange,
}: {
  team: TeamDetailResponse
  squad: TeamSquadPlayer[] | undefined
  squadLoading: boolean
  memberships: SearchTeamMembership[]
  selectedMode: TeamProfileMode
  onModeChange: (mode: TeamProfileMode) => void
}) {
  const displayTeam = useMemo(() => withoutCombinedStandings(team), [team])
  const meta = displayTeam.meta
  const hasMetrics = Object.values(displayTeam.stats).some(value => value != null)
  const [rateMode, setRateMode] = useState<ProfileRateMode>('full')
  const { scope, buildScopedPath, setScope } = useScope()

  useSeoMeta({
    title: `${displayTeam.canonical_team_name} Stats | ${displayTeam.season_label} Football Data`,
    description: `${displayTeam.canonical_team_name} football team stats for ${displayTeam.competition_code} ${displayTeam.season_label}: squad data, xG, xA, per-match metrics, rankings and chart tools.`,
    canonicalPath: `/team/${displayTeam.canonical_team_id}`,
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
        <span className="text-ink-dim truncate max-w-[min(560px,60vw)]" title={displayTeam.canonical_team_name}>
          {displayTeam.canonical_team_name}
        </span>
      </nav>

      <div className="mb-6 flex flex-col gap-5 sm:mb-8 sm:flex-row sm:items-end sm:justify-between sm:gap-6">
        <div className="min-w-0">
          <h1 className="mb-2 break-words text-[30px] font-black leading-tight tracking-tight text-ink sm:truncate sm:text-[40px] sm:leading-none">
            {displayTeam.canonical_team_name}
          </h1>
          <p className="text-[12px] text-ink-muted font-mono tabular-nums">
            {displayTeam.season_label} · {selectedMode === 'combined' ? 'Domestic + Europe' : displayTeam.competition_code}
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
        <div className="flex w-full flex-wrap items-center justify-start gap-2 sm:w-auto sm:justify-end sm:shrink-0">
          <ProfileScopeSelector
            label="team-profile-scope"
            currentScope={scope}
            memberships={memberships}
            onChange={nextScope => {
              setScope(nextScope)
            }}
          />
          <TeamModeSelector
            availableModes={team.available_modes ?? [selectedMode]}
            selectedMode={selectedMode}
            onChange={onModeChange}
          />
          {selectedMode !== 'combined' && (
            <Link
              to={buildTeamCreateChartsPath(displayTeam, rateMode)}
              className="relative flex items-center gap-1.5 whitespace-nowrap border border-control-border px-3 py-1.5 text-[11px] font-medium uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10"
            >
              <BarChart3 size={13} />
              Create Chart
            </Link>
          )}
          <ProfileRateToggle value={rateMode} onChange={setRateMode} />
        </div>
      </div>

      <div className="flex flex-col gap-8">
        {selectedMode === 'combined' && <TeamComponentBreakdown components={team.components ?? []} />}
        {!hasMetrics ? (
          <div className="border border-electric/20 bg-mat/45 px-4 py-5 text-[12px] text-ink-muted">
            No team performance data is available for this competition mode and season.
          </div>
        ) : (
          <>
            <TeamKeyStats team={displayTeam} meta={meta} rateMode={rateMode} />
            {selectedMode === 'combined' ? (
              <CombinedTeamStatSections team={displayTeam} rateMode={rateMode} />
            ) : (
              <TeamStatSections team={displayTeam} rateMode={rateMode} />
            )}
          </>
        )}
        {selectedMode === 'domestic' && squadLoading && (
          <div className="flex items-center gap-2 text-[11px] text-ink-muted">
            <Loader2 size={14} className="animate-spin text-electric" />
            Loading squad…
          </div>
        )}
        {selectedMode === 'domestic' && !squadLoading && squad && <TeamSquadList squad={squad} />}
      </div>
    </div>
  )
}

function TeamModeSelector({
  availableModes,
  selectedMode,
  onChange,
}: {
  availableModes: TeamProfileMode[]
  selectedMode: TeamProfileMode
  onChange: (mode: TeamProfileMode) => void
}) {
  return (
    <div className="flex max-w-full shrink-0 items-center gap-1 border border-electric/30 bg-mat/60 p-1" aria-label="Competition mode">
      {availableModes.map(mode => (
        <button
          key={mode}
          type="button"
          aria-pressed={selectedMode === mode}
          onClick={() => onChange(mode)}
          className={`min-h-7 px-2 text-[9px] font-mono uppercase tracking-[0.12em] transition-colors outline-none focus-visible:ring-1 focus-visible:ring-electric/70 ${
            selectedMode === mode
              ? 'bg-electric/15 text-electric'
              : 'text-ink-muted hover:bg-electric/5 hover:text-ink'
          }`}
        >
          {TEAM_MODE_LABELS[mode]}
        </button>
      ))}
    </div>
  )
}

function TeamComponentBreakdown({ components }: { components: ProfileModeComponent[] }) {
  return (
    <section className="border border-electric/20 bg-mat/45" aria-labelledby="combined-components-title">
      <div className="flex items-start gap-2 border-b border-electric/15 px-4 py-3">
        <Layers3 size={14} className="mt-0.5 shrink-0 text-electric" aria-hidden="true" />
        <div className="min-w-0">
          <h2 id="combined-components-title" className="text-[10px] font-mono uppercase tracking-[0.16em] text-electric">
            Combined components
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
            Totals combine the competition entries below. Standings and ranks are intentionally not combined.
          </p>
        </div>
      </div>
      {components.length ? (
        <ul className="divide-y divide-electric/10">
          {components.map((component, index) => (
            <li key={`${component.competition_season ?? index}-${component.competition_code}`} className="flex min-w-0 flex-wrap items-center justify-between gap-x-4 gap-y-1 px-4 py-2.5 text-[11px]">
              <span className="min-w-0 truncate font-medium text-ink">
                {component.competition_code} · {component.canonical_team_name ?? 'Team'}
              </span>
              <span className="text-right font-mono text-[10px] uppercase tracking-[0.08em] text-ink-muted">
                {component.competition_type ? `${component.competition_type} · ` : ''}{component.season_label}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="px-4 py-3 text-[11px] text-ink-muted">No component detail was returned for this season.</p>
      )}
    </section>
  )
}

function CombinedTeamStatSections({
  team,
  rateMode,
}: {
  team: TeamDetailResponse
  rateMode: ProfileRateMode
}) {
  const matches = team.stats.matches ?? null
  const sections = Object.entries(team.sections).filter(([, section]) => section.metrics.some(metric => metric.value != null))

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {sections.map(([key, section]) => (
          <HudFrame key={key} className="w-full" header={<span className="text-electric/90">{section.label}</span>}>
            <div className="border-t border-electric/10 px-4 pb-3 pt-1">
              <div className="grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3 border-b border-electric/15 py-2 text-[9px] font-medium uppercase tracking-[0.2em] text-ink-muted">
                <span>Metric</span>
                <span className="text-right">Stat</span>
              </div>
              {section.metrics.flatMap(metric => {
                if (metric.value == null) return []
                return [(
                  <div key={metric.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-electric/5 py-1.5 last:border-b-0">
                    <span className="min-w-0 text-[11px] font-medium leading-snug text-ink-dim">{metric.label}</span>
                    <span className="text-right text-[13px] font-semibold tabular-nums text-ink">
                      {formatTeamStatMode(metric.key, metric.value, matches, rateMode)}
                    </span>
                  </div>
                )]
              })}
            </div>
          </HudFrame>
        ))}
      </div>
      <p className="text-[10px] leading-relaxed tracking-wide text-ink-muted">
        <span className="mr-2 font-mono uppercase tracking-[0.12em] text-electric/80">Combined</span>
        These are response-provided totals across the listed components. There is no combined table,
        position, points, or ranking.
      </p>
    </div>
  )
}
