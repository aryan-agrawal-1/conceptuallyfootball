import type { PlayerRow, StatMeta } from '../../types/api'
import {
  barKindForMetricKey,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { formatValue } from '../../lib/format'
import { COMPARISON_SLOT_STROKES } from '../../lib/comparisonConstants'
import { cn } from '../../lib/utils'

export interface CompareStatTablePlayer {
  row: PlayerRow
  slot: number
}

interface CompareStatTableProps {
  metricKeys: string[]
  players: CompareStatTablePlayer[]
  meta: StatMeta
  rateMode: ProfileRateMode
  lockedStatIndex: number | null
  hoveredStatIndex: number | null
}

export function CompareStatTable({
  metricKeys,
  players,
  meta,
  rateMode,
  lockedStatIndex,
  hoveredStatIndex,
}: CompareStatTableProps) {
  const highlight = lockedStatIndex ?? hoveredStatIndex

  return (
    <div className="overflow-x-auto border border-electric/20">
      <table className="w-full min-w-[520px] text-left text-[12px] border-collapse">
        <thead>
          <tr className="border-b border-electric/20 bg-electric/[0.06]">
            <th className="px-3 py-2.5 text-[10px] uppercase tracking-[0.18em] text-electric/80 font-mono font-medium">
              Stat
            </th>
            {players.map(({ row, slot }) => (
              <th
                key={row.canonical_player_id}
                className="px-3 py-2.5 text-[10px] uppercase tracking-[0.12em] font-mono font-medium"
                style={{ color: COMPARISON_SLOT_STROKES[slot % COMPARISON_SLOT_STROKES.length] }}
              >
                <span className="line-clamp-2">{row.canonical_player_name}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metricKeys.map((key, i) => {
            const label = stripPer90Suffix(meta.metrics[key]?.label ?? key)
            const active = highlight === i
            return (
              <tr
                key={key}
                className={cn(
                  'border-b border-electric/10 last:border-0',
                  active && 'bg-electric/10',
                )}
              >
                <td className="px-3 py-2.5 text-ink-muted font-mono text-[11px]">{label}</td>
                {players.map(({ row, slot }) => {
                  const kind = barKindForMetricKey(key)
                  const r = resolveProfileMetric(row, rateMode, kind, meta)
                  const pctOk = row.eligibility.percentiles_eligible
                  const pct = pctOk ? r.percentile : null
                  return (
                    <td key={`${row.canonical_player_id}-${key}`} className="px-3 py-2.5 align-top">
                      <div className="flex flex-col gap-0.5">
                        <span
                          className="text-ink tabular-nums"
                          style={{ color: COMPARISON_SLOT_STROKES[slot % COMPARISON_SLOT_STROKES.length] }}
                        >
                          {formatValue(r.value, r.formatUnit)}
                        </span>
                        <span className="text-[10px] text-ink-muted tabular-nums">
                          {pct != null ? `${Math.round(pct)}th percentile` : '— percentile'}
                        </span>
                      </div>
                    </td>
                  )
                })}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
