import { Fragment, lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, FileImage } from 'lucide-react'
import { fetchGalaxySimilarForPlayer, fetchPlayerDetail } from '../lib/api'
import type { PlayerDetailResponse, SecondaryTeamBadge } from '../types/api'
import { useScope, type Scope } from '../context/ScopeContext'
import { useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { ProfileBreadcrumb } from '../components/profile/ProfileBreadcrumb'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import { ProfileKeyStats } from '../components/profile/ProfileKeyStats'
import { ProfileStatBars } from '../components/profile/ProfileStatBars'
import { ProfilePizzaSection } from '../components/profile/ProfilePizzaSection'
import { ProfileEligibilityBanner } from '../components/profile/ProfileEligibilityBanner'
import { ProfileScopeSelector } from '../components/profile/ProfileScopeSelector'
import { ProfileSimilarPlayers } from '../components/profile/ProfileSimilarPlayers'
import type { ProfileRateMode } from '../lib/profileMetrics'
import type { PositionGroup, SearchPlayerMembership } from '../types/api'
import { profileSliceMatchesParams, resolveProfileSlice, withProfileSliceParams, type ProfileSlice } from '../lib/profileSlice'
import { cn } from '../lib/utils'
import { useSeoMeta } from '../lib/seo'
import { RelatedAnalysisSections } from '../components/editorial/RelatedAnalysisSections'

const PlayerProfileExportModal = lazy(() =>
  import('../components/profile/PlayerProfileExportModal').then(module => ({
    default: module.PlayerProfileExportModal,
  })),
)

const POSITION_COHORT_LABEL: Record<PositionGroup, string> = {
  FWD: 'forwards',
  MID: 'midfielders',
  DEF: 'defenders',
  GK: 'goalkeepers',
  UNK: 'players',
}

function comparisonScopeLabel(code: string): string {
  if (code === 'BIG5') return 'Big 5'
  if (code === 'ALL') return 'All'
  return code
}

function FormerClubsNote({
  teams,
  profileScope,
}: {
  teams: SecondaryTeamBadge[] | undefined
  profileScope: Scope
}) {
  const { buildScopedPath } = useScope()
  if (!teams?.length) return null
  return (
    <>
      {' '}
      <span className="text-ink-dim">(</span>
      <span className="text-ink-muted normal-case">formerly of </span>
      {teams.map((t, i) => (
        <Fragment key={t.canonical_team_id}>
          {i > 0 && i < teams.length - 1 && <span>, </span>}
          {i > 0 && i === teams.length - 1 && <span> and </span>}
          <Link
            to={buildScopedPath(`/team/${t.canonical_team_id}`, profileScope)}
            className="text-electric/90 hover:text-electric hover:underline"
          >
            {t.canonical_team_name}
          </Link>
        </Fragment>
      ))}
      <span className="text-ink-dim">)</span>
    </>
  )
}

export function PlayerProfile() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()
  const [searchParams, setSearchParams] = useSearchParams()
  const { globalPlayers, isLoading: searchIndexLoading } = useSearchPaletteIndex(true)
  const playerId = Number(id)
  const playerEntity = useMemo(
    () => globalPlayers.find(p => p.canonical_player_id === playerId),
    [globalPlayers, playerId],
  )

  const profileSlice = useMemo(
    () => playerEntity && resolveProfileSlice(playerEntity.memberships, scope, {
      competition: searchParams.get('profileCompetition') ?? undefined,
      season: searchParams.get('profileSeason') ?? undefined,
    }),
    [playerEntity, scope, searchParams],
  )

  useEffect(() => {
    if (!profileSlice || profileSliceMatchesParams(searchParams, profileSlice)) return
    setSearchParams(previous => withProfileSliceParams(previous, profileSlice), { replace: true })
  }, [profileSlice, searchParams, setSearchParams])

  const detailCompetition = profileSlice?.competition
  const detailSeason = profileSlice?.season
  const requestedComparisonScope = searchParams.get('comparisonScope') ?? undefined

  const { data, isLoading, isError, error } = useQuery({
    queryKey: [
      'player-detail',
      id,
      detailCompetition,
      detailSeason,
      requestedComparisonScope,
    ],
    queryFn: () =>
      fetchPlayerDetail(Number(id), {
        competition: detailCompetition!,
        season: detailSeason!,
        include: 'meta,profile_distributions',
        comparison_scope: requestedComparisonScope,
      }),
    enabled: !!id && detailCompetition != null && detailSeason != null,
  })

  if (searchIndexLoading || (playerEntity != null && profileSlice != null && isLoading)) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 size={28} className="text-electric animate-spin" />
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-96 gap-4 px-6">
        <AlertCircle size={28} className="text-ember" />
        <p className="text-[13px] text-ink-muted text-center">
          {error?.message ?? 'Player not found'}
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

  if (!data.meta) {
    return (
      <div className="max-w-xl mx-auto px-6 py-16">
        <p className="text-[13px] text-ink-muted">
          Player loaded without stat definitions. Ensure the API is called with{' '}
          <code className="text-electric/90">include=meta</code>.
        </p>
      </div>
    )
  }

  return <ProfileLayout player={data} meta={data.meta} memberships={playerEntity?.memberships ?? []} profileSlice={profileSlice} />
}

