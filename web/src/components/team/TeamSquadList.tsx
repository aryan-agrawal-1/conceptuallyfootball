import { Link } from 'react-router-dom'
import { HudFrame } from '../hud/Hud'
import { cn } from '../../lib/utils'
import type { TeamSquadPlayer } from '../../types/api'
import { formatValue } from '../../lib/format'

const POSITION_COLORS: Record<string, string> = {
  FWD: '#F05A28',
  MID: '#4A9EF5',
  DEF: '#1FD17C',
  GK: '#A855F7',
  UNK: '#4E5878',
}

interface TeamSquadListProps {
  squad: TeamSquadPlayer[]
}

const SQUAD_GRID =
  'grid grid-cols-[minmax(0,1fr)_auto_auto_auto] gap-3 items-center px-4'

export function TeamSquadList({ squad }: TeamSquadListProps) {
  return (
    <HudFrame header={<span>Squad // Roster</span>} className="w-full">
      <div className="border-t border-electric/10">
        <div
          className={cn(
            SQUAD_GRID,
            'shrink-0 border-b border-electric/15 py-2 text-[9px] font-medium uppercase tracking-[0.2em] text-ink-muted',
          )}
        >
          <span className="text-left">Player name</span>
          <span className="w-9 shrink-0 text-center">Pos</span>
          <span className="w-14 shrink-0 text-right tabular-nums">Mins</span>
          <span className="w-10 shrink-0 text-right tabular-nums">Apps</span>
        </div>
        <div className="divide-y divide-electric/10">
          {squad.map(p => (
            <Link
              key={p.canonical_player_id}
              to={`/player/${p.canonical_player_id}`}
              className={cn(
                SQUAD_GRID,
                'py-2.5 transition-colors hover:bg-electric/5',
              )}
            >
              <span className="min-w-0 truncate text-[13px] font-medium text-ink">
                {p.canonical_player_name}
              </span>
              <span
                className="w-9 shrink-0 text-center text-[10px] font-mono uppercase"
                style={{ color: POSITION_COLORS[p.position_group] ?? POSITION_COLORS.UNK }}
              >
                {p.position_group}
              </span>
              <span className="w-14 shrink-0 text-right text-[11px] tabular-nums text-ink-muted">
                {formatValue(p.minutes, 'integer')}
              </span>
              <span className="w-10 shrink-0 text-right text-[11px] tabular-nums text-ink-dim">
                {p.appearances != null ? p.appearances : '—'}
              </span>
            </Link>
          ))}
        </div>
      </div>
    </HudFrame>
  )
}
