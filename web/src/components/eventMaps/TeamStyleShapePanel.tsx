import { useMemo, useState } from 'react'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type {
  TeamStyleAxis,
  TeamStyleAxisCategory,
  TeamStyleAxisDefinition,
  TeamStyleShapePayload,
  TeamStyleSignedShift,
} from '../../types/teamStyleShape'
import { EventMapCard, EventMapNotice } from './EventMapUi'

const CATEGORY_ORDER: TeamStyleAxisCategory[] = [
  'build_up',
  'progression_attack',
  'defence',
  'transitions',
]

const CATEGORY_LABELS: Record<TeamStyleAxisCategory, string> = {
  build_up: 'Build-up',
  progression_attack: 'Progression & attack',
  defence: 'Defence',
  transitions: 'Possession-derived transitions',
}

const POSITIVE = '#1FD17C'
const NEGATIVE = '#EF5C66'
const ZERO = '#65759E'

function scopeLabel(scope: TeamStyleShapePayload['selected']['scope'] | null) {
  if (!scope || scope.state === 'all') return 'All states'
  const state = scope.state.replaceAll('_', ' ')
  const qualifiers = [
    scope.goalDifference == null ? null : `GD ${scope.goalDifference > 0 ? '+' : ''}${scope.goalDifference}`,
    scope.phase?.replaceAll('_', ' '),
    scope.drawProvenance && scope.drawProvenance !== 'none' ? scope.drawProvenance : null,
  ].filter((value): value is string => value != null)
  return [state.replace(/^./, value => value.toUpperCase()), ...qualifiers].join(' · ')
}

function formatValue(axis: TeamStyleAxis, value = axis.value) {
  if (value == null) return '—'
  if (axis.unit.startsWith('share')) return `${(value * 100).toFixed(1)}%`
  if (axis.unit === 'pitch x percentage') return `${value.toFixed(1)}%`
  if (axis.unit.includes('metres per second')) return `${value.toFixed(2)} m/s`
  if (axis.unit.includes('metres per pass')) return `${value.toFixed(1)} m`
  return value.toFixed(2)
}

function formatDelta(shift: TeamStyleSignedShift | undefined) {
  if (!shift || shift.rawDelta == null) return '—'
  const sign = shift.rawDelta > 0 ? '+' : ''
  if (shift.unit?.startsWith('share')) return `${sign}${(shift.rawDelta * 100).toFixed(1)} pp`
  if (shift.unit === 'pitch x percentage') return `${sign}${shift.rawDelta.toFixed(1)} pts`
  return `${sign}${shift.rawDelta.toFixed(2)}`
}

function reliabilityLabel(value: TeamStyleAxis['reliability']) {
  return value === 'verified' ? 'Verified' : value === 'partial' ? 'Partial' : value === 'sparse' ? 'Sparse' : 'Unavailable'
}

function categoryAxes(definitions: TeamStyleAxisDefinition[], active: string[]) {
  return CATEGORY_ORDER.map(category => ({
    category,
    definitions: definitions.filter(definition => definition.category === category && active.includes(definition.key)),
  })).filter(group => group.definitions.length)
}

