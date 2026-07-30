import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
} from 'react'
import { createPortal } from 'react-dom'
import { CircleHelp } from 'lucide-react'
import { cn } from '../../lib/utils'
import {
  REGRESSION_LAB_WALKTHROUGH_STEPS,
  saveRegressionLabWalkthroughStatus,
  shouldOfferRegressionLabWalkthrough,
} from '../../lib/regressionLabWalkthrough'

type WalkthroughMode = 'idle' | 'intro' | 'tour'
type AnchorStatus = 'checking' | 'available' | 'unavailable'

interface ViewportSize {
  width: number
  height: number
}

interface ElementRect {
  left: number
  top: number
  right: number
  bottom: number
  width: number
  height: number
}

const VIEWPORT_PADDING = 12
const CALLOUT_GAP = 14
const MOBILE_BREAKPOINT = 640
const DEFAULT_CALLOUT_SIZE = { width: 360, height: 268 }
const FOCUSABLE_SELECTOR = [
  'button:not([disabled])',
  'a[href]',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',')

function currentViewport(): ViewportSize {
  if (typeof window === 'undefined') return { width: 1024, height: 768 }
  const visualViewport = window.visualViewport
  return {
    width: visualViewport?.width ?? window.innerWidth,
    height: visualViewport?.height ?? window.innerHeight,
  }
}

function sameRect(previous: ElementRect | null, next: ElementRect): boolean {
  return Boolean(
    previous &&
      previous.left === next.left &&
      previous.top === next.top &&
      previous.width === next.width &&
      previous.height === next.height,
  )
}

function measuredRect(element: HTMLElement): ElementRect {
  const rect = element.getBoundingClientRect()
  return {
    left: rect.left,
    top: rect.top,
    right: rect.right,
    bottom: rect.bottom,
    width: rect.width,
    height: rect.height,
  }
}

function isVisibleAnchor(element: HTMLElement): boolean {
  const style = window.getComputedStyle(element)
  return style.display !== 'none' && style.visibility !== 'hidden'
}

function calloutPosition(
  anchor: ElementRect | null,
  callout: { width: number; height: number },
  viewport: ViewportSize,
): CSSProperties {
  const width = Math.min(callout.width, viewport.width - VIEWPORT_PADDING * 2)
  const height = Math.min(callout.height, viewport.height - VIEWPORT_PADDING * 2)
  const clampLeft = (left: number) =>
    Math.min(
      Math.max(left, VIEWPORT_PADDING),
      Math.max(VIEWPORT_PADDING, viewport.width - width - VIEWPORT_PADDING),
    )
  const clampTop = (top: number) =>
    Math.min(
      Math.max(top, VIEWPORT_PADDING),
      Math.max(VIEWPORT_PADDING, viewport.height - height - VIEWPORT_PADDING),
    )

  if (!anchor) {
    return {
      left: clampLeft((viewport.width - width) / 2),
      top: clampTop((viewport.height - height) / 2),
      width,
    }
  }

  if (viewport.width < MOBILE_BREAKPOINT) {
    const roomAbove = anchor.top - CALLOUT_GAP - VIEWPORT_PADDING
    const roomBelow = viewport.height - anchor.bottom - CALLOUT_GAP - VIEWPORT_PADDING
    const top =
      roomBelow >= height || roomBelow >= roomAbove
        ? anchor.bottom + CALLOUT_GAP
        : anchor.top - height - CALLOUT_GAP
    return {
      left: VIEWPORT_PADDING,
      top: clampTop(top),
      width,
    }
  }

  const centeredTop = anchor.top + anchor.height / 2 - height / 2
  const centeredLeft = anchor.left + anchor.width / 2 - width / 2
  const roomRight = viewport.width - anchor.right - CALLOUT_GAP - VIEWPORT_PADDING
  const roomLeft = anchor.left - CALLOUT_GAP - VIEWPORT_PADDING
  const roomBelow = viewport.height - anchor.bottom - CALLOUT_GAP - VIEWPORT_PADDING
  const roomAbove = anchor.top - CALLOUT_GAP - VIEWPORT_PADDING

  if (roomRight >= width) {
    return { left: anchor.right + CALLOUT_GAP, top: clampTop(centeredTop), width }
  }
  if (roomLeft >= width) {
    return { left: anchor.left - width - CALLOUT_GAP, top: clampTop(centeredTop), width }
  }
  if (roomBelow >= height) {
    return { left: clampLeft(centeredLeft), top: anchor.bottom + CALLOUT_GAP, width }
  }
  if (roomAbove >= height) {
    return { left: clampLeft(centeredLeft), top: anchor.top - height - CALLOUT_GAP, width }
  }

  const placeBelow = roomBelow >= roomAbove
  return {
    left: clampLeft(centeredLeft),
    top: clampTop(
      placeBelow ? anchor.bottom + CALLOUT_GAP : anchor.top - height - CALLOUT_GAP,
    ),
    width,
  }
}

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    element => element.getAttribute('aria-hidden') !== 'true',
  )
}

