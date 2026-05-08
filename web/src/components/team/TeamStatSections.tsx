import { HudFrame } from '../hud/Hud'
import { cn } from '../../lib/utils'
import type { TeamDetailResponse } from '../../types/api'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import { TEAM_SECTION_LAYOUT, formatTeamStatMode } from '../../lib/teamProfileMetrics'

/** Shared viewport height for stat panels so paired columns align in a grid. */
const STAT_PANEL_HEIGHT = 'min-h-[240px] h-[min(40vh,400px)]'

interface TeamStatSectionsProps {
  team: TeamDetailResponse
  rateMode: ProfileRateMode
}

function TeamSectionCard({
  sectionKey,
  team,
  rateMode,
}: {
  sectionKey: string
  team: TeamDetailResponse
  rateMode: ProfileRateMode
}) {
  const section = team.sections[sectionKey]
  if (!section?.metrics?.length) return null

  const matches = team.stats.matches ?? null

  return (
    <div className={cn('flex flex-col', STAT_PANEL_HEIGHT)}>
      <HudFrame
        className="flex h-full min-h-0 w-full min-w-0 flex-col"
        bodyClassName="min-h-0 flex flex-1 flex-col"
        header={<span className="text-electric/90">{section.label}</span>}
      >
        <div className="flex min-h-0 flex-1 flex-col px-4 pt-1 pb-3">
          <div
            className={cn(
              'my-1 grid shrink-0 grid-cols-[minmax(0,1fr)_auto_auto] items-end gap-3 border-b border-electric/15 pb-2 text-[9px] font-medium uppercase tracking-[0.2em] text-ink-muted',
            )}
          >
            <span className="text-left">Metric</span>
            <span className="text-right tabular-nums">Stat</span>
            <span
              className="w-14 shrink-0 text-right tabular-nums leading-tight"
              title="League rank"
            >
              Rank
            </span>
          </div>
          <div
            className={cn(
              'min-h-0 flex-1 overflow-y-auto overflow-x-hidden pr-1',
              '[scrollbar-width:thin] [scrollbar-color:rgba(74,158,245,0.35)_transparent]',
            )}
          >
            <div className="flex flex-col pb-1">
              {section.metrics.filter(m => m.value != null).map(m => {
                const formatted = formatTeamStatMode(m.key, m.value, matches, rateMode)
                const rk = rateMode === 'full' ? m.rank : m.rank_per_match
                return (
                  <div
                    key={m.key}
                    className="grid grid-cols-[minmax(0,1fr)_auto_auto] gap-3 items-center border-b border-electric/5 py-1.5 last:border-b-0"
                  >
                    <span className="min-w-0 text-left text-[11px] font-medium leading-snug text-ink-dim">
                      {m.label}
                    </span>
                    <span className="text-right text-[13px] font-semibold tabular-nums text-ink">
                      {formatted}
                    </span>
                    <span
                      className={cn(
                        'w-14 shrink-0 text-right font-mono text-[11px] tabular-nums',
                        rk != null ? 'font-bold text-electric' : 'text-ink-muted',
                      )}
                    >
                      {rk != null ? `#${rk}` : '—'}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </HudFrame>
    </div>
  )
}

export function TeamStatSections({ team, rateMode }: TeamStatSectionsProps) {
  return (
    <div className="flex flex-col gap-6">
      {TEAM_SECTION_LAYOUT.map(row => {
        if (row.kind === 'pair') {
          return (
            <div
              key={`row-${row.left}-${row.right}`}
              className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2"
            >
              <TeamSectionCard sectionKey={row.left} team={team} rateMode={rateMode} />
              <TeamSectionCard sectionKey={row.right} team={team} rateMode={rateMode} />
            </div>
          )
        }
        return (
          <div
            key={`row-single-${row.section}`}
            className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2"
          >
            <TeamSectionCard sectionKey={row.section} team={team} rateMode={rateMode} />
          </div>
        )
      })}
      <p className="text-[10px] text-ink-muted leading-relaxed tracking-wide">
        <span className="text-electric/80 font-mono uppercase tracking-[0.12em] mr-2">Ranks</span>
        Season ranks use full-season totals. Per match ranks use the same per-match scaling as the
        Per 90 toggle (volumes ÷ matches; percentage stats use the same ordering as season). A dash
        means no rank (missing value or not comparable in that slice).
      </p>
    </div>
  )
}
