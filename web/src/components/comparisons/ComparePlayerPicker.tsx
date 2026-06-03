import { useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { foldForSearch } from '../../lib/foldAccents'
import type { PlayerRow, PositionGroup } from '../../types/api'
import { COMPARISON_MIN_MINUTES_WARNING } from '../../lib/comparisonConstants'
import { HudFrame } from '../hud/Hud'
import { cn } from '../../lib/utils'

interface ComparePlayerPickerProps {
  open: boolean
  title: string
  /** When set, only players in this position group appear. When null (empty comparison), all positions are shown. */
  lockPosition: PositionGroup | null
  /** Already selected player-season row tokens (excluded from results). */
  excludeTokens: Set<string>
  rows: PlayerRow[]
  isLoading: boolean
  isError: boolean
  onClose: () => void
  onPick: (row: PlayerRow) => void
}

export function ComparePlayerPicker({
  open,
  title,
  lockPosition,
  excludeTokens,
  rows,
  isLoading,
  isError,
  onClose,
  onPick,
}: ComparePlayerPickerProps) {
  const [q, setQ] = useState('')

  const filtered = useMemo(() => {
    const cohort = rows.filter(p => {
      const token = `${p.competition_code}:${p.season_label}:${p.canonical_player_id}`
      if (excludeTokens.has(token)) return false
      if (lockPosition && p.position_group !== lockPosition) return false
      return true
    })
    const sorted = cohort.toSorted((a, b) => b.minutes - a.minutes)
    const trimmed = q.trim()
    if (!trimmed) return sorted
    const needle = foldForSearch(trimmed)
    return sorted.filter(p => foldForSearch(p.canonical_player_name).includes(needle))
  }, [rows, lockPosition, excludeTokens, q])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[90] flex items-start justify-center pt-[min(15vh,120px)] px-4 bg-mat/70 backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div className="w-full max-w-md" onClick={e => e.stopPropagation()}>
      <HudFrame
        className="w-full max-w-md border-electric/30 shadow-[0_0_48px_-12px_rgba(74,158,245,0.35)]"
        header={<span>{title}</span>}
      >
        <div className="p-3 flex flex-col gap-3">
          <div className="flex items-center justify-between gap-2">
            <input
              value={q}
              onChange={e => setQ(e.target.value)}
              placeholder="Search name…"
              className="min-w-0 flex-1 border border-electric/25 bg-transparent px-3 py-2 text-[16px] text-ink outline-none placeholder:text-ink-muted focus:border-electric/50 lg:text-[13px]"
              autoFocus
            />
            <button
              type="button"
              onClick={() => {
                setQ('')
                onClose()
              }}
              className="shrink-0 px-3 py-2 text-[10px] uppercase tracking-widest text-ink-muted border border-electric/20 hover:border-electric/40 hover:text-electric/80"
            >
              Close
            </button>
          </div>

          {isLoading && (
            <div className="flex items-center justify-center gap-2 py-10 text-ink-muted">
              <Loader2 className="size-4 animate-spin text-electric" />
              <span className="text-[11px] font-mono uppercase tracking-wider">Loading players…</span>
            </div>
          )}

          {isError && !isLoading && (
            <p className="py-6 text-center text-[12px] text-ember">Could not load player list.</p>
          )}

          {!isLoading && !isError && (
            <ul className="max-h-[min(50vh,360px)] overflow-y-auto border border-electric/15 divide-y divide-electric/10">
              {filtered.length === 0 ? (
                <li className="px-3 py-6 text-center text-[12px] text-ink-muted">No matching players.</li>
              ) : (
                filtered.map(p => {
                  const minutes = p.minutes ?? 0
                  const lowMins = minutes < COMPARISON_MIN_MINUTES_WARNING
                  const token = `${p.competition_code}:${p.season_label}:${p.canonical_player_id}`
                  return (
                    <li key={token}>
                      <button
                        type="button"
                        onClick={() => {
                          setQ('')
                          onPick(p)
                        }}
                        className={cn(
                          'relative w-full text-left px-3 py-2.5 flex items-center gap-2',
                          'hover:bg-electric/10 border border-transparent hover:border-electric/25',
                        )}
                      >
                        <span className="flex-1 min-w-0 truncate text-[13px] text-ink">{p.canonical_player_name}</span>
                        {p.canonical_team_name && (
                          <span className="hidden sm:inline shrink-0 truncate text-[11px] text-ink-muted max-w-[140px]">
                            {p.canonical_team_name} · {p.competition_code}
                          </span>
                        )}
                        <span className="shrink-0 text-[11px] font-mono tabular-nums text-ink-muted">
                          {minutes.toLocaleString()}′
                        </span>
                        {lowMins && (
                          <span className="shrink-0 text-[9px] uppercase tracking-wide px-1.5 py-0.5 border border-ember/40 text-ember/90">
                            Low mins
                          </span>
                        )}
                      </button>
                    </li>
                  )
                })
              )}
            </ul>
          )}
        </div>
      </HudFrame>
      </div>
    </div>
  )
}
