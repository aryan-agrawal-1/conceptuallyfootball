/* eslint-disable react-refresh/only-export-components -- hook module + small floater */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { getGroupHeaderTooltip, getStatHeaderTooltip } from '../../lib/statTooltips'
import { HudCornerMarks } from '../hud/Hud'

type TipAnchor = { left: number; top: number; width: number; height: number }

interface ActiveTip {
  kind: 'group' | 'leaf'
  columnId: string
  anchor: TipAnchor
}

/**
 * One portal + minimal state instead of dozens of Radix Tooltip roots (each
 * mounts Popper, Presence, DismissableLayer). Header hover stays instant when
 * scanning columns.
 */
export function useMatrixHeaderTooltip() {
  const [active, setActive] = useState<ActiveTip | null>(null)
  const hideTimer = useRef(0)

  const clearScheduledHide = useCallback(() => {
    if (hideTimer.current) {
      window.clearTimeout(hideTimer.current)
      hideTimer.current = 0
    }
  }, [])

  const hide = useCallback(() => {
    clearScheduledHide()
    setActive(null)
  }, [clearScheduledHide])

  const show = useCallback(
    (kind: 'group' | 'leaf', columnId: string, el: HTMLElement) => {
      clearScheduledHide()
      const has =
        kind === 'group' ? getGroupHeaderTooltip(columnId) : getStatHeaderTooltip(columnId)
      if (!has) {
        setActive(null)
        return
      }
      const r = el.getBoundingClientRect()
      setActive({
        kind,
        columnId,
        anchor: { left: r.left, top: r.top, width: r.width, height: r.height },
      })
    },
    [clearScheduledHide],
  )

  /** Defer hide so pointerenter on the next header can cancel it (after pointerleave on the previous). */
  const scheduleHide = useCallback(() => {
    clearScheduledHide()
    hideTimer.current = window.setTimeout(() => {
      hideTimer.current = 0
      setActive(null)
    }, 0)
  }, [clearScheduledHide])

  useEffect(() => {
    window.addEventListener('resize', hide)
    return () => {
      window.removeEventListener('resize', hide)
      clearScheduledHide()
    }
  }, [hide, clearScheduledHide])

  const portal =
    active &&
    typeof document !== 'undefined' &&
    createPortal(
      <MatrixHeaderTooltipFloater
        key={`${active.kind}-${active.columnId}`}
        active={active}
      />,
      document.body,
    )

  return { portal, show, scheduleHide, hide }
}

/** Viewport padding (px) — keep tooltip fully inside horizontal edges. */
const TOOLTIP_VIEWPORT_PAD = 12

function MatrixHeaderTooltipFloater({ active }: { active: ActiveTip }) {
  const { anchor, kind, columnId } = active
  const tip =
    kind === 'group' ? getGroupHeaderTooltip(columnId) : getStatHeaderTooltip(columnId)
  if (!tip) return null

  const wrapRef = useRef<HTMLDivElement>(null)
  /** Horizontal offset so translate(-50% + dx) matches clamped center (avoids clipping). */
  const [dx, setDx] = useState(0)

  const cx = anchor.left + anchor.width / 2
  const top = anchor.top

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) {
      setDx(0)
      return
    }
    const w = el.getBoundingClientRect().width
    const halfW = w / 2
    const vw = window.innerWidth
    const minCenter = TOOLTIP_VIEWPORT_PAD + halfW
    const maxCenter = vw - TOOLTIP_VIEWPORT_PAD - halfW
    const clamped =
      minCenter <= maxCenter
        ? Math.min(Math.max(cx, minCenter), maxCenter)
        : vw / 2
    setDx(clamped - cx)
  }, [active.columnId, active.kind, cx])

  return (
    <div
      ref={wrapRef}
      className="pointer-events-none fixed z-[200] w-max max-w-[min(20rem,calc(100vw-1.5rem))]"
      style={{
        left: cx,
        top,
        transform: `translate(calc(-50% + ${dx}px), calc(-100% - 6px))`,
      }}
    >
      <div className="relative border border-electric/30 bg-panel/95 backdrop-blur-md shadow-[0_12px_40px_-8px_rgba(74,158,245,0.45)] text-left">
        <HudCornerMarks />
        <div className="px-3 py-2">
          <p className="text-[11px] font-semibold text-ink leading-tight tracking-wide">
            {tip.fullName}
          </p>
          <p className="mt-1 text-[10px] text-ink-dim leading-snug">
            {tip.description}
          </p>
        </div>
      </div>
    </div>
  )
}
