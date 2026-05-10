import { Fragment, useEffect, useMemo, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2, AlertCircle, FileImage } from 'lucide-react'
import { fetchPlayerDetail } from '../lib/api'
import type { PlayerDetailResponse, SecondaryTeamBadge } from '../types/api'
import { useScope } from '../context/ScopeContext'
import { resolveEntityScope, useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { ProfileBreadcrumb } from '../components/profile/ProfileBreadcrumb'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import { ProfileKeyStats } from '../components/profile/ProfileKeyStats'
import { ProfileStatBars } from '../components/profile/ProfileStatBars'
import { ProfilePizzaSection } from '../components/profile/ProfilePizzaSection'
import { ProfileEligibilityBanner } from '../components/profile/ProfileEligibilityBanner'
import { ProfileScopeSelector } from '../components/profile/ProfileScopeSelector'
import { PlayerProfileExportModal } from '../components/profile/PlayerProfileExportModal'
import type { ProfileRateMode } from '../lib/profileMetrics'
import type { PositionGroup, SearchPlayerMembership } from '../types/api'

const POSITION_COHORT_LABEL: Record<PositionGroup, string> = {
  FWD: 'forwards',
  MID: 'midfielders',
  DEF: 'defenders',
  GK: 'goalkeepers',
  UNK: 'players',
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
    const hasCurrent = playerEntity.memberships.some(
      m => m.competition === scope.competition && m.season === scope.season,
    )
    if (hasCurrent) return
    const nextScope = resolveEntityScope(playerEntity.memberships, scope)
    if (nextScope) {
      navigate(buildScopedPath(`/player/${playerId}`, nextScope), { replace: true })
    }
  }, [buildScopedPath, navigate, playerEntity, playerId, scope])

  const { data, isLoading, isError, error } = useQuery({
    queryKey: [
      'player-detail',
      id,
      scope.competition,
      scope.season,
    ],
    queryFn: () =>
      fetchPlayerDetail(Number(id), {
        competition: scope.competition,
        season: scope.season,
        include: 'meta',
      }),
    enabled: !!id,
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
  const [exportOpen, setExportOpen] = useState(false)
  const navigate = useNavigate()
  const { scope, buildScopedPath } = useScope()

  const showLowSampleBanner = useMemo(
    () => !player.eligibility.percentiles_eligible,
    [player.eligibility.percentiles_eligible],
  )

  return (
    <div className="max-w-[1400px] mx-auto px-6 lg:px-10 py-8 pb-20">
      <ProfileBreadcrumb playerName={player.canonical_player_name} />

      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-8">
        <div className="min-w-0">
          <h1 className="text-[34px] sm:text-[40px] font-black tracking-tight text-ink leading-none mb-2 truncate">
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
            in the {player.season_label} season.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 justify-end shrink-0">
          <ProfileScopeSelector
            label="player-profile-scope"
            currentScope={scope}
            memberships={memberships}
            onChange={nextScope => {
              navigate(buildScopedPath(`/player/${player.canonical_player_id}`, nextScope))
            }}
          />
          <Link
            to={buildScopedPath(`/comparisons?players=${player.canonical_player_id}`)}
            className="relative px-3 py-1.5 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80 whitespace-nowrap"
          >
            Compare
          </Link>
          <button
            type="button"
            onClick={() => setExportOpen(true)}
            className="relative flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80 whitespace-nowrap"
          >
            <FileImage size={13} />
            Export
          </button>
          <ProfileRateToggle value={rateMode} onChange={setRateMode} />
        </div>
      </div>

      {showLowSampleBanner && (
        <div className="mb-6">
          <ProfileEligibilityBanner
            reason={player.eligibility.percentiles_ineligibility_reason}
          />
        </div>
      )}

      <div className="flex flex-col gap-8">
        <ProfileKeyStats player={player} rateMode={rateMode} meta={meta} />

        <section aria-labelledby="profile-breakdown-heading">
          <h2 id="profile-breakdown-heading" className="sr-only">
            Stat breakdown
          </h2>
          <ProfileStatBars player={player} rateMode={rateMode} meta={meta} />
        </section>

        <section aria-labelledby="profile-pizza-heading">
          <h2 id="profile-pizza-heading" className="sr-only">
            Percentile pizza chart
          </h2>
          <ProfilePizzaSection player={player} rateMode={rateMode} meta={meta} />
        </section>
      </div>

      {exportOpen && (
        <PlayerProfileExportModal
          player={player}
          meta={meta}
          initialRateMode={rateMode}
          onClose={() => setExportOpen(false)}
        />
      )}
    </div>
  )
}