function AxisPicker({
  definitions,
  selected,
  onChange,
}: {
  definitions: TeamStyleAxisDefinition[]
  selected: string[]
  onChange: (keys: string[]) => void
}) {
  const groups = categoryAxes(definitions, definitions.map(definition => definition.key))
  const toggle = (key: string) => {
    if (selected.includes(key)) {
      if (selected.length > 1) onChange(selected.filter(value => value !== key))
      return
    }
    onChange(definitions.map(definition => definition.key).filter(value => selected.includes(value) || value === key))
  }
  return (
    <details className="relative">
      <summary className="event-lens-control flex min-w-48 list-none items-center justify-between gap-3 text-left marker:hidden">
        <span>Axes · {selected.length}/{definitions.length}</span>
        <span aria-hidden className="text-electric">▾</span>
      </summary>
      <div className="absolute right-0 z-30 mt-1 max-h-[min(75svh,32rem)] min-w-64 max-w-[calc(100vw-2rem)] overflow-y-auto border border-control-border bg-overlay p-2 shadow-2xl">
        <p className="px-2 pb-2 text-[10px] leading-relaxed text-ink-dim">Choose the style behaviours to show. At least one axis stays selected.</p>
        {groups.map(group => (
          <fieldset key={group.category} className="border-t border-line-bright py-1">
            <legend className="px-2 pt-1 text-[9px] font-bold uppercase tracking-[0.12em] text-electric">{CATEGORY_LABELS[group.category]}</legend>
            {group.definitions.map(definition => (
              <label key={definition.key} className="flex min-h-9 items-center gap-2 px-2 text-[10px] text-control-fg hover:bg-raised hover:text-ink">
                <input type="checkbox" checked={selected.includes(definition.key)} onChange={() => toggle(definition.key)} />
                <span>{definition.label}</span>
              </label>
            ))}
          </fieldset>
        ))}
      </div>
    </details>
  )
}

function RadialLegend() {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-ink-dim" aria-label="Signed style shift legend">
      <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ backgroundColor: POSITIVE }} aria-hidden /> More prevalent in selected</span>
      <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ backgroundColor: NEGATIVE }} aria-hidden /> Less prevalent in selected</span>
      <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ backgroundColor: ZERO }} aria-hidden /> Unsupported / sparse</span>
    </div>
  )
}

function SignedShiftRadial({
  axes,
  shifts,
}: {
  axes: TeamStyleAxis[]
  shifts: Record<string, TeamStyleSignedShift> | null
}) {
  const center = 200
  const radius = 126
  const count = Math.max(axes.length, 1)
  const angleStep = (Math.PI * 2) / count
  const point = (angle: number, distance: number) => ({
    x: center + Math.cos(angle) * distance,
    y: center + Math.sin(angle) * distance,
  })
  return (
    <div className="w-full max-w-[440px]">
      <svg
        viewBox="0 0 400 400"
        className="h-auto w-full overflow-visible"
        role="img"
        aria-labelledby="team-style-shift-title team-style-shift-description"
      >
        <title id="team-style-shift-title">Signed Team Style State Shift</title>
        <desc id="team-style-shift-description">A diverging radial chart centred at zero. Green spokes indicate more prevalent selected-state behaviour; red spokes indicate less prevalent behaviour. Spoke length is a robust, clipped comparison scale and is not a quality score.</desc>
        {[1 / 3, 2 / 3, 1].map(fraction => (
          <circle key={fraction} cx={center} cy={center} r={radius * fraction} fill="none" stroke="#2A3050" strokeWidth="1" strokeDasharray={fraction === 1 ? undefined : '3 5'} />
        ))}
        <circle cx={center} cy={center} r="4" fill="#E4EAF8" />
        {axes.map((axis, index) => {
          const angle = -Math.PI / 2 + index * angleStep
          const outer = point(angle, radius)
          const shift = shifts?.[axis.key]
          const normalised = shift?.normalisedDelta ?? null
          const length = normalised == null ? 13 : Math.max(9, radius * Math.abs(normalised))
          const end = point(angle, length)
          const labelPoint = point(angle, radius + 24)
          const tone = normalised == null ? ZERO : normalised >= 0 ? POSITIVE : NEGATIVE
          const anchor = Math.abs(Math.cos(angle)) < 0.35 ? 'middle' : Math.cos(angle) > 0 ? 'start' : 'end'
          return (
            <g key={axis.key}>
              <line x1={center} y1={center} x2={outer.x} y2={outer.y} stroke="#1F2438" strokeWidth="1" />
              <line x1={center} y1={center} x2={end.x} y2={end.y} stroke={tone} strokeWidth="13" strokeLinecap="round" strokeDasharray={normalised == null ? '2 4' : undefined} opacity={normalised == null ? 0.65 : 0.92}>
                <title>{`${axis.label}: ${shift ? formatDelta(shift) : 'unavailable'}${normalised == null ? ' · no stable radial shift' : ''}`}</title>
              </line>
              <text x={labelPoint.x} y={labelPoint.y} textAnchor={anchor} dominantBaseline="middle" fill="#8A95B8" fontSize="9" fontWeight="600" letterSpacing="0.4" aria-hidden="true">{axis.label.length > 19 ? `${axis.label.slice(0, 18)}…` : axis.label}</text>
            </g>
          )
        })}
        <text x={center} y={center - 9} textAnchor="middle" fill="#E4EAF8" fontSize="9" fontWeight="700" letterSpacing="1.2">ZERO</text>
        <text x={center} y={center + 12} textAnchor="middle" fill="#8A95B8" fontSize="8" letterSpacing="0.4">STATE SHIFT</text>
      </svg>
    </div>
  )
}

