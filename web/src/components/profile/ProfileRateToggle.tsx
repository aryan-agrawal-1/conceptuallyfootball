import { cn } from '../../lib/utils'
import type { ProfileRateMode } from '../../lib/profileMetrics'

interface ProfileRateToggleProps {
  value: ProfileRateMode
  onChange: (mode: ProfileRateMode) => void
  per90Label?: string
  fullLabel?: string
  ariaLabel?: string
}

export function ProfileRateToggle({
  value,
  onChange,
  per90Label = 'Per 90',
  fullLabel = 'Season',
  ariaLabel = 'Per 90 or season totals',
}: ProfileRateToggleProps) {
  return (
    <div
      className="relative flex items-center border border-electric/30 bg-mat/60 overflow-hidden shrink-0"
      role="group"
      aria-label={ariaLabel}
    >
      <button
        type="button"
        className={cn(
          'px-3 py-1.5 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors',
          value === 'per90'
            ? 'bg-electric/15 text-electric shadow-[inset_0_0_12px_-4px_rgba(74,158,245,0.6)]'
            : 'text-ink-muted hover:text-electric/80',
        )}
        onClick={() => onChange('per90')}
      >
        {per90Label}
      </button>
      <span className="w-px h-full min-h-[30px] bg-electric/25" />
      <button
        type="button"
        className={cn(
          'px-3 py-1.5 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors',
          value === 'full'
            ? 'bg-electric/15 text-electric shadow-[inset_0_0_12px_-4px_rgba(74,158,245,0.6)]'
            : 'text-ink-muted hover:text-electric/80',
        )}
        onClick={() => onChange('full')}
      >
        {fullLabel}
      </button>
    </div>
  )
}
