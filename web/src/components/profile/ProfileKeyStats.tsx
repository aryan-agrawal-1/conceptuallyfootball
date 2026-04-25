import { HudFrame } from '../hud/Hud'
import { formatValue } from '../../lib/format'
import type { PlayerRow, StatMeta } from '../../types/api'
import {
  headerSpecsForPosition,
  resolveHeaderCard,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { cn } from '../../lib/utils'
import { getPercentileTextColor } from '../../lib/heatmap'

interface ProfileKeyStatsProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
}

export function ProfileKeyStats({ player, rateMode, meta }: ProfileKeyStatsProps) {
  const specs = headerSpecsForPosition(player.position_group)

  return (
    <HudFrame header={<span>Signal // Key metrics</span>} className="w-full">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-0 divide-x divide-electric/10 border-t border-electric/10">
        {specs.map(spec => {
          const r = resolveHeaderCard(player, rateMode, spec, meta)
          const pct =
            player.eligibility.percentiles_eligible && r.percentile != null
              ? r.percentile
              : null
          const pc = pct != null ? getPercentileTextColor(pct) : undefined
          return (
            <div key={spec.id} className="p-4 flex flex-col gap-2 min-h-[96px]">
              <span className="text-[10px] font-medium tracking-[0.2em] uppercase text-ink-muted">
                {r.label}
              </span>
              <span className="text-[26px] font-black text-ink leading-none tabular-nums">
                {formatValue(r.value, r.formatUnit)}
              </span>
              <div className="mt-auto flex items-center gap-2">
                <span className="text-[9px] tracking-[0.15em] uppercase text-ink-muted">
                  Pctl
                </span>
                <span
                  className={cn(
                    'text-[12px] font-mono font-bold tabular-nums px-2 py-0.5 rounded border border-line-bright/60',
                    pct == null && 'text-ink-muted border-line/50',
                  )}
                  style={
                    pct != null
                      ? { color: pc, borderColor: `${pc}55`, backgroundColor: `${pc}18` }
                      : undefined
                  }
                >
                  {pct != null ? Math.round(pct) : '—'}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </HudFrame>
  )
}