function PrevalenceRadial({ axes }: { axes: TeamStyleAxis[] }) {
  const center = 200
  const radius = 124
  const count = Math.max(axes.length, 1)
  const point = (index: number, fraction: number) => {
    const angle = -Math.PI / 2 + index * ((Math.PI * 2) / count)
    return {
      x: center + Math.cos(angle) * radius * fraction,
      y: center + Math.sin(angle) * radius * fraction,
      angle,
    }
  }
  const polygon = axes.map((axis, index) => {
    const percentile = axis.percentile == null ? 0 : Math.max(0, Math.min(100, axis.percentile))
    const coordinate = point(index, 0.18 + (percentile / 100) * 0.82)
    return `${coordinate.x},${coordinate.y}`
  }).join(' ')

  return (
    <div className="mx-auto w-full max-w-[520px]">
      <svg viewBox="0 0 400 400" className="h-auto w-full overflow-visible" role="img" aria-labelledby="team-style-prevalence-title team-style-prevalence-description">
        <title id="team-style-prevalence-title">Team style prevalence profile</title>
        <desc id="team-style-prevalence-description">A radial profile showing how prevalent each selected behaviour is relative to teams in the same competition and season. Distance from the centre represents percentile, not quality.</desc>
        {[0.25, 0.5, 0.75, 1].map(fraction => (
          <circle key={fraction} cx={center} cy={center} r={radius * fraction} fill="none" stroke="#2A3050" strokeWidth="1" strokeDasharray={fraction === 1 ? undefined : '3 5'} />
        ))}
        {axes.map((axis, index) => {
          const outer = point(index, 1)
          const label = point(index, 1.18)
          const anchor = Math.abs(Math.cos(label.angle)) < 0.35 ? 'middle' : Math.cos(label.angle) > 0 ? 'start' : 'end'
          return <g key={axis.key}>
            <line x1={center} y1={center} x2={outer.x} y2={outer.y} stroke="#1F2438" strokeWidth="1" />
            <text x={label.x} y={label.y} textAnchor={anchor} dominantBaseline="middle" fill="#8A95B8" fontSize="9" fontWeight="600">{axis.label.length > 18 ? `${axis.label.slice(0, 17)}…` : axis.label}</text>
          </g>
        })}
        <polygon points={polygon} fill="rgba(74,158,245,0.20)" stroke="#4A9EF5" strokeWidth="2" />
        {axes.map((axis, index) => {
          const percentile = axis.percentile == null ? 0 : Math.max(0, Math.min(100, axis.percentile))
          const coordinate = point(index, 0.18 + (percentile / 100) * 0.82)
          return <circle key={axis.key} cx={coordinate.x} cy={coordinate.y} r="4" fill={axis.percentile == null ? ZERO : '#4A9EF5'}><title>{axis.label}: {axis.percentile == null ? 'percentile unavailable' : `P${Math.round(axis.percentile)}`}</title></circle>
        })}
        <text x={center} y={center - 7} textAnchor="middle" fill="#E4EAF8" fontSize="10" fontWeight="700">STYLE</text>
        <text x={center} y={center + 10} textAnchor="middle" fill="#8A95B8" fontSize="8">PREVALENCE</text>
      </svg>
      <p className="text-center text-[9px] text-ink-muted">Distance from centre = same competition-season percentile · prevalence, not quality</p>
    </div>
  )
}

