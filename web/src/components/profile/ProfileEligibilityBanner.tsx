import { AlertTriangle } from 'lucide-react'
import { HudFrame } from '../hud/Hud'

interface ProfileEligibilityBannerProps {
  reason: string | null
}

function formatReason(reason: string | null): string {
  switch (reason) {
    case 'below_minutes_threshold':
      return 'This player is below the minutes threshold for positional percentiles. Raw values are still shown, but percentile ranks and heatmap colours are withheld until the sample is large enough.'
    case 'unknown_position_group':
      return 'This player does not have a reliable position group for percentile comparison. Raw values are still shown without positional percentile ranks.'
    case null:
    case '':
      return 'This player is below the minutes threshold for positional percentiles. Raw values are still shown, but percentile ranks and heatmap colours are withheld until the sample is large enough.'
    default:
      return reason
  }
}

export function ProfileEligibilityBanner({ reason }: ProfileEligibilityBannerProps) {
  return (
    <HudFrame
      className="w-full border-ember/35 shadow-[0_0_28px_-12px_rgba(239,68,68,0.35)]"
      header={<span className="text-ember">Low sample // Percentiles</span>}
    >
      <div className="flex items-start gap-3 p-4">
        <AlertTriangle size={18} className="text-ember shrink-0 mt-0.5" aria-hidden />
        <p className="text-[12px] text-ink-dim leading-relaxed">
          {formatReason(reason)}
        </p>
      </div>
    </HudFrame>
  )
}
