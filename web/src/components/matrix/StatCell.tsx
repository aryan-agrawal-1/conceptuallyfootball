import type { CSSProperties } from 'react'
import { getHeatmapStyle } from '../../lib/heatmap'
import { formatValue } from '../../lib/format'
import { STAT_CELL_PX, type ColumnUnit } from '../../lib/columns'

interface StatCellProps {
  value: number | null | undefined
  percentile?: number | null
  unit?: ColumnUnit
  heatmapEnabled?: boolean
  size?: number
}

export function StatCell({
  value,
  percentile,
  unit,
  heatmapEnabled = true,
  size = STAT_CELL_PX,
}: StatCellProps) {
  const heatStyle: CSSProperties = heatmapEnabled
    ? getHeatmapStyle(percentile ?? null)
    : {}

  const formatted = formatValue(value ?? null, unit)

  return (
    <div
      className="flex items-center justify-center text-[12px] font-normal tabular-nums transition-colors duration-150 rounded-sm"
      style={{
        width: size,
        height: size,
        ...heatStyle,
      }}
    >
      {formatted}
    </div>
  )
}