function ProfileLayout({
  player,
  meta,
  memberships,
  profileSlice,
}: {
  player: PlayerDetailResponse
  meta: NonNullable<PlayerDetailResponse['meta']>
  memberships: SearchPlayerMembership[]
  profileSlice: ProfileSlice | undefined
}) {
  const [rateMode, setRateMode] = useState<ProfileRateMode>('per90')
  const [exportOpen, setExportOpen] = useState(false)
  const { scope, buildScopedPath } = useScope()
  const [searchParams, setSearchParams] = useSearchParams()

  const setProfileSlice = (requested: Partial<ProfileSlice>) => {
    const next = resolveProfileSlice(memberships, scope, requested)
    if (!next) return
    setSearchParams(previous => withProfileSliceParams(previous, next))
  }

  useSeoMeta({
    title: `${player.canonical_player_name} Stats | ${player.season_label} Football Data`,
    description: `${player.canonical_player_name} football stats for ${player.canonical_team_name ?? player.competition_code} in ${player.season_label}: per 90 metrics, percentiles, xG, xA, similar players and comparison tools.`,
    canonicalPath: `/player/${player.canonical_player_id}`,
  })

  const domesticScope = profileSlice?.competition ?? player.competition_code
  const hasComparisonContract = player.comparison_available_scopes !== undefined
  const availableComparisonScopes = hasComparisonContract
    ? player.comparison_available_scopes ?? []
    : [domesticScope]
  const requestedComparisonScope = searchParams.get('comparisonScope')
  const comparisonScope = availableComparisonScopes.includes(requestedComparisonScope ?? '')
    ? requestedComparisonScope!
    : availableComparisonScopes[0] ?? ''
  const hasComparisonScope = comparisonScope !== ''
  const comparisonEligibility = player.comparison_eligibility ?? player.eligibility
  const exportPlayer = useMemo(
    () => ({ ...player, eligibility: comparisonEligibility }),
    [comparisonEligibility, player],
  )
  const showLowSampleBanner = !comparisonEligibility.percentiles_eligible
  const activePercentileMap = hasComparisonContract
    ? player.comparison_percentiles ?? {}
    : player.percentiles
  const activeDistributions = hasComparisonContract
    ? player.comparison_profile_distributions
    : player.profile_distributions
  const percentileScopeLabel = hasComparisonScope ? comparisonScopeLabel(comparisonScope) : 'Unavailable'
  const comparisonSeasonLabel = activeDistributions?.context.season_label ?? player.season_label
  const similarScopeLabel = `${percentileScopeLabel} ${comparisonSeasonLabel}`
  const playerTeamScope = { competition: player.competition_code, season: player.season_label }
  const similarQuery = useQuery({
    queryKey: ['profile-similar-players', player.competition_code, player.season_label, comparisonScope, player.canonical_player_id],
    queryFn: () =>
      fetchGalaxySimilarForPlayer(
        player.canonical_player_id,
        player.comparison_source_competition ?? player.competition_code,
        player.season_label,
        comparisonScope,
      ),
    enabled: hasComparisonScope && player.position_group !== 'GK',
    staleTime: 10 * 60 * 1000,
  })

  useEffect(() => {
    if (
      !searchParams.has('profileMode')
      && (hasComparisonScope
        ? searchParams.get('comparisonScope') === comparisonScope
        : !searchParams.has('comparisonScope'))
    ) return
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      next.delete('profileMode')
      if (hasComparisonScope) next.set('comparisonScope', comparisonScope)
      else next.delete('comparisonScope')
      return next
    }, { replace: true })
  }, [comparisonScope, hasComparisonScope, searchParams, setSearchParams])

  const setComparisonScope = (nextScope: string) => {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      next.set('comparisonScope', nextScope)
      return next
    })
  }

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:px-10 lg:pb-20">
      <ProfileBreadcrumb playerName={player.canonical_player_name} />

      <div className="mb-6 flex flex-col gap-5 sm:mb-8 lg:flex-row lg:items-end lg:justify-between lg:gap-6">
        <div className="min-w-0">
          <h1 className="mb-2 break-words text-[30px] font-black leading-tight tracking-tight text-ink sm:truncate sm:text-[40px] sm:leading-none">
            {player.canonical_player_name}
          </h1>
          <p className="text-[12px] text-ink-muted font-mono tabular-nums">
            {player.season_label} ·{' '}
            {player.canonical_team_id != null && player.canonical_team_name ? (
              <Link
                to={buildScopedPath(`/team/${player.canonical_team_id}`, playerTeamScope)}
                className="text-electric/90 hover:text-electric hover:underline"
              >
                {player.canonical_team_name}
              </Link>
            ) : (
              <span>{player.canonical_team_name ?? '—'}</span>
            )}
            <FormerClubsNote teams={player.secondary_teams} profileScope={playerTeamScope} />
            {' '}
            · {player.minutes != null ? player.minutes.toLocaleString() : '—'} min
          </p>
          <p className="mt-2 text-[11px] text-ink-dim leading-relaxed">
            <span className="text-electric/80 font-mono uppercase tracking-[0.15em] mr-2">
              Note
            </span>
            Percentiles compare this player against other{' '}
            <span className="text-ink">
              {POSITION_COHORT_LABEL[player.position_group]}
            </span>{' '}
            {hasComparisonScope
              ? <>in {percentileScopeLabel} {comparisonSeasonLabel}.</>
              : <>in an available domestic cohort. No eligible domestic comparison cohort exists for this season.</>}
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 lg:w-auto lg:shrink-0 lg:items-end">
          <div className="flex w-full flex-wrap items-center justify-start gap-2 lg:justify-end">
            {profileSlice && (
              <ProfileScopeSelector
                label="player-profile-scope"
                currentScope={profileSlice}
                memberships={memberships}
                onChange={nextScope => setProfileSlice(nextScope)}
              />
            )}
            <Link
              to={hasComparisonScope
                ? buildScopedPath(
                  `/comparisons?players=${player.competition_code}:${player.season_label}:${player.canonical_player_id}`,
                  { competition: comparisonScope, season: comparisonSeasonLabel },
                )
                : buildScopedPath(
                  `/comparisons?players=${player.competition_code}:${player.season_label}:${player.canonical_player_id}`,
                )}
              className="relative flex h-8 items-center whitespace-nowrap border border-control-border px-3 text-[11px] font-medium uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10"
            >
              Compare
            </Link>
            <ProfileRateToggle value={rateMode} onChange={setRateMode} />
            <button
              type="button"
              onClick={() => setExportOpen(true)}
              className={cn(
                'relative flex h-8 shrink-0 items-center justify-center gap-1.5 border border-electric bg-electric/15 px-4 text-[11px] font-bold uppercase tracking-[0.15em] text-electric transition-colors',
                'shadow-[0_0_24px_-8px_rgba(74,158,245,0.8)] hover:bg-electric/25 hover:text-ink',
                'w-full md:w-auto',
              )}
            >
              <FileImage size={13} />
              Export
            </button>
          </div>
        </div>
      </div>

      <div className="mb-6 flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Comparison cohort">
          <span className="mr-1 text-[10px] font-mono uppercase tracking-[0.15em] text-ink-dim">Compare against</span>
          {availableComparisonScopes.map(scopeCode => (
            <button key={scopeCode} type="button" onClick={() => setComparisonScope(scopeCode)} className={cn(
              'border px-3 py-1.5 text-[11px] uppercase tracking-[0.15em]',
              scopeCode === comparisonScope ? 'border-electric/50 bg-electric/10 text-electric' : 'border-control-border text-control-fg hover:border-electric hover:text-control-fg-hover active:bg-electric/10',
            )}>
              {comparisonScopeLabel(scopeCode)}
            </button>
          ))}
          {!availableComparisonScopes.length && (
            <span className="border border-control-border px-3 py-1.5 text-[11px] uppercase tracking-[0.15em] text-ink-dim">
              Unavailable
            </span>
          )}
        </div>
      </div>

      {showLowSampleBanner && (
        <div className="mb-6">
          <ProfileEligibilityBanner
            reason={comparisonEligibility.percentiles_ineligibility_reason}
            minimumEligibleMinutes={
              comparisonEligibility.minimum_eligible_minutes ?? player.meta?.minimum_eligible_minutes
            }
          />
        </div>
      )}

      <div className="flex flex-col gap-8">
        <ProfileKeyStats player={player} rateMode={rateMode} meta={meta} percentileMap={activePercentileMap} />

        <section aria-labelledby="profile-breakdown-heading">
          <h2 id="profile-breakdown-heading" className="sr-only">
            Stat breakdown
          </h2>
          <ProfileStatBars
            player={player}
            rateMode={rateMode}
            meta={meta}
            percentileMap={activePercentileMap}
            similarPlayers={
              <ProfileSimilarPlayers
                edges={similarQuery.data?.edges ?? []}
                isLoading={similarQuery.isLoading}
                isError={!hasComparisonScope || player.position_group === 'GK' || similarQuery.isError}
                scopeLabel={similarScopeLabel}
              />
            }
          />
        </section>

        <section aria-labelledby="profile-pizza-heading">
          <h2 id="profile-pizza-heading" className="sr-only">
            Percentile pizza chart
          </h2>
          <ProfilePizzaSection
            player={player}
            rateMode={rateMode}
            meta={meta}
            percentileMap={activePercentileMap}
            distributions={activeDistributions}
          />
        </section>
        <RelatedAnalysisSections kind="player" entityId={player.canonical_player_id} />
      </div>

      {exportOpen && (
        <Suspense fallback={null}>
          <PlayerProfileExportModal
            player={exportPlayer}
            meta={meta}
            initialRateMode={rateMode}
            percentileMap={activePercentileMap}
            percentileScopeLabel={percentileScopeLabel}
            distributions={activeDistributions}
            similarEdges={similarQuery.data?.edges ?? []}
            similarIsLoading={similarQuery.isLoading}
            similarIsError={!hasComparisonScope || player.position_group === 'GK' || similarQuery.isError}
            similarScopeLabel={similarScopeLabel}
            onClose={() => setExportOpen(false)}
          />
        </Suspense>
      )}
    </div>
  )
}
