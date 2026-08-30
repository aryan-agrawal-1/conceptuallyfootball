import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import { createPortal } from 'react-dom'
import { cn } from '../../lib/utils'
import { HudCornerMarks } from './Hud'

type TooltipAnchor = { left: number; top: number; width: number; height: number }

const VIEWPORT_PADDING = 12
const TOOLTIP_GAP = 7

export function HudTooltipSurface({
  id,
  title,
  description,
  children,
}: {
  id?: string
  title: string
  description?: ReactNode
  children?: ReactNode
}) {
  return (
    <div id={id} role="tooltip" className="relative border border-electric/30 bg-panel/95 text-left shadow-[0_12px_40px_-8px_rgba(74,158,245,0.45)] backdrop-blur-md">
      <HudCornerMarks />
      <div className="px-3 py-2">
        <p className="text-[11px] font-semibold leading-tight tracking-wide text-ink">{title}</p>
        {description ? <div className="mt-1 text-[10px] leading-snug text-ink-dim">{description}</div> : null}
        {children ? <div className="mt-2 border-t border-electric/15 pt-2 text-[9px] leading-relaxed text-ink-muted">{children}</div> : null}
      </div>
    </div>
  )
}

export function HudTooltip({
  label,
  title,
  description,
  children,
  className,
  tooltipClassName,
}: {
  label: string
  title: string
  description?: ReactNode
  children: ReactNode
  className?: string
  tooltipClassName?: string
}) {
  const triggerRef = useRef<HTMLButtonElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const [anchor, setAnchor] = useState<TooltipAnchor | null>(null)
  const [offsetX, setOffsetX] = useState(0)
  const [placeAbove, setPlaceAbove] = useState(true)
  const tooltipId = useId()

  const show = useCallback(() => {
    const trigger = triggerRef.current
    if (!trigger) return
    const rect = trigger.getBoundingClientRect()
    setAnchor({ left: rect.left, top: rect.top, width: rect.width, height: rect.height })
  }, [])
  const hide = useCallback(() => setAnchor(null), [])

  useEffect(() => {
    if (!anchor) return
    window.addEventListener('resize', hide)
    window.addEventListener('scroll', hide, true)
    return () => {
      window.removeEventListener('resize', hide)
      window.removeEventListener('scroll', hide, true)
    }
  }, [anchor, hide])

  useLayoutEffect(() => {
    if (!anchor) return
    const frame = window.requestAnimationFrame(() => {
      const tooltip = tooltipRef.current
      if (!tooltip) return
      const rect = tooltip.getBoundingClientRect()
      const centre = anchor.left + anchor.width / 2
      const minimum = VIEWPORT_PADDING + rect.width / 2
      const maximum = window.innerWidth - VIEWPORT_PADDING - rect.width / 2
      const clamped = minimum <= maximum ? Math.min(Math.max(centre, minimum), maximum) : window.innerWidth / 2
      setOffsetX(clamped - centre)
      setPlaceAbove(anchor.top >= rect.height + TOOLTIP_GAP + VIEWPORT_PADDING)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [anchor])

  const portal = anchor && typeof document !== 'undefined'
    ? createPortal(
        <div
          ref={tooltipRef}
          className={cn('pointer-events-none fixed z-[200] w-max max-w-[min(22rem,calc(100vw-1.5rem))]', tooltipClassName)}
          style={{
            left: anchor.left + anchor.width / 2,
            top: placeAbove ? anchor.top - TOOLTIP_GAP : anchor.top + anchor.height + TOOLTIP_GAP,
            transform: `translate(calc(-50% + ${offsetX}px), ${placeAbove ? '-100%' : '0'})`,
          }}
        >
          <HudTooltipSurface id={tooltipId} title={title} description={description} />
        </div>,
        document.body,
      )
    : null

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-describedby={anchor ? tooltipId : undefined}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        onKeyDown={event => {
          if (event.key === 'Escape') hide()
        }}
        className={cn('outline-none focus-visible:ring-1 focus-visible:ring-electric/70', className)}
      >
        {children}
      </button>
      {portal}
    </>
  )
}
