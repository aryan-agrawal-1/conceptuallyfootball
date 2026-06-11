import type { ReactNode } from 'react'
import { HudFrame } from '../hud/Hud'
import { getPercentileTextColor } from '../../lib/heatmap'
import { formatValue } from '../../lib/format'
import type { PlayerRow, StatMeta } from '../../types/api'
import {
  PROFILE_SECTION_LABEL,
  labelForBarSpec,
  profileBarSpecsForPosition,
  profileSectionOrderForPosition,
  type ProfileBarSpec,
  type ProfileRateMode,
  type ProfileUiSection,
  resolveProfileMetric,
} from '../../lib/profileMetrics'
import { cn } from '../../lib/utils'
import type { ColumnUnit } from '../../lib/columns'

function barsBySection(specs: ProfileBarSpec[], sectionOrder: ProfileUiSection[]) {
  const map = new Map<ProfileUiSection, ProfileBarSpec[]>()
  for (const s of sectionOrder) map.set(s, [])
  for (const spec of specs) {
    map.get(spec.section)!.push(spec)
  }
  return map
}

interface ProfileStatBarsProps {
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  percentileMap?: Record<string, number | null>
  similarPlayers?: ReactNode
}

export function ProfileStatBars({
  player,
  rateMode,
  meta,
  percentileMap = player.percentiles,
  similarPlayers,
}: ProfileStatBarsProps) {
  const barSpecs = profileBarSpecsForPosition(player.position_group)
  const sectionOrder = profileSectionOrderForPosition(player.position_group)
  const availableBarSpecs = barSpecs.filter(spec => {
    const resolved = resolveProfileMetric(player, rateMode, spec.bar, meta)
    return resolved.value != null
  })
  const grouped = barsBySection(availableBarSpecs, sectionOrder)
  const pctOk = player.eligibility.percentiles_eligible
  const rawOnly = !pctOk
  const displaySectionOrder =
    player.position_group === 'GK'
      ? sectionOrder.toSorted((left, right) => {
          const order: Partial<Record<ProfileUiSection, number>> = {
            shot_stopping: 0,
            distribution: 1,
            sweeper: 2,
          }
          return (order[left] ?? 99) - (order[right] ?? 99)
        })
      : sectionOrder

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 xl:grid-cols-2">
        {displaySectionOrder.map(section => {
          const rows = grouped.get(section) ?? []
          if (!rows.length) return null
          return (
            <HudFrame
              key={section}
              className="w-full"
              header={
                <span className="text-electric/90">{PROFILE_SECTION_LABEL[section]}</span>
              }
              footer={
                rawOnly ? (
                  <span className="text-electric/75">Raw values shown · percentile rank unavailable</span>
                ) : undefined
              }
            >
              <div className="flex flex-col gap-2.5 p-3">
                <div className="grid grid-cols-[minmax(8.5rem,10rem)_minmax(24rem,1fr)_3rem] items-center gap-2.5 text-[9px] uppercase tracking-[0.16em] text-electric/60 max-xl:grid-cols-[minmax(8rem,10rem)_minmax(0,1fr)_3rem]">
                  <span>Stat</span>
                  <span>Value</span>
                  <span className="text-right">%</span>
                </div>
                {rows.map(spec => (
                  <ProfileBarRow
                    key={spec.id}
                    spec={spec}
                    player={player}
                    rateMode={rateMode}
                    meta={meta}
                    pctOk={pctOk}
                    percentileMap={percentileMap}
                  />
                ))}
              </div>
            </HudFrame>
          )
        })}
        {similarPlayers}
      </div>
      {availableBarSpecs.length > 0 && (
        <p className="text-[10px] text-ink-muted leading-relaxed tracking-wide max-w-2xl">
          {rawOnly
            ? 'This profile is below the minutes threshold, so values are shown without positional percentile colouring.'
            : 'Season column shows accumulated totals where the API stores them; otherwise it shows an estimated season count from rate × minutes (ranking still uses the per-90 percentile for that stat).'}
        </p>
      )}
    </div>
  )
}

interface ProfileBarRowProps {
  spec: ProfileBarSpec
  player: PlayerRow
  rateMode: ProfileRateMode
  meta: StatMeta
  pctOk: boolean
  percentileMap: Record<string, number | null>
}

function ProfileBarRow({ spec, player, rateMode, meta, pctOk, percentileMap }: ProfileBarRowProps) {
  const resolved = resolveProfileMetric(player, rateMode, spec.bar, meta, percentileMap)
  const label = labelForBarSpec(spec, meta)
  const pct = pctOk ? resolved.percentile : null
  const rawOnly = !pctOk
  const fillPct = pct != null ? Math.min(100, Math.max(0, pct)) : 0
  const fill = pct != null ? getPercentileTextColor(pct) : 'rgba(78, 88, 120, 0.35)'
  const formatted = formatValue(resolved.value, mapUnit(resolved.formatUnit))

  return (
    <div className="grid grid-cols-[minmax(8.5rem,10rem)_minmax(24rem,1fr)_3rem] items-center gap-2.5 max-xl:grid-cols-[minmax(8rem,10rem)_minmax(0,1fr)_3rem]">
      <span className="min-w-0 truncate text-[11px] text-ink-dim leading-tight font-medium">
        {label}
      </span>

      <div
        className={cn(
          'relative h-7 rounded-sm bg-raised/80 border overflow-hidden',
          rawOnly ? 'border-electric/20 shadow-[inset_0_0_0_1px_rgba(74,158,245,0.08)]' : 'border-line/80',
        )}
      >
        <div
          className="absolute left-0 top-0 h-full transition-[width] duration-500 ease-out"
          style={{
            width: rawOnly ? '100%' : pct != null ? `${fillPct}%` : 0,
            background: rawOnly
              ? 'linear-gradient(90deg, rgba(74,158,245,0.18), rgba(31,209,124,0.08))'
              : fill,
          }}
        />
        {pct != null && !rawOnly ? (
          <>
            <span
              className="absolute inset-x-0 top-1/2 -translate-y-1/2 truncate px-2 text-[12px] font-semibold tabular-nums text-ink"
              style={{
                clipPath: `inset(0 0 0 ${fillPct}%)`,
              }}
            >
              {formatted}
            </span>
            <span
              className="absolute inset-x-0 top-1/2 -translate-y-1/2 truncate px-2 text-[12px] font-semibold tabular-nums text-black"
              style={{
                clipPath: `inset(0 ${100 - fillPct}% 0 0)`,
              }}
              aria-hidden="true"
            >
              {formatted}
            </span>
          </>
        ) : (
          <span
            className={cn(
              'absolute inset-x-0 top-1/2 -translate-y-1/2 truncate px-2 text-[12px] font-semibold tabular-nums',
              rawOnly ? 'text-ink' : 'text-ink-muted',
            )}
          >
            {formatted}
          </span>
        )}
      </div>

      <span
        className={cn(
          'text-[13px] font-mono tabular-nums w-12 text-right font-semibold shrink-0',
          rawOnly ? 'text-electric/80 text-[10px] tracking-[0.12em] uppercase' : pct != null ? '' : 'text-ink-muted',
        )}
        style={pct != null ? { color: fill } : undefined}
      >
        {rawOnly ? 'Raw' : pct != null ? Math.round(pct) : '—'}
      </span>
    </div>
  )
}

function mapUnit(u: ColumnUnit): ColumnUnit {
  return u
}
