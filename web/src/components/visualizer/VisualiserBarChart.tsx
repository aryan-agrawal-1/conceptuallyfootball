import { useMemo } from 'react'
import { cn } from '../../lib/utils'
import { shortPlayerName } from '../../lib/entityLabels'

export interface VisualiserBarDatum {
  id: number
  label: string
  sublabel?: string
  value: number
  valueText: string
  highlighted?: boolean
}

interface VisualiserBarChartProps {
  rows: VisualiserBarDatum[]
  metricLabel: string
  exportMode?: boolean
  shortenLabels?: boolean
  onSelect?: (id: number) => void
}

export function VisualiserBarChart({
  rows,
  metricLabel,
  exportMode = false,
  shortenLabels = false,
  onSelect,
}: VisualiserBarChartProps) {
  const valueCol = exportMode ? '136px' : '88px'

  const maxAbs = useMemo(
    () => rows.reduce((acc, row) => Math.max(acc, Math.abs(row.value)), 0) || 1,
    [rows],
  )

  if (!rows.length) {
    return <p className="py-12 text-center text-[12px] text-ink-muted">No rows to rank for this chart.</p>
  }

  return (
    <div className={cn('relative flex flex-col gap-2', exportMode && 'w-full max-w-[1120px]')}>
      <div
        className="grid gap-3 px-3 text-[10px] uppercase tracking-[0.22em] text-electric/75"
        style={{ gridTemplateColumns: `minmax(0,1fr) ${valueCol}` }}
      >
        <span>{metricLabel}</span>
        <span className="text-right">Value</span>
      </div>

      <div className="flex flex-col gap-2">
        {rows.map((row, index) => {
          const widthPct = Math.max((Math.abs(row.value) / maxAbs) * 100, 6)
          return (
            <button
              key={row.id}
              type="button"
              disabled={!onSelect || exportMode}
              onClick={() => onSelect?.(row.id)}
              className={cn(
                'grid items-center gap-3 border border-electric/15 bg-panel/55 text-left',
                exportMode ? 'w-full px-5 py-3.5' : 'px-3 py-2',
                !exportMode && onSelect && 'cursor-pointer transition-colors hover:border-electric/35 hover:bg-electric/8',
                row.highlighted && 'border-amber-300/45 bg-amber-300/8',
              )}
              style={{ gridTemplateColumns: `minmax(0,1fr) ${valueCol}` }}
            >
              <div className="min-w-0">
                <div className="mb-1 flex items-center gap-2">
                  <span className={cn('shrink-0 font-mono text-electric/60', exportMode ? 'text-[12px]' : 'text-[10px]')}>
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span className={cn('truncate font-medium text-ink', exportMode ? 'text-[16px]' : 'text-[13px]')}>
                    {shortenLabels ? shortPlayerName(row.label) : row.label}
                  </span>
                </div>
                {row.sublabel && (
                  <div className={cn('mb-2 truncate text-ink-muted', exportMode ? 'text-[12px]' : 'text-[10px]')}>
                    {row.sublabel}
                  </div>
                )}
                <div className={cn('overflow-hidden border border-electric/15 bg-mat/70', exportMode ? 'h-3' : 'h-2')}>
                  <div
                    className={cn(
                      'h-full',
                      row.highlighted ? 'bg-amber-300/80' : 'bg-electric/70',
                    )}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
              <div className={cn('text-right font-mono text-electric/90', exportMode ? 'text-[15px]' : 'text-[12px]')}>
                {row.valueText}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
