import {
  useEffect,
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
  const btnRef = useRef<HTMLButtonElement>(null)
  const [anchor, setAnchor] = useState<Anchor | null>(null)

  const show = () => {
    const el = btnRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    setAnchor({ left: r.left, top: r.top, width: r.width, height: r.height })
  }

  const hide = () => setAnchor(null)

  useEffect(() => {
    if (!anchor) return
    const onDismiss = () => hide()
    window.addEventListener('resize', onDismiss)
    window.addEventListener('scroll', onDismiss, true)
    return () => {
      window.removeEventListener('resize', onDismiss)
      window.removeEventListener('scroll', onDismiss, true)
    }
  }, [anchor])

  const portal =
    anchor &&
    typeof document !== 'undefined' &&
    createPortal(
      <LabHelpTooltipFloater anchor={anchor}>{children}</LabHelpTooltipFloater>,
      document.body,
    )

  return (
    <span
      className={cn('relative inline-flex items-center shrink-0', className)}
      onMouseEnter={show}
      onMouseLeave={hide}
    >
      <button
        ref={btnRef}
        type="button"
        onClick={e => e.stopPropagation()}
        className={cn(
          'p-0.5 rounded border border-transparent text-electric/50 hover:text-electric hover:border-electric/30',
          'transition-colors outline-none focus-visible:ring-1 focus-visible:ring-electric/50',
        )}
        aria-label={label}
      >
        <CircleHelp size={13} strokeWidth={2} />
      </button>
      {portal}
    </span>
  )
}

function LabHelpTooltipFloater({
  anchor,
  children,
}: {
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
    const el = wrapRef.current
    if (!el) {
      setDx(0)
      setFlipUp(false)
      return
    }
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
  }, [anchor.left, anchor.top, anchor.width, anchor.height, cx, belowTop])

  return (
    <div
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
