import { HudFrame } from '../hud/Hud'
import { cn } from '../../lib/utils'
import type { TeamDetailResponse, TeamStatMeta } from '../../types/api'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import { teamKeyStatSpecs } from '../../lib/teamProfileMetrics'

interface TeamKeyStatsProps {
  team: TeamDetailResponse
  meta: TeamStatMeta | undefined
  rateMode: ProfileRateMode
}

export function TeamKeyStats({ team, meta, rateMode }: TeamKeyStatsProps) {
  const specs = teamKeyStatSpecs(team, meta, rateMode)
  const rankModeLabel = rateMode === 'full' ? 'Season' : 'Per match'

  return (
    <HudFrame header={<span>Signal // Key metrics</span>} className="w-full">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-0 divide-x divide-electric/10 border-t border-electric/10">
        {specs.map(spec => {
          const rk = spec.rank
          return (
            <div key={spec.key} className="p-4 flex flex-col gap-2 min-h-[96px]">
              <span className="text-[10px] font-medium tracking-[0.2em] uppercase text-ink-muted">
                {spec.label}
              </span>
              <span className="text-[26px] font-black text-ink leading-none tabular-nums">
                {spec.value}
              </span>
              {spec.showRankRow && (
                <div className="mt-auto flex items-center gap-2">
                  <span className="text-[9px] tracking-[0.15em] uppercase text-ink-muted">
                    Lg rank
                    <span className="block text-[8px] font-normal normal-case tracking-normal text-ink-dim">
                      {rankModeLabel}
                    </span>
                  </span>
                  <span
                    className={cn(
                      'text-[12px] font-mono font-bold tabular-nums px-2 py-0.5 rounded border border-line-bright/60',
                      rk == null && 'text-ink-muted border-line/50',
                      rk != null && 'text-electric border-electric/40 bg-electric/10',
                    )}
                  >
                    {rk != null ? rk : '—'}
                  </span>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </HudFrame>
  )
}
