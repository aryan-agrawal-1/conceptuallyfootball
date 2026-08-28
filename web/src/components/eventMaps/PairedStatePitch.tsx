import type { ActionGridCell, PitchCoordinate } from '../../types/eventMaps'
import { statePresentation } from '../../lib/eventMaps/statePresentation'
import { PortraitPitch } from './PortraitPitch'

export type PairedPitchCohort = {
  state: string
  label: string
  cells: ActionGridCell[]
  average: (PitchCoordinate & { sampleSize?: number }) | null
  exposureMinutes: number
  matchCount: number
}

export function PairedStatePitch({ selected, comparison, unit = 'share of located actions', ariaLabel }: {
  selected: PairedPitchCohort
  comparison: PairedPitchCohort
  unit?: string
  ariaLabel: string
}) {
  const domain = Math.max(0, ...selected.cells.map(cell => cell.share), ...comparison.cells.map(cell => cell.share))
  const selectedStyle = statePresentation(selected.state)
  const comparisonStyle = statePresentation(comparison.state)
  const movement = selected.average && comparison.average ? {
    x: selected.average.x - comparison.average.x,
    y: selected.average.y - comparison.average.y,
  } : null
  const marker = (cohort: PairedPitchCohort, color: string) => cohort.average ? [{
    id: `${cohort.state}-average`,
    coordinate: cohort.average,
    kind: 'jersey' as const,
    ariaLabel: `${cohort.label} average position from ${cohort.average.sampleSize ?? 'available'} located actions`,
    label: 'Average',
    color,
  }] : []

  return (
    <figure aria-label={ariaLabel} className="space-y-3">
      <div className="grid gap-3 md:grid-cols-2">
        {[
          { cohort: selected, style: selectedStyle },
          { cohort: comparison, style: comparisonStyle },
        ].map(({ cohort, style }) => <section key={`${cohort.state}-${cohort.label}`} className="border border-line-bright bg-raised/25 p-2" style={{ borderTopColor: style.color }}>
          <div className="mb-2 flex items-center justify-between gap-2 text-[9px]">
            <strong className="uppercase tracking-[0.12em]" style={{ color: style.color }}>{cohort.label}</strong>
            <span className="text-ink-muted">{cohort.matchCount} matches · {cohort.exposureMinutes.toFixed(0)} min</span>
          </div>
          <PortraitPitch densityCells={cohort.cells} densityStyle="smooth" markers={marker(cohort, style.color)} layerOptions={{ densityColor: '#4A9EF5', densityDomainMax: domain }} ariaLabel={`${cohort.label} density map. ${unit}.`} />
        </section>)}
      </div>
      {selected.average && comparison.average && movement ? <div className="border border-line-bright bg-raised/20 px-3 py-2">
        <p className="text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim">Average-position movement</p>
        <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">
          In <span style={{ color: selectedStyle.color }}>{selected.label}</span>, the average position was <span className="font-mono text-ink">{Math.abs(movement.x * 1.05).toFixed(1)} m</span> {movement.x >= 0 ? 'further forward' : 'deeper'} and <span className="font-mono text-ink">{Math.abs(movement.y * 0.68).toFixed(1)} m</span> {movement.y >= 0 ? 'toward the lower touchline' : 'toward the upper touchline'} than in <span style={{ color: comparisonStyle.color }}>{comparison.label}</span>.
        </p>
        <p className="mt-1 text-[8px] text-ink-muted">Estimated from a 105 × 68 metre pitch · attacking left to right</p>
      </div> : null}
      <figcaption className="text-[9px] leading-relaxed text-ink-muted">Both panels use the same blue density scale ({unit}). State colour identifies the average-position marker; labels provide a non-colour cue.</figcaption>
    </figure>
  )
}