function usePrefersReducedMotion(): boolean {
  const [reducedMotion, setReducedMotion] = useState(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  )

  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const onChange = () => setReducedMotion(media.matches)
    media.addEventListener?.('change', onChange)
    return () => media.removeEventListener?.('change', onChange)
  }, [])

  return reducedMotion
}

export function RegressionLabWalkthrough() {
  const [mode, setMode] = useState<WalkthroughMode>(() =>
    shouldOfferRegressionLabWalkthrough() ? 'intro' : 'idle',
  )
  const [stepIndex, setStepIndex] = useState(0)
  const [anchorRect, setAnchorRect] = useState<ElementRect | null>(null)
  const [anchorStatus, setAnchorStatus] = useState<AnchorStatus>('checking')
  const [viewport, setViewport] = useState(currentViewport)
  const [calloutSize, setCalloutSize] = useState(DEFAULT_CALLOUT_SIZE)
  const launcherRef = useRef<HTMLButtonElement>(null)
  const dialogRef = useRef<HTMLDivElement>(null)
  const titleRef = useRef<HTMLHeadingElement>(null)
  const activeAnchorRef = useRef<HTMLElement | null>(null)
  const returnFocusRef = useRef<HTMLElement | null>(null)
  const reducedMotion = usePrefersReducedMotion()
  const activeStep = REGRESSION_LAB_WALKTHROUGH_STEPS[stepIndex]
  const isLastStep = stepIndex === REGRESSION_LAB_WALKTHROUGH_STEPS.length - 1
  const anchorAvailable = anchorStatus === 'available'

  const restoreFocus = useCallback(() => {
    const destination = returnFocusRef.current?.isConnected
      ? returnFocusRef.current
      : launcherRef.current
    returnFocusRef.current = null
    window.requestAnimationFrame(() => destination?.focus())
  }, [])

  const closeWalkthrough = useCallback(
    (status: 'skipped' | 'completed') => {
      saveRegressionLabWalkthroughStatus(status)
      setMode('idle')
      setAnchorRect(null)
      setAnchorStatus('checking')
      activeAnchorRef.current = null
      restoreFocus()
    },
    [restoreFocus],
  )

  const openTour = useCallback((opener?: HTMLElement) => {
    if (opener) returnFocusRef.current = opener
    setViewport(currentViewport())
    setAnchorRect(null)
    setAnchorStatus('checking')
    setStepIndex(0)
    setMode('tour')
  }, [])

  const goToStep = useCallback((nextStep: number) => {
    setAnchorRect(null)
    setAnchorStatus('checking')
    activeAnchorRef.current = null
    setStepIndex(
      Math.min(REGRESSION_LAB_WALKTHROUGH_STEPS.length - 1, Math.max(0, nextStep)),
    )
  }, [])

  const measureAnchor = useCallback(() => {
    const element = activeAnchorRef.current
    if (!element?.isConnected || !isVisibleAnchor(element)) {
      setAnchorStatus('unavailable')
      setAnchorRect(null)
      return
    }
    const nextRect = measuredRect(element)
    setAnchorStatus('available')
    setAnchorRect(previous => (sameRect(previous, nextRect) ? previous : nextRect))
  }, [])

  useLayoutEffect(() => {
    if (mode !== 'tour') return
    const frame = window.requestAnimationFrame(() => {
      const element = document.querySelector<HTMLElement>(activeStep.anchor)
      activeAnchorRef.current = element
      if (!element || !isVisibleAnchor(element)) {
        setAnchorStatus('unavailable')
        setAnchorRect(null)
        return
      }

      setAnchorStatus('available')
      element.scrollIntoView?.({
        behavior: reducedMotion ? 'auto' : 'smooth',
        block: 'center',
        inline: 'nearest',
      })
      measureAnchor()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [activeStep.anchor, measureAnchor, mode, reducedMotion])

  useEffect(() => {
    if (mode !== 'tour') return
    const onViewportChange = () => {
      const nextViewport = currentViewport()
      setViewport(previous =>
        previous.width === nextViewport.width && previous.height === nextViewport.height
          ? previous
          : nextViewport,
      )
      measureAnchor()
    }
    const visualViewport = window.visualViewport
    window.addEventListener('resize', onViewportChange)
    window.addEventListener('scroll', onViewportChange, { capture: true, passive: true })
    visualViewport?.addEventListener('resize', onViewportChange)
    visualViewport?.addEventListener('scroll', onViewportChange)

    const resizeObserver =
      typeof ResizeObserver === 'undefined'
        ? null
        : new ResizeObserver(() => measureAnchor())
    if (activeAnchorRef.current) resizeObserver?.observe(activeAnchorRef.current)

    return () => {
      window.removeEventListener('resize', onViewportChange)
      window.removeEventListener('scroll', onViewportChange, true)
      visualViewport?.removeEventListener('resize', onViewportChange)
      visualViewport?.removeEventListener('scroll', onViewportChange)
      resizeObserver?.disconnect()
    }
  }, [anchorAvailable, measureAnchor, mode, stepIndex])

  useLayoutEffect(() => {
    if (mode !== 'tour') return
    const dialog = dialogRef.current
    if (!dialog) return
    const updateSize = () => {
      const rect = dialog.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      setCalloutSize(previous =>
        previous.width === rect.width && previous.height === rect.height
          ? previous
          : { width: rect.width, height: rect.height },
      )
    }
    updateSize()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(updateSize)
    observer.observe(dialog)
    return () => observer.disconnect()
  }, [anchorAvailable, mode, stepIndex])

  useEffect(() => {
    if (mode !== 'intro' || returnFocusRef.current) return
    const activeElement = document.activeElement
    if (
      activeElement instanceof HTMLElement &&
      activeElement !== document.body &&
      activeElement !== document.documentElement
    ) {
      returnFocusRef.current = activeElement
    }
  }, [mode])

  useEffect(() => {
    if (mode === 'idle') return
    const frame = window.requestAnimationFrame(() => titleRef.current?.focus())
    return () => window.cancelAnimationFrame(frame)
  }, [mode, stepIndex])

  useEffect(() => {
    if (mode === 'idle') return
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault()
        closeWalkthrough('skipped')
        return
      }
      if (event.key !== 'Tab' || !dialogRef.current) return
      const elements = focusableElements(dialogRef.current)
      if (!elements.length) {
        event.preventDefault()
        titleRef.current?.focus()
        return
      }
      const first = elements[0]
      const last = elements[elements.length - 1]
      const active = document.activeElement
      if (event.shiftKey && (active === first || !dialogRef.current.contains(active))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && (active === last || !dialogRef.current.contains(active))) {
        event.preventDefault()
        first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [closeWalkthrough, mode])

  const portal =
    mode !== 'idle' &&
    typeof document !== 'undefined' &&
    createPortal(
      mode === 'intro' ? (
        <div className="fixed inset-0 z-[300] flex items-center justify-center bg-mat/85 px-4 backdrop-blur-sm">
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="regression-walkthrough-intro-title"
            aria-describedby="regression-walkthrough-intro-description"
            className="relative w-full max-w-lg overflow-hidden border border-electric/40 bg-panel shadow-[0_24px_80px_-24px_rgba(74,158,245,0.75)]"
          >
            <span className="absolute left-0 top-0 h-8 w-px bg-electric" aria-hidden />
            <span className="absolute left-0 top-0 h-px w-20 bg-electric" aria-hidden />
            <div className="border-b border-electric/20 bg-electric/5 px-5 py-3">
              <p className="font-mono text-[9px] uppercase tracking-[0.28em] text-electric/70">
                Regression Lab // guided analysis
              </p>
            </div>
            <div className="px-5 py-6 sm:px-7">
              <h2
                ref={titleRef}
                id="regression-walkthrough-intro-title"
                tabIndex={-1}
                className="text-xl font-bold tracking-tight text-ink outline-none sm:text-2xl"
              >
                Learn the workflow in eight short steps
              </h2>
              <p
                id="regression-walkthrough-intro-description"
                className="mt-3 max-w-md text-[12px] leading-relaxed text-ink-dim"
              >
                Follow the real controls from cohort selection to responsible result
                interpretation. The walkthrough will not change your current model.
              </p>
              <div className="mt-6 grid grid-cols-8 gap-1" aria-hidden>
                {REGRESSION_LAB_WALKTHROUGH_STEPS.map(step => (
                  <span key={step.id} className="h-1 bg-electric/45" />
                ))}
              </div>
              <div className="mt-7 flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => openTour()}
                  className="border border-electric bg-electric/15 px-4 py-3 text-[11px] font-bold uppercase tracking-[0.16em] text-electric transition-colors hover:bg-electric/30 hover:text-ink motion-reduce:transition-none"
                >
                  Start walkthrough
                </button>
                <button
                  type="button"
                  onClick={() => closeWalkthrough('skipped')}
                  className="border border-control-border px-4 py-3 text-[11px] uppercase tracking-[0.16em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover motion-reduce:transition-none"
                >
                  Skip
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="fixed inset-0 z-[300] bg-mat/60 backdrop-blur-[1px]">
          {anchorAvailable && anchorRect ? (
            <div
              aria-hidden
              className="pointer-events-none fixed border border-electric bg-electric/5 shadow-[0_0_0_3px_rgba(74,158,245,0.18),0_0_38px_rgba(74,158,245,0.45)]"
              style={{
                left: anchorRect.left - 5,
                top: anchorRect.top - 5,
                width: anchorRect.width + 10,
                height: anchorRect.height + 10,
              }}
            />
          ) : null}
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="regression-walkthrough-step-title"
            aria-describedby={cn(
              'regression-walkthrough-step-description',
              anchorStatus === 'unavailable' && 'regression-walkthrough-unavailable',
            )}
            className="fixed max-h-[calc(100svh-24px)] overflow-y-auto border border-electric/45 bg-panel shadow-[0_24px_80px_-24px_rgba(74,158,245,0.85)]"
            style={calloutPosition(anchorRect, calloutSize, viewport)}
          >
            <div className="sticky top-0 border-b border-electric/20 bg-panel/95 px-4 py-3 backdrop-blur-md">
              <div className="flex items-center justify-between gap-3">
                <p
                  role="status"
                  aria-live="polite"
                  aria-atomic="true"
                  className="font-mono text-[9px] uppercase tracking-[0.24em] text-electric"
                >
                  Step {stepIndex + 1} of {REGRESSION_LAB_WALKTHROUGH_STEPS.length}
                </p>
                <button
                  type="button"
                  onClick={() => closeWalkthrough('skipped')}
                  className="text-[9px] uppercase tracking-[0.18em] text-control-fg transition-colors hover:text-ink motion-reduce:transition-none"
                >
                  Skip
                </button>
              </div>
              <div className="mt-2 grid grid-cols-8 gap-1" aria-hidden>
                {REGRESSION_LAB_WALKTHROUGH_STEPS.map((step, index) => (
                  <span
                    key={step.id}
                    className={cn(
                      'h-1',
                      index <= stepIndex ? 'bg-electric' : 'bg-line-bright',
                    )}
                  />
                ))}
              </div>
            </div>
            <div className="px-4 py-4">
              <h2
                ref={titleRef}
                id="regression-walkthrough-step-title"
                tabIndex={-1}
                className="text-lg font-bold tracking-tight text-ink outline-none"
              >
                {activeStep.title}
              </h2>
              <p
                id="regression-walkthrough-step-description"
                className="mt-2 text-[11px] leading-relaxed text-ink-dim"
              >
                {activeStep.body}
              </p>
              {anchorStatus === 'unavailable' ? (
                <p
                  id="regression-walkthrough-unavailable"
                  className="mt-3 border-l-2 border-gold bg-gold/10 px-3 py-2 text-[10px] leading-relaxed text-amber-100"
                >
                  {activeStep.unavailable}
                </p>
              ) : null}
              <div className="mt-5 flex items-center justify-between gap-2 border-t border-electric/15 pt-3">
                <button
                  type="button"
                  disabled={stepIndex === 0}
                  onClick={() => goToStep(stepIndex - 1)}
                  className="border border-control-border px-3 py-2 text-[10px] uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-ink disabled:cursor-not-allowed disabled:opacity-35 motion-reduce:transition-none"
                >
                  Back
                </button>
                {isLastStep ? (
                  <button
                    type="button"
                    onClick={() => closeWalkthrough('completed')}
                    className="border border-electric bg-electric/15 px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-electric transition-colors hover:bg-electric/30 hover:text-ink motion-reduce:transition-none"
                  >
                    Finish
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => goToStep(stepIndex + 1)}
                    className="border border-electric bg-electric/15 px-4 py-2 text-[10px] font-bold uppercase tracking-[0.15em] text-electric transition-colors hover:bg-electric/30 hover:text-ink motion-reduce:transition-none"
                  >
                    Next
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      ),
      document.body,
    )

  return (
    <>
      <button
        ref={launcherRef}
        type="button"
        onClick={event => openTour(event.currentTarget)}
        className="inline-flex shrink-0 items-center gap-1.5 border border-electric/25 px-2 py-1 text-[9px] uppercase tracking-[0.16em] text-electric/75 transition-colors hover:border-electric hover:bg-electric/10 hover:text-electric motion-reduce:transition-none"
        aria-label="Open Regression Lab walkthrough"
      >
        <CircleHelp className="size-3.5" aria-hidden />
        <span className="hidden sm:inline">Help / Walkthrough</span>
        <span className="sm:hidden">Help</span>
      </button>
      {portal}
    </>
  )
}
