import type { CSSProperties } from 'react'
import { cn } from '../../lib/utils'

export function CompareMarkerIcon({
  color,
  className,
}: {
  color: string
  className?: string
}) {
  const style = { '--marker-color': color } as CSSProperties
  return (
    <span
      aria-hidden="true"
      style={style}
      className={cn(
        'inline-block size-2.5 shrink-0 border border-black/70 bg-[var(--marker-color)]',
        className,
      )}
    />
  )
}

export function CompareSvgMarker({
  color,
  x,
  y,
  size = 5,
}: {
  color: string
  x: number
  y: number
  size?: number
}) {
  const common = {
    fill: color,
    stroke: 'rgba(7,8,16,0.95)',
    strokeWidth: 1,
    pointerEvents: 'none' as const,
  }
  return <rect x={x - size} y={y - size} width={size * 2} height={size * 2} {...common} />
}
