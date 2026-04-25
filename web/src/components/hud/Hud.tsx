import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

// ─── HUD primitives ──────────────────────────────────────────────────────────
// A small set of building blocks for the "HUD" aesthetic used across the app.
// The goal is a consistent readout-style: electric-tinted borders, small
// L-brackets at corners, uppercase tracking-wide micro-labels, and a soft
// blue glow. Every page that wants the aesthetic pulls from here so the look
// can be tweaked in one place.

// Four small L-brackets that sit flush to a parent's border. The parent must
// be `relative` for these to anchor correctly.
export function HudCornerMarks({
  size = 'size-2',
  className,
}: {
  size?: string
  className?: string
}) {
  const base = cn(
    'absolute border-electric pointer-events-none',
    size,
    className,
  )
  return (
    <>
      <span className={cn(base, '-top-px -left-px border-t border-l')} />
      <span className={cn(base, '-top-px -right-px border-t border-r')} />
      <span className={cn(base, '-bottom-px -left-px border-b border-l')} />
      <span className={cn(base, '-bottom-px -right-px border-b border-r')} />
    </>
  )
}

// The reusable chrome for any HUD panel. Renders:
//   - a subtle electric border + semi-transparent backdrop
//   - four corner L-brackets
//   - optional header/footer slots with a small pulse dot + micro-label cap
// Callers pass sizing/position via `className`.
export function HudFrame({
  children,
  className,
  bodyClassName,
  header,
  footer,
}: {
  children: ReactNode
  className?: string
  /** Applied to the wrapper around `children` (e.g. `min-h-0 flex-1 flex flex-col` for scroll layouts). */
  bodyClassName?: string
  header?: ReactNode
  footer?: ReactNode
}) {
  return (
    <div
      className={cn(
        'relative flex flex-col min-h-0 border border-electric/25 bg-panel/70 backdrop-blur-md shadow-[0_0_40px_-12px_rgba(74,158,245,0.25)]',
        className,
      )}
    >
      <HudCornerMarks />
      {header && (
        <div className="flex shrink-0 items-center gap-2 border-b border-electric/20 bg-electric/5 px-3 py-1.5 min-w-0">
          <span className="size-1 rounded-full bg-electric animate-pulse shrink-0" />
          <div className="min-w-0 flex-1 flex items-center gap-2 text-[10px] uppercase tracking-[0.2em] text-electric">
            {header}
          </div>
        </div>
      )}
      <div className={cn('min-h-0', bodyClassName)}>{children}</div>
      {footer && (
        <div className="border-t border-electric/20 bg-electric/5 px-3 py-1 text-[10px] uppercase tracking-[0.2em] text-electric/80">
          {footer}
        </div>
      )}
    </div>
  )
}

// Tiny horizontal rule with tick marks — the "divider" staple of HUDs.
export function HudDivider({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'flex items-center gap-1 text-electric/40 text-[9px] tracking-widest select-none',
        className,
      )}
    >
      <span className="h-px flex-1 bg-electric/20" />
      <span className="font-mono">////</span>
      <span className="h-px flex-1 bg-electric/20" />
    </div>
  )
}

// Vertical, electric-tinted separator meant for use inside a HUD bar between
// clusters of controls. Kept thin so a row of controls still reads as one
// continuous readout.
export function HudVSep({ className }: { className?: string }) {
  return <span className={cn('w-px h-5 bg-electric/20', className)} />
}

// A HUD-styled pill button. Inactive reads as a quiet outline; active lights
// up with electric fill + corner brackets so the current choice pops. Used
// for filter segments (positions, min-minutes, rate mode, etc.).
export function HudPill({
  active,
  onClick,
  children,
  className,
  title,
  type = 'button',
}: {
  active: boolean
  onClick?: () => void
  children: ReactNode
  className?: string
  title?: string
  type?: 'button' | 'submit'
}) {
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      className={cn(
        'relative px-2.5 py-1 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border',
        active
          ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
          : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
        className,
      )}
    >
      {active && <HudCornerMarks size="size-1" />}
      {children}
    </button>
  )
}

// A block-level HUD button with bigger presence and the full corner-bracket
// treatment from Galaxy's "Open Profile" CTA. Good for the primary action in
// a HUD panel.
export function HudActionButton({
  onClick,
  children,
  className,
  type = 'button',
  disabled = false,
}: {
  onClick?: () => void
  children: ReactNode
  className?: string
  type?: 'button' | 'submit'
  disabled?: boolean
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'group relative px-4 py-3 border border-electric bg-electric/15 hover:bg-electric/30 text-electric hover:text-ink transition-colors',
        'flex items-center justify-center gap-2 font-bold tracking-[0.15em] uppercase text-[12px]',
        'shadow-[0_0_24px_-6px_rgba(74,158,245,0.7)] hover:shadow-[0_0_32px_-6px_rgba(74,158,245,0.9)]',
        disabled && 'opacity-40 pointer-events-none border-electric/20 text-electric/50 shadow-none',
        className,
      )}
    >
      {children}
      <span className="absolute top-0.5 left-0.5 size-1.5 border-t border-l border-electric" />
      <span className="absolute top-0.5 right-0.5 size-1.5 border-t border-r border-electric" />
      <span className="absolute bottom-0.5 left-0.5 size-1.5 border-b border-l border-electric" />
      <span className="absolute bottom-0.5 right-0.5 size-1.5 border-b border-r border-electric" />
    </button>
  )
}

// Inline "pulse-dot + micro-label" readout. Mirrors the look of a HudFrame
// header but flows inline — useful as a section marker inside a toolbar.
export function HudLabel({
  children,
  className,
  active = true,
}: {
  children: ReactNode
  className?: string
  active?: boolean
}) {
  return (
    <span
      className={cn(
        'flex items-center gap-1.5 text-[10px] uppercase tracking-[0.2em]',
        active ? 'text-electric' : 'text-electric/60',
        className,
      )}
    >
      <span
        className={cn(
          'size-1 rounded-full bg-electric',
          active && 'animate-pulse',
        )}
      />
      {children}
    </span>
  )
}
