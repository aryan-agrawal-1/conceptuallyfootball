import { Link } from 'react-router-dom'
import { ArrowUpRight, Loader2 } from 'lucide-react'
import { HudFrame } from '../hud/Hud'
import { useScope } from '../../context/ScopeContext'
import type { GalaxyEdge } from '../../types/api'

export function ProfileSimilarPlayers({
  edges,
  isLoading,
  isError,
  scopeLabel,
}: {
  edges: GalaxyEdge[]
  isLoading: boolean
  isError: boolean
  scopeLabel: string
}) {
  const { buildScopedPath } = useScope()

  return (
    <HudFrame
      className="h-full w-full"
      bodyClassName="flex flex-1 flex-col"
      header={<span className="text-electric/90">Similar players</span>}
      footer={<span>{scopeLabel}</span>}
    >
      <div className="flex min-h-[220px] flex-1 flex-col p-3">
        {isLoading && (
          <div className="flex flex-1 items-center justify-center gap-2 text-[11px] uppercase tracking-[0.18em] text-ink-muted">
            <Loader2 size={14} className="animate-spin text-electric" />
            Scanning similarity matrix
          </div>
        )}

        {isError && !isLoading && (
          <p className="flex flex-1 items-center justify-center px-4 text-center text-[12px] leading-relaxed text-ink-muted">
            Similar players are unavailable for this league-season.
          </p>
        )}

        {!isLoading && !isError && edges.length === 0 && (
          <p className="flex flex-1 items-center justify-center px-4 text-center text-[12px] leading-relaxed text-ink-muted">
            No similar players found for this profile.
          </p>
        )}

        {!isLoading && !isError && edges.length > 0 && (
          <div className="flex flex-col divide-y divide-electric/10 border border-electric/15 bg-mat/35">
            {edges.slice(0, 5).map(edge => (
              <Link
                key={`${edge.to_galaxy_player_id}-${edge.rank}`}
                to={buildScopedPath(`/player/${edge.to_player_id}`)}
                className="group grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 px-2.5 py-2 text-left transition-colors hover:bg-electric/10"
              >
                <span className="font-mono text-[10px] text-electric/55">
                  #{edge.rank}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[12px] font-semibold text-ink group-hover:text-electric">
                    {edge.to_player_name}
                  </span>
                  <span className="mt-0.5 block truncate text-[10px] text-ink-muted">
                    {edge.to_team_name ?? edge.to_competition_code ?? '—'}
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  <span className="border border-electric/25 bg-electric/10 px-1.5 py-0.5 font-mono text-[10px] text-electric">
                    {Math.round(edge.profile_match_score ?? edge.similarity * 100)}
                  </span>
                  <ArrowUpRight size={12} className="text-electric/55 group-hover:text-electric" />
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </HudFrame>
  )
}
