import { Fragment, lazy, Suspense, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { BarChart3, Loader2, AlertCircle, FileImage } from 'lucide-react'
import { fetchGalaxySimilarForPlayer, fetchPlayerDetail } from '../lib/api'
import type { PlayerDetailResponse, SecondaryTeamBadge } from '../types/api'
import { useScope } from '../context/ScopeContext'
import { resolveEntityMembership, resolveEntityScope, useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { ProfileBreadcrumb } from '../components/profile/ProfileBreadcrumb'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import { ProfileKeyStats } from '../components/profile/ProfileKeyStats'
import { ProfileStatBars } from '../components/profile/ProfileStatBars'
import { ProfilePizzaSection } from '../components/profile/ProfilePizzaSection'
import { ProfileEligibilityBanner } from '../components/profile/ProfileEligibilityBanner'
import { ProfileScopeSelector } from '../components/profile/ProfileScopeSelector'
import { ProfileSimilarPlayers } from '../components/profile/ProfileSimilarPlayers'
import type { ProfileRateMode } from '../lib/profileMetrics'
import { buildPlayerCreateChartsPath } from '../lib/createChartsUrl'
import type { PositionGroup, SearchPlayerMembership } from '../types/api'
import { scopeIncludesMembership } from '../lib/scopeMembership'
import { cn } from '../lib/utils'
import { useSeoMeta } from '../lib/seo'

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

type ProfilePercentileMode = 'league' | 'scope'

function aggregateScopeLabel(code: string): string {
  if (code === 'BIG5') return 'Big 5'
  if (code === 'ALL') return 'All'
  return code
}

function FormerClubsNote({ teams }: { teams: SecondaryTeamBadge[] | undefined }) {
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
            to={buildScopedPath(`/team/${t.canonical_team_id}`)}
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
  const { globalPlayers } = useSearchPaletteIndex(true)
  const playerId = Number(id)
  const playerEntity = useMemo(
    () => globalPlayers.find(p => p.canonical_player_id === playerId),
    [globalPlayers, playerId],
  )

  useEffect(() => {
    if (!Number.isFinite(playerId) || !playerEntity) return
    const hasCurrent = playerEntity.memberships.some(m => scopeIncludesMembership(scope, m))
    if (hasCurrent) return
    const nextScope = resolveEntityScope(playerEntity.memberships, scope)
    if (nextScope) {
      navigate(buildScopedPath(`/player/${playerId}`, nextScope), { replace: true })
    }
  }, [buildScopedPath, navigate, playerEntity, playerId, scope])

  const concreteMembership = useMemo(
    () => (playerEntity ? resolveEntityMembership(playerEntity.memberships, scope) : undefined),
    [playerEntity, scope],
  )
  const isAggregateScope = scope.competition === 'BIG5' || scope.competition === 'ALL'
  const detailCompetition = concreteMembership?.competition ?? scope.competition
  const detailSeason = concreteMembership?.season ?? scope.season

  const { data, isLoading, isError, error } = useQuery({
    queryKey: [
      'player-detail',
      id,
      detailCompetition,
      detailSeason,
      isAggregateScope ? scope.competition : null,
    ],
    queryFn: () =>
      fetchPlayerDetail(Number(id), {
        competition: detailCompetition,
        season: detailSeason,
        include: isAggregateScope ? 'meta,scope_percentiles' : 'meta',
        percentile_scope: isAggregateScope ? scope.competition : undefined,
      }),
    enabled: !!id && (!isAggregateScope || concreteMembership != null),
  })

  if (isLoading) {
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

  return <ProfileLayout player={data} meta={data.meta} memberships={playerEntity?.memberships ?? []} />
}

function ProfileLayout({
  player,
  meta,
  memberships,
}: {
  player: PlayerDetailResponse
  meta: NonNullable<PlayerDetailResponse['meta']>
  memberships: SearchPlayerMembership[]
}) {
  const [rateMode, setRateMode] = useState<ProfileRateMode>('per90')
  const [percentileMode, setPercentileMode] = useState<ProfilePercentileMode>('league')
  const [exportOpen, setExportOpen] = useState(false)
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()

  useSeoMeta({
    title: `${player.canonical_player_name} Stats | ${player.season_label} Football Data`,
    description: `${player.canonical_player_name} football stats for ${player.canonical_team_name ?? player.competition_code} in ${player.season_label}: per 90 metrics, percentiles, xG, xA, similar players and comparison tools.`,
    canonicalPath: `/player/${player.canonical_player_id}`,
  })

  const showLowSampleBanner = !player.eligibility.percentiles_eligible
  const isAggregateScope = scope.competition === 'BIG5' || scope.competition === 'ALL'
  const canUseScopePercentiles = isAggregateScope && player.scope_percentiles != null
  const activePercentileMap =
    percentileMode === 'scope' && canUseScopePercentiles ? player.scope_percentiles ?? {} : player.percentiles
  const percentileScopeLabel =
    percentileMode === 'scope' && canUseScopePercentiles ? aggregateScopeLabel(scope.competition) : player.competition_code
  const similarScopeLabel = `${player.competition_code} ${player.season_label}`
  const similarQuery = useQuery({
    queryKey: ['profile-similar-players', player.competition_code, player.season_label, player.canonical_player_id],
    queryFn: () =>
      fetchGalaxySimilarForPlayer(
        player.canonical_player_id,
        player.competition_code,
        player.season_label,
      ),
    staleTime: 10 * 60 * 1000,
  })

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
                to={buildScopedPath(`/team/${player.canonical_team_id}`)}
                className="text-electric/90 hover:text-electric hover:underline"
              >
                {player.canonical_team_name}
              </Link>
            ) : (
              <span>{player.canonical_team_name ?? '—'}</span>
            )}
            <FormerClubsNote teams={player.secondary_teams} />
            {' '}
            · {player.minutes.toLocaleString()} min
          </p>
          <p className="mt-2 text-[11px] text-ink-dim leading-relaxed">
            <span className="text-electric/80 font-mono uppercase tracking-[0.15em] mr-2">
              Note
            </span>
            Percentiles compare this player against other{' '}
            <span className="text-ink">
              {POSITION_COHORT_LABEL[player.position_group]}
            </span>{' '}
            in {percentileScopeLabel} {player.season_label}.
          </p>
        </div>
        <div className="flex w-full flex-col gap-2 lg:w-auto lg:shrink-0 lg:items-end">
          <div className="flex w-full flex-wrap items-center justify-start gap-2 lg:justify-end">
            <ProfileScopeSelector
              label="player-profile-scope"
              currentScope={scope}
              memberships={memberships}
              onChange={nextScope => {
                navigate(buildScopedPath(`/player/${player.canonical_player_id}`, nextScope))
              }}
            />
            <Link
              to={buildPlayerCreateChartsPath(player, rateMode)}
              className="relative flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80 whitespace-nowrap"
            >
              <BarChart3 size={13} />
              Create Chart
            </Link>
            <Link
              to={buildScopedPath(
                `/comparisons?players=${player.competition_code}:${player.season_label}:${player.canonical_player_id}`,
              )}
              className="relative px-3 py-1.5 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80 whitespace-nowrap"
            >
              Compare
            </Link>
            <ProfileRateToggle value={rateMode} onChange={setRateMode} />
            <button
              type="button"
              onClick={() => setExportOpen(true)}
              className={cn(
                'relative flex min-h-[36px] shrink-0 items-center justify-center gap-1.5 border border-electric bg-electric/15 px-4 py-2 text-[11px] font-bold uppercase tracking-[0.15em] text-electric transition-colors',
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

      {showLowSampleBanner && (
        <div className="mb-6">
          <ProfileEligibilityBanner
            reason={player.eligibility.percentiles_ineligibility_reason}
          />
        </div>
      )}

      {canUseScopePercentiles && (
        <div className="mb-6 flex flex-wrap items-center gap-2">
          {(['league', 'scope'] as const).map(mode => (
            <button
              key={mode}
              type="button"
              onClick={() => setPercentileMode(mode)}
              className={
                mode === percentileMode
                  ? 'border border-electric/50 bg-electric/10 px-3 py-1.5 text-[11px] uppercase tracking-[0.15em] text-electric'
                  : 'border border-electric/15 px-3 py-1.5 text-[11px] uppercase tracking-[0.15em] text-ink-muted hover:border-electric/35 hover:text-electric/80'
              }
            >
              {mode === 'league'
                ? 'Compare in league'
                : `Compare in ${aggregateScopeLabel(scope.competition)}`}
            </button>
          ))}
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
                isError={similarQuery.isError}
                scopeLabel={similarScopeLabel}
              />
            }
          />
        </section>

        <section aria-labelledby="profile-pizza-heading">
          <h2 id="profile-pizza-heading" className="sr-only">
            Percentile pizza chart
          </h2>
          <ProfilePizzaSection player={player} rateMode={rateMode} meta={meta} percentileMap={activePercentileMap} />
        </section>
      </div>

      {exportOpen && (
        <Suspense fallback={null}>
          <PlayerProfileExportModal
            player={player}
            meta={meta}
            initialRateMode={rateMode}
            percentileMap={activePercentileMap}
            percentileScopeLabel={percentileScopeLabel}
            similarEdges={similarQuery.data?.edges ?? []}
            similarIsLoading={similarQuery.isLoading}
            similarIsError={similarQuery.isError}
            similarScopeLabel={similarScopeLabel}
            onClose={() => setExportOpen(false)}
          />
        </Suspense>
      )}
    </div>
  )
}
