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
import { CircleHelp } from 'lucide-react'
import { cn } from '../../lib/utils'

interface LabHelpHoverProps {
  /** Short label for assistive tech */
  label: string
  children: ReactNode
  className?: string
}

type Anchor = { left: number; top: number; width: number; height: number }

const VIEWPORT_PAD = 12

/**
 * Small “?” hover explainer. Portaled + viewport-clamped (same idea as matrix
 * header tooltips) so right-aligned icons do not push content off-screen.
 */
export function LabHelpHover({ label, children, className }: LabHelpHoverProps) {
  const rootRef = useRef<HTMLSpanElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const [anchor, setAnchor] = useState<Anchor | null>(null)
  const [pinned, setPinned] = useState(false)
  const tooltipId = useId()

  const show = useCallback(() => {
    const el = btnRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setAnchor({ left: r.left, top: r.top, width: r.width, height: r.height })
  }, [])

  const hide = useCallback(() => setAnchor(null), [])
  const dismiss = useCallback(() => {
    setPinned(false)
    hide()
  }, [hide])

  useEffect(() => {
    if (!anchor) return
    const onDismiss = () => dismiss()
    window.addEventListener('resize', onDismiss)
    window.addEventListener('scroll', onDismiss, true)
    return () => {
      window.removeEventListener('resize', onDismiss)
      window.removeEventListener('scroll', onDismiss, true)
    }
  }, [anchor, dismiss])

  useEffect(() => {
    if (!pinned) return
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) dismiss()
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [dismiss, pinned])

  const portal =
    anchor &&
    typeof document !== 'undefined' &&
    createPortal(
      <LabHelpTooltipFloater id={tooltipId} anchor={anchor}>
        {children}
      </LabHelpTooltipFloater>,
      document.body,
    )

  return (
    <span
      ref={rootRef}
      className={cn('relative inline-flex items-center shrink-0', className)}
      onMouseEnter={show}
      onMouseLeave={() => {
        if (!pinned && document.activeElement !== btnRef.current) hide()
      }}
    >
      <button
        ref={btnRef}
        type="button"
        onClick={event => {
          event.stopPropagation()
          if (pinned) {
            dismiss()
          } else {
            show()
            setPinned(true)
          }
        }}
        onFocus={show}
        onBlur={() => {
          if (!pinned) hide()
        }}
        onKeyDown={event => {
          if (event.key !== 'Escape') return
          event.preventDefault()
          event.stopPropagation()
          dismiss()
        }}
        className={cn(
          'p-0.5 rounded border border-transparent text-electric/50 hover:text-electric hover:border-electric/30',
          'transition-colors outline-none focus-visible:ring-1 focus-visible:ring-electric/50',
        )}
        aria-label={label}
        aria-describedby={anchor ? tooltipId : undefined}
      >
        <CircleHelp size={13} strokeWidth={2} />
      </button>
      {portal}
    </span>
  )
}

function LabHelpTooltipFloater({
  id,
  anchor,
  children,
}: {
  id: string
  anchor: Anchor
  children: ReactNode
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [dx, setDx] = useState(0)
  const [flipUp, setFlipUp] = useState(false)

  const cx = anchor.left + anchor.width / 2
  const gap = 6
  const belowTop = anchor.top + anchor.height + gap

  useLayoutEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const el = wrapRef.current
      if (!el) return
      const rect = el.getBoundingClientRect()
      const w = rect.width
      const h = rect.height
      const halfW = w / 2
      const vw = window.innerWidth
      const vh = window.innerHeight
      const minCenter = VIEWPORT_PAD + halfW
      const maxCenter = vw - VIEWPORT_PAD - halfW
      const clampedCx =
        minCenter <= maxCenter ? Math.min(Math.max(cx, minCenter), maxCenter) : vw / 2
      setDx(clampedCx - cx)

      const spaceBelow = vh - belowTop - VIEWPORT_PAD
      const spaceAbove = anchor.top - VIEWPORT_PAD
      setFlipUp(h > spaceBelow && spaceAbove >= spaceBelow)
    })
    return () => window.cancelAnimationFrame(frame)
  }, [anchor.left, anchor.top, anchor.width, anchor.height, cx, belowTop])

  return (
    <div
      id={id}
      ref={wrapRef}
      role="tooltip"
      className={cn(
        'pointer-events-none fixed z-[200] w-max max-w-[min(320px,calc(100vw-24px))]',
        'border border-electric/30 bg-panel/95 backdrop-blur-md px-3 py-2.5 shadow-xl',
        'text-[11px] leading-snug text-ink-dim normal-case tracking-normal font-normal text-left',
      )}
      style={{
        left: cx,
        top: flipUp ? anchor.top - gap : belowTop,
        transform: flipUp
          ? `translate(calc(-50% + ${dx}px), calc(-100% - ${gap}px))`
          : `translate(calc(-50% + ${dx}px), 0)`,
      }}
    >
      {children}
    </div>
  )
}
