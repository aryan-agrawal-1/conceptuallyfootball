import type { CSSProperties } from 'react'
import {
  comparisonMarkerForSlot,
} from '../../lib/comparisonConstants'
import { cn } from '../../lib/utils'

export function CompareMarkerIcon({
  slot,
  color,
  className,
}: {
  slot: number
  color: string
  className?: string
}) {
  const shape = comparisonMarkerForSlot(slot)
  const style = { '--marker-color': color } as CSSProperties
  return (
    <span
      aria-hidden="true"
      style={style}
      className={cn(
        'inline-block size-2.5 shrink-0 border border-black/70 bg-[var(--marker-color)]',
        shape === 'circle' && 'rounded-full',
        shape === 'diamond' && 'rotate-45',
        className,
      )}
    />
  )
}

export function CompareSvgMarker({
  slot,
  color,
  x,
  y,
  size = 5,
}: {
  slot: number
  color: string
  x: number
  y: number
  size?: number
}) {
  const shape = comparisonMarkerForSlot(slot)
  const common = {
    fill: color,
    stroke: 'rgba(7,8,16,0.95)',
    strokeWidth: 1,
    pointerEvents: 'none' as const,
  }
  if (shape === 'square') {
    return <rect x={x - size} y={y - size} width={size * 2} height={size * 2} {...common} />
  }
  if (shape === 'diamond') {
    return (
      <path
        d={`M ${x} ${y - size - 1} L ${x + size + 1} ${y} L ${x} ${y + size + 1} L ${x - size - 1} ${y} Z`}
        {...common}
      />
    )
  }
  return <circle cx={x} cy={y} r={size} {...common} />
}