function ExposureStrip({ payload }: { payload: TeamStyleShapePayload }) {
  const selected = payload.selected.exposure
  const baseline = payload.baseline?.exposure
  return (
    <dl className="grid border border-line-bright bg-line sm:grid-cols-3">
      {[
        ['Selected exposure', `${selected.minutes.toLocaleString()} min`, `${selected.matchCount} matches · ${selected.episodeCount} episodes`],
        ['Baseline exposure', baseline ? `${baseline.minutes.toLocaleString()} min` : 'Not selected', baseline ? `${baseline.matchCount} matches · ${baseline.episodeCount} episodes` : 'Enable a baseline to show signed shifts'],
        ['Cohort', payload.cohort.percentilesAvailable ? `${payload.cohort.teamCount} teams` : 'Raw only', payload.cohort.percentileNote],
      ].map(([label, value, detail]) => (
        <div key={label} className="bg-panel px-3 py-2.5">
          <dt className="text-[8px] font-bold uppercase tracking-[0.15em] text-ink-dim">{label}</dt>
          <dd className="mt-1 font-mono text-[14px] tabular-nums text-ink">{value}</dd>
          <p className="mt-1 text-[9px] leading-relaxed text-ink-muted">{detail}</p>
        </div>
      ))}
    </dl>
  )
}

