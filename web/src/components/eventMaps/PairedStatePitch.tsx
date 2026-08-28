import { useId } from 'react'
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
  const arrowMarkerId = useId().replaceAll(':', '')
  const domain = Math.max(0, ...selected.cells.map(cell => cell.share), ...comparison.cells.map(cell => cell.share))
  const selectedStyle = statePresentation(selected.state)
  const comparisonStyle = statePresentation(comparison.state)
  const movement = selected.average && comparison.average ? {
    x: selected.average.x - comparison.average.x,
    y: selected.average.y - comparison.average.y,
  } : null
  const pitchPoint = (point: PitchCoordinate) => ({
    x: 5 + point.x * 0.95,
    y: 4 + point.y * 0.6,
  })
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
          <PortraitPitch densityCells={cohort.cells} densityStyle="smooth" markers={marker(cohort, style.color)} layerOptions={{ densityColor: '#8A95B8', densityDomainMax: domain }} ariaLabel={`${cohort.label} density map. ${unit}.`} />
        </section>)}
      </div>
      {selected.average && comparison.average && movement ? <div className="grid items-center gap-3 border border-line-bright bg-raised/20 px-3 py-2 sm:grid-cols-[minmax(220px,0.7fr)_minmax(0,1fr)]">
        <div>
          <p className="text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim">Average-position movement</p>
          <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">
            In <span style={{ color: selectedStyle.color }}>{selected.label}</span>, the average was <span className="font-mono text-ink">{Math.abs(movement.x).toFixed(1)}</span> pitch points {movement.x >= 0 ? 'further forward' : 'deeper'} and <span className="font-mono text-ink">{Math.abs(movement.y).toFixed(1)}</span> points {movement.y >= 0 ? 'toward the lower touchline' : 'toward the upper touchline'} than <span style={{ color: comparisonStyle.color }}>{comparison.label}</span>.
          </p>
          <p className="mt-1 text-[8px] text-ink-muted">Arrow runs from comparison to selected · attacking left to right</p>
        </div>
        <svg viewBox="0 0 105 68" className="h-auto max-h-28 w-full" role="img" aria-label={`${comparison.label} average at ${comparison.average.x.toFixed(1)}, ${comparison.average.y.toFixed(1)} moving to ${selected.label} average at ${selected.average.x.toFixed(1)}, ${selected.average.y.toFixed(1)}`}>
          <defs>
            <marker id={arrowMarkerId} viewBox="0 0 8 8" refX="6" refY="4" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 8 4 L 0 8 Z" fill={selectedStyle.color} />
            </marker>
          </defs>
          <rect x="1" y="1" width="103" height="66" fill="#0A101B" stroke="#3B4564" />
          <line x1="52.5" y1="1" x2="52.5" y2="67" stroke="#3B4564" />
          <circle cx="52.5" cy="34" r="9.15" fill="none" stroke="#3B4564" />
          <rect x="1" y="17" width="16" height="34" fill="none" stroke="#3B4564" />
          <rect x="88" y="17" width="16" height="34" fill="none" stroke="#3B4564" />
          {(() => {
            const from = pitchPoint(comparison.average)
            const to = pitchPoint(selected.average)
            return <>
              <line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={selectedStyle.color} strokeWidth="1.8" markerEnd={`url(#${arrowMarkerId})`} />
              <rect x={from.x - 2.5} y={from.y - 2.5} width="5" height="5" fill={comparisonStyle.color}><title>{comparison.label} average</title></rect>
              <circle cx={to.x} cy={to.y} r="3" fill={selectedStyle.color}><title>{selected.label} average</title></circle>
            </>
          })()}
        </svg>
      </div> : null}
      <figcaption className="text-[9px] leading-relaxed text-ink-muted">Both panels use the same neutral density scale ({unit}). State colour identifies the cohort; marker shape and labels provide a non-colour cue.</figcaption>
    </figure>
  )
}
