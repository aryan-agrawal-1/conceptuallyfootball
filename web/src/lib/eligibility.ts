export function percentileIneligibilityMessage(
  reason: string | null,
  minimumEligibleMinutes?: number,
): string {
  const threshold = minimumEligibleMinutes
    ? `${minimumEligibleMinutes.toLocaleString()} minutes`
    : 'the competition minutes threshold'

  switch (reason) {
    case 'below_minutes_threshold':
    case null:
    case '':
      return `This player is below ${threshold} for positional percentiles. Raw values are still shown, but percentile ranks and heatmap colours are withheld until the sample is large enough.`
    case 'unknown_position_group':
      return 'This player does not have a reliable position group for percentile comparison. Raw values are still shown without positional percentile ranks.'
    default:
      return reason
  }
}