function AxisRows({
  payload,
  axes,
  shifts,
}: {
  payload: TeamStyleShapePayload
  axes: TeamStyleAxis[]
  shifts: Record<string, TeamStyleSignedShift> | null
}) {
  return (
    <div className="overflow-x-auto border border-line-bright">
      <table className="w-full min-w-[620px] border-collapse text-left text-[10px]">
        <caption className="sr-only">Team style prevalence values, competition-season percentiles and selected-minus-baseline shifts</caption>
        <thead className="bg-raised text-[8px] font-bold uppercase tracking-[0.13em] text-ink-dim">
          <tr>
            <th scope="col" className="px-3 py-2">Axis</th>
            <th scope="col" className="px-3 py-2">Overall</th>
            <th scope="col" className="px-3 py-2">Selected</th>
            <th scope="col" className="px-3 py-2">Prevalence percentile</th>
            <th scope="col" className="px-3 py-2">Signed shift</th>
            <th scope="col" className="px-3 py-2">Evidence</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {axes.map(axis => {
            const overall = payload.overall.axes[axis.key]
            const shift = shifts?.[axis.key]
            const percentile = payload.selected.axes[axis.key].percentile
            return (
              <tr key={axis.key} className="bg-panel align-top hover:bg-raised/70">
                <th scope="row" className="px-3 py-2 font-medium text-ink">
                  <span className="block">{axis.label}</span>
                  <span className="mt-0.5 block font-normal text-ink-muted">{axis.unit}</span>
                </th>
                <td className="px-3 py-2 font-mono tabular-nums text-ink-dim">{formatValue(overall)}</td>
                <td className="px-3 py-2 font-mono tabular-nums text-ink">{formatValue(axis)}</td>
                <td className="px-3 py-2 font-mono tabular-nums text-electric">{percentile == null ? '—' : `P${Math.round(percentile)}`}<span className="ml-1 font-sans text-[9px] text-ink-muted">{reliabilityLabel(axis.reliability)}</span></td>
                <td className={`px-3 py-2 font-mono tabular-nums ${shift?.rawDelta == null ? 'text-ink-muted' : shift.rawDelta >= 0 ? 'text-mint' : 'text-ember'}`}>{formatDelta(shift)}</td>
                <td className="px-3 py-2 text-ink-dim"><span className="font-mono">{axis.evidence.count.toLocaleString()}</span> · {axis.percentileEligible ? 'eligible' : axis.ineligibilityReason ?? 'unavailable'}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function MethodDetails({
  payload,
  axes,
}: {
  payload: TeamStyleShapePayload
  axes: TeamStyleAxis[]
}) {
  return (
    <details className="border border-line-bright bg-raised/35 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
      <summary className="cursor-pointer text-control-fg hover:text-ink">Definitions, raw evidence &amp; distributions</summary>
      <div className="mt-2 space-y-3">
        <p>Every axis has one formula, unit and minimum-evidence rule. Values and percentiles describe style prevalence, not quality. The outcome layer is intentionally separate.</p>
        {axes.map(axis => {
          const definition = payload.axisDefinitions.find(item => item.key === axis.key)
          const distribution = payload.distributions.selected[axis.key]
          return (
            <div key={axis.key} className="border-t border-line pt-2">
              <p className="font-medium text-ink">{axis.label} <span className="font-normal text-ink-muted">· {axis.unit} · {reliabilityLabel(axis.reliability)}</span></p>
              <p className="mt-1">{definition?.description ?? 'Style prevalence axis.'} Formula: <span className="text-ink">{definition?.formula ?? '—'}</span></p>
              <p className="mt-1">Raw: <span className="font-mono text-ink">{axis.value == null ? '—' : formatValue(axis)}</span> · {axis.evidence.count.toLocaleString()} evidence events · minimum {axis.evidence.minimum.events} events / {axis.evidence.minimum.exposureSeconds}s exposure.</p>
              <p className="mt-1">Competition-season distribution: n={distribution?.sampleSize ?? 0} · p10 {distribution?.distribution.p10 ?? '—'} · p50 {distribution?.distribution.p50 ?? '—'} · p90 {distribution?.distribution.p90 ?? '—'}.</p>
              {Object.keys(axis.raw).length ? <p className="mt-1 break-words font-mono text-[9px] text-ink-muted">{JSON.stringify(axis.raw)}</p> : null}
            </div>
          )
        })}
        {payload.notes.map(note => <p key={note} className="text-ink-muted">{note}</p>)}
      </div>
    </details>
  )
}

export type TeamStyleShapePanelProps = {
  payload?: TeamStyleShapePayload
  loading: boolean
  error?: string
  onRetry: () => void
  exportContext?: EventMapExportContext
  expanded?: boolean
  onExpandedChange?: (expanded: boolean) => void
  axisSelection?: string[]
  onAxisSelectionChange?: (keys: string[]) => void
}

export function TeamStyleShapePanel({
  payload,
  loading,
  error,
  onRetry,
  exportContext,
  expanded = false,
  onExpandedChange = () => undefined,
  axisSelection,
  onAxisSelectionChange,
}: TeamStyleShapePanelProps) {
  const defaultAxisKeys = payload?.axisDefinitions.filter(definition => (
    payload.axisDefinitions.filter(candidate => candidate.category === definition.category).indexOf(definition) < 2
  )).map(definition => definition.key) ?? []
  const [localAxisSelection, setLocalAxisSelection] = useState<string[]>(() => defaultAxisKeys)
  const localKeys = payload && localAxisSelection.length && localAxisSelection.every(key => payload.axisKeys.includes(key))
    ? localAxisSelection
    : defaultAxisKeys
  const activeAxisKeys = axisSelection ?? localKeys
  const setAxisSelection = (keys: string[]) => {
    if (onAxisSelectionChange) onAxisSelectionChange(keys)
    else setLocalAxisSelection(keys)
  }
  const activeDefinitions = useMemo(
    () => payload?.axisDefinitions.filter(definition => activeAxisKeys.includes(definition.key)) ?? [],
    [activeAxisKeys, payload],
  )
  const activeAxes = useMemo(
    () => activeDefinitions.map(definition => payload?.selected.axes[definition.key]).filter((axis): axis is TeamStyleAxis => axis != null),
    [activeDefinitions, payload],
  )

  if (loading) return <EventMapNotice kind="loading" title="Loading team style shape" />
  if (error || !payload) return <EventMapNotice kind="error" title="Team style shape failed to load" onRetry={onRetry}>{error ?? 'The Team Style Shape service returned no data.'}</EventMapNotice>

  const resolvedExportContext = exportContext ?? {
    subjectName: payload.canonicalTeamName,
    subjectType: 'Team' as const,
    competition: payload.competitionCode,
    season: payload.seasonLabel,
    filters: [{ label: 'Game state', value: scopeLabel(payload.selected.scope) }],
  }
  const shifts = payload.comparison.selectedMinusBaseline
  const shiftAxes = activeAxes
  const stableShiftCount = shiftAxes.filter(axis => shifts?.[axis.key]?.eligible).length

  return (
    <EventMapCard
      title="Team Style Shape"
      description="A prevalence profile across passing, progression, defence and possession-derived transitions. Percentiles are not quality grades."
      controls={(
        <AxisPicker definitions={payload.axisDefinitions} selected={activeAxisKeys} onChange={setAxisSelection} />
      )}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      exportContext={{
        ...resolvedExportContext,
        filters: [
          ...resolvedExportContext.filters,
          { label: 'Style axes', value: `${activeAxes.length} selected` },
          { label: 'Percentile cohort', value: payload.cohort.percentilesAvailable ? `${payload.cohort.teamCount} competition-season teams` : 'Raw evidence only' },
        ],
      }}
    >
      <div className="w-full max-w-[1180px] space-y-3" aria-label="Team Style Shape evidence">
        <section className="border border-line-bright bg-panel p-3" aria-labelledby="style-shift-heading">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <h4 id="style-shift-heading" className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">{shifts ? 'Signed State Shift' : 'Style prevalence'}</h4>
                <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">{payload.canonicalTeamName} · {scopeLabel(payload.selected.scope)}</p>
              </div>
              {shifts ? <span className="font-mono text-[9px] text-ink-muted">{stableShiftCount}/{shiftAxes.length} stable</span> : null}
            </div>
            {shifts ? <SignedShiftRadial axes={shiftAxes} shifts={shifts} /> : <PrevalenceRadial axes={activeAxes} />}
            {shifts ? <RadialLegend /> : null}
          </section>

        <details className="group border border-line-bright bg-panel">
          <summary className="cursor-pointer list-none px-3 py-2.5 text-[10px] font-bold uppercase tracking-[0.12em] text-control-fg hover:text-ink">Evidence & methodology <span className="ml-2 font-normal normal-case tracking-normal text-ink-muted">{payload.selected.exposure.matchCount} matches · {payload.cohort.teamCount} team cohort</span></summary>
          <div className="space-y-3 border-t border-line-bright p-3">
            <ExposureStrip payload={payload} />
            <section className="min-w-0 space-y-2" aria-labelledby="style-values-heading">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <div>
                <h4 id="style-values-heading" className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">Prevalence readout</h4>
                <p className="mt-1 text-[10px] text-ink-dim">Overall and selected raw values with a same competition-season cohort rank.</p>
              </div>
              {!payload.cohort.percentilesAvailable ? <span className="text-[10px] text-gold">Percentiles withheld for single-match scope</span> : null}
            </div>
            <AxisRows payload={payload} axes={activeAxes} shifts={shifts} />
            <MethodDetails payload={payload} axes={activeAxes} />
          </section>
          </div>
        </details>
        {payload.selected.reliability.sparseAxes.length || (payload.baseline?.reliability.sparseAxes.length ?? 0) ? (
          <EventMapNotice kind="sparse" title="Comparison contains sparse axes">
            Raw selected and baseline evidence remains available. Percentiles and radial magnitudes are withheld for axes below their family-specific minimum evidence rule.
          </EventMapNotice>
        ) : null}
      </div>
    </EventMapCard>
  )
}
