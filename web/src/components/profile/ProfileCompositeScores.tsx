import { HudFrame } from '../hud/Hud'
import { getHeatmapStyle, getPercentileTextColor } from '../../lib/heatmap'
import type { PlayerRow } from '../../types/api'
import { cn } from '../../lib/utils'

const SCORES: { id: string; label: string }[] = [
  { id: 'finishing_score', label: 'Finishing' },
  { id: 'creation_score', label: 'Creation' },
  { id: 'buildup_score', label: 'Buildup' },
  { id: 'ball_winning_score', label: 'Ball Winning' },
  { id: 'involvement_score', label: 'Involvement' },
]

interface ProfileCompositeScoresProps {
  player: PlayerRow
}

export function ProfileCompositeScores({ player }: ProfileCompositeScoresProps) {
  if (player.position_group === 'GK') {
    return null
  }

  return (
    <HudFrame header={<span>Composite scores</span>} className="w-full">
      <div className="p-4 flex flex-col gap-2">
        {SCORES.map(({ id, label }) => {
          const score = player.eligibility.scores_eligible ? (player.scores[id] ?? null) : null
          const hStyle = getHeatmapStyle(score)
          const textCol = score != null ? getPercentileTextColor(score) : undefined
          return (
            <div
              key={id}
              className="flex items-center gap-4 bg-mat/40 border border-line/80 rounded-sm px-3 h-11"
            >
              <span className="text-[11px] font-medium text-ink-dim w-32 shrink-0 uppercase tracking-wide">
                {label}
              </span>
              <div className="flex-1 h-1.5 bg-raised rounded-full overflow-hidden">
                {score !== null && (
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${score}%`,
                      background:
                        (hStyle.backgroundColor as string) || getPercentileTextColor(score),
                    }}
                  />
                )}
              </div>
              <span
                className={cn(
                  'text-[13px] font-mono tabular-nums w-10 text-right font-semibold',
                  score === null && 'text-ink-muted',
                )}
                style={score !== null ? { color: textCol } : undefined}
              >
                {score !== null ? Math.round(score) : '—'}
              </span>
            </div>
          )
        })}
      </div>
    </HudFrame>
  )
}
