import { useMemo, useState } from 'react'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import type {
  TeamStyleAxis,
  TeamStyleAxisCategory,
  TeamStyleAxisDefinition,
  TeamStyleCohort,
  TeamStyleDistribution,
  TeamStyleGameState,
  TeamStyleShapePayload,
  TeamStyleSignedShift,
} from '../../types/teamStyleShape'
import { radarLabelLines } from '../../lib/profileMetrics'
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
const REFERENCE = '#7E8FB8'

const STATE_CONFIG: Array<{
  key: TeamStyleGameState
  label: string
  color: string
  shape: 'circle' | 'diamond' | 'square'
}> = [
  { key: 'winning', label: 'Winning', color: POSITIVE, shape: 'circle' },
  { key: 'drawing', label: 'Drawing', color: '#E6B85C', shape: 'diamond' },
  { key: 'losing', label: 'Losing', color: NEGATIVE, shape: 'square' },
]

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
  const activeKeys = new Set(active)
  return CATEGORY_ORDER.map(category => ({
    category,
    definitions: definitions.filter(definition => definition.category === category && activeKeys.has(definition.key)),
  })).filter(group => group.definitions.length)
}

function defaultAxisSelection(definitions: TeamStyleAxisDefinition[]) {
  const categoryCounts = new Map<TeamStyleAxisCategory, number>()
  return definitions.reduce<string[]>((keys, definition) => {
    const count = categoryCounts.get(definition.category) ?? 0
    if (count < 2) keys.push(definition.key)
    categoryCounts.set(definition.category, count + 1)
    return keys
  }, [])
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

function SvgLabel({
  x,
  y,
  lines,
  fill = '#8A95B8',
  anchor = 'start',
  fontSize = 9,
}: {
  x: number
  y: number
  lines: string[]
  fill?: string
  anchor?: 'start' | 'middle' | 'end'
  fontSize?: number
}) {
  const offset = lines.length > 1 ? (lines.length - 1) * -0.58 : 0
  return (
    <text x={x} y={y} textAnchor={anchor} fill={fill} fontSize={fontSize} fontWeight="600" letterSpacing="0.35">
      {lines.map((line, index) => (
        <tspan key={`${line}-${index}`} x={x} dy={index === 0 ? `${offset}em` : '1.16em'}>{line}</tspan>
      ))}
    </text>
  )
}

function RadialLegend({ comparison }: { comparison: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-ink-dim" aria-label="Style chart legend">
      {comparison ? <>
        <span className="inline-flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ backgroundColor: '#4A9EF5' }} aria-hidden /> Selected</span>
        <span className="inline-flex items-center gap-1.5"><span className="size-2 rotate-45" style={{ backgroundColor: '#E6B85C' }} aria-hidden /> Comparison</span>
      </> : STATE_CONFIG.map(state => (
        <span key={state.key} className="inline-flex items-center gap-1.5">
          <span className={`inline-block size-2 ${state.shape === 'circle' ? 'rounded-full' : state.shape === 'square' ? 'rounded-[1px]' : 'rotate-45'}`} style={{ backgroundColor: state.color }} aria-hidden />
          {state.label}
        </span>
      ))}
      <span className="inline-flex items-center gap-1.5"><span className="inline-block size-2 rotate-45 border border-dashed border-[#7E8FB8]" aria-hidden /> All-state reference</span>
    </div>
  )
}

function ProfileLegend() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[10px] text-ink-dim" aria-label="Style profile legend">
      <span className="inline-flex items-center gap-1.5"><span className="inline-block size-2 rounded-full bg-[#4A9EF5]" aria-hidden /> Selected profile</span>
      <span className="inline-flex items-center gap-1.5"><span className="inline-block size-2 rotate-45 border border-[#7E8FB8]" aria-hidden /> All-state reference</span>
    </div>
  )
}

function polygonForAxes(
  axes: TeamStyleAxis[],
  radius: number,
  center: number,
  percentileForAxis: (axis: TeamStyleAxis) => number | null,
) {
  const count = Math.max(axes.length, 1)
  return axes.map((axis, index) => {
    const percentileValue = percentileForAxis(axis)
    const percentile = percentileValue == null ? 0 : Math.max(0, Math.min(100, percentileValue))
    const angle = -Math.PI / 2 + index * ((Math.PI * 2) / count)
    const distance = radius * (0.18 + (percentile / 100) * 0.82)
    return `${center + Math.cos(angle) * distance},${center + Math.sin(angle) * distance}`
  }).join(' ')
}

function PrevalenceRadial({ axes, overallAxes }: { axes: TeamStyleAxis[]; overallAxes: Record<string, TeamStyleAxis> }) {
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
  const polygon = polygonForAxes(axes, radius, center, axis => axis.percentile)

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
            <SvgLabel x={label.x} y={label.y} lines={radarLabelLines(axis.label)} anchor={anchor} />
          </g>
        })}
        <polygon points={polygon} fill="rgba(74,158,245,0.20)" stroke="#4A9EF5" strokeWidth="2" />
        {axes.map((axis, index) => {
          const percentile = axis.percentile == null ? 0 : Math.max(0, Math.min(100, axis.percentile))
          const coordinate = point(index, 0.18 + (percentile / 100) * 0.82)
          return <circle key={axis.key} cx={coordinate.x} cy={coordinate.y} r="4" fill={axis.percentile == null ? ZERO : '#4A9EF5'}><title>{axis.label}: {axis.percentile == null ? 'percentile unavailable' : `P${Math.round(axis.percentile)}`}</title></circle>
        })}
        {axes.map((axis, index) => {
          const overall = overallAxes[axis.key]
          if (!overall || overall.percentile == null) return null
          const coordinate = point(index, 0.18 + (overall.percentile / 100) * 0.82)
          return <g key={`overall-${axis.key}`} role="img" aria-label={`${axis.label} all-state reference P${Math.round(overall.percentile)}`}>
            <title>{`${axis.label}: all-state reference P${Math.round(overall.percentile)}`}</title>
            <StateMarker x={coordinate.x} y={coordinate.y} color={REFERENCE} shape="diamond" size={4} opacity={0.8} />
          </g>
        })}
      </svg>
      <ProfileLegend />
      <p className="text-center text-[9px] text-ink-muted">Distance from centre = same competition-season percentile · prevalence, not quality</p>
    </div>
  )
}

type ChartSeries = {
  key: string
  label: string
  color: string
  shape: 'circle' | 'diamond' | 'square'
  cohort: TeamStyleCohort
}

function normalizedPosition(
  value: number | null,
  distribution: TeamStyleDistribution | undefined,
) {
  const p10 = distribution?.distribution.p10
  const p90 = distribution?.distribution.p90
  if (value == null || p10 == null || p90 == null || p90 <= p10) return null
  return {
    position: Math.max(0, Math.min(100, ((value - p10) / (p90 - p10)) * 100)),
    direction: value < p10 ? 'low' as const : value > p90 ? 'high' as const : null,
  }
}

function StateMarker({
  x,
  y,
  color,
  shape,
  hollow = false,
  opacity = 1,
  size = 5,
}: {
  x: number
  y: number
  color: string
  shape: 'circle' | 'diamond' | 'square'
  hollow?: boolean
  opacity?: number
  size?: number
}) {
  const fill = hollow ? '#101320' : color
  if (shape === 'circle') return <circle cx={x} cy={y} r={size} fill={fill} stroke={color} strokeWidth={hollow ? 1.5 : 1} opacity={opacity} />
  if (shape === 'square') return <rect x={x - size} y={y - size} width={size * 2} height={size * 2} rx="1" fill={fill} stroke={color} strokeWidth={hollow ? 1.5 : 1} opacity={opacity} />
  return <rect x={x - size * 0.78} y={y - size * 0.78} width={size * 1.56} height={size * 1.56} transform={`rotate(45 ${x} ${y})`} fill={fill} stroke={color} strokeWidth={hollow ? 1.5 : 1} opacity={opacity} />
}

function EdgeIndicator({ x, y, direction, color }: { x: number; y: number; direction: 'low' | 'high'; color: string }) {
  const points = direction === 'low'
    ? `${x + 7},${y} ${x + 1},${y - 4} ${x + 1},${y + 4}`
    : `${x - 7},${y} ${x - 1},${y - 4} ${x - 1},${y + 4}`
  return <path d={`M ${points.split(' ').join(' L ')} Z`} fill={color} opacity="0.85" />
}

function StateComparisonChart({
  payload,
  axes,
}: {
  payload: TeamStyleShapePayload
  axes: TeamStyleAxis[]
}) {
  const comparison = payload.comparison.enabled && payload.baseline != null
  const series: ChartSeries[] = comparison
    ? [
        { key: 'selected', label: 'Selected', color: '#4A9EF5', shape: 'circle', cohort: payload.selected },
        { key: 'comparison', label: 'Comparison', color: '#E6B85C', shape: 'square', cohort: payload.baseline as TeamStyleCohort },
      ]
    : STATE_CONFIG.flatMap(state => {
        const cohort = payload.gameStates?.[state.key]
        return cohort ? [{ key: state.key, label: state.label, color: state.color, shape: state.shape, cohort }] : []
      })
  const width = 960
  const left = 236
  const right = 34
  const plotWidth = width - left - right
  const top = 50
  const rowHeight = 46
  const height = top + Math.max(axes.length, 1) * rowHeight + 30
  const xFor = (position: number) => left + (position / 100) * plotWidth

  if (!series.length) {
    return (
      <div className="border border-dashed border-line-bright bg-raised/30 px-4 py-8 text-center text-[10px] leading-relaxed text-ink-dim">
        State observations are not loaded for this view yet. Select <span className="text-ink">By game state</span> again to request the compact state series.
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="h-auto min-w-[720px] w-full overflow-visible"
          role="img"
          aria-labelledby="team-style-states-title team-style-states-description"
        >
          <title id="team-style-states-title">Team style by game state</title>
          <desc id="team-style-states-description">Each row positions state values against the all-state competition-season tenth to ninetieth percentile range. The all-state reference is a diamond. Sparse observations are hollow and faded.</desc>
          <text x={left} y="16" fill="#8A95B8" fontSize="9" fontWeight="600" letterSpacing="0.35">LOWER IN TYPICAL RANGE</text>
          <text x={left + plotWidth} y="16" textAnchor="end" fill="#8A95B8" fontSize="9" fontWeight="600" letterSpacing="0.35">HIGHER IN TYPICAL RANGE</text>
          {[0, 50, 100].map(position => (
            <g key={position}>
              <line x1={xFor(position)} y1={top - 13} x2={xFor(position)} y2={height - 18} stroke="#252B43" strokeWidth="1" strokeDasharray={position === 50 ? '2 5' : undefined} />
              <text x={xFor(position)} y={height - 4} textAnchor={position === 0 ? 'start' : position === 100 ? 'end' : 'middle'} fill="#65759E" fontSize="8">{position === 0 ? 'P10' : position === 100 ? 'P90' : 'P50'}</text>
            </g>
          ))}
          {axes.map((axis, index) => {
            const y = top + index * rowHeight + 16
            const labelLines = radarLabelLines(axis.label)
            const distribution = payload.distributions.overall[axis.key]
            const overallValue = normalizedPosition(payload.overall.axes[axis.key]?.value ?? null, distribution)
            const points = series.map(item => {
              const stateAxis = item.cohort.axes[axis.key]
              const normalized = normalizedPosition(stateAxis?.value ?? null, distribution)
              const supported = Boolean(normalized && stateAxis?.reliability !== 'sparse' && stateAxis?.reliability !== 'unavailable')
              return { item, stateAxis, normalized, supported }
            })
            const supportedPositions = points.filter(point => point.supported && point.normalized).map(point => point.normalized!.position)
            const min = supportedPositions.length > 1 ? Math.min(...supportedPositions) : null
            const max = supportedPositions.length > 1 ? Math.max(...supportedPositions) : null
            return (
              <g key={axis.key}>
                <SvgLabel x={12} y={y + 3} lines={labelLines} fill="#E4EAF8" fontSize={9} />
                <line x1={left} y1={y} x2={left + plotWidth} y2={y} stroke="#1B2034" strokeWidth="1" />
                {min != null && max != null ? <line x1={xFor(min)} y1={y} x2={xFor(max)} y2={y} stroke="#56617F" strokeWidth="2" strokeLinecap="round" opacity="0.8" /> : null}
                {overallValue ? <g aria-label={`${axis.label} all-state reference`}>
                  <StateMarker x={xFor(overallValue.position)} y={y} color={REFERENCE} shape="diamond" size={4.5} opacity={0.75} />
                  <title>{`${axis.label}: all-state reference ${formatValue(axis, payload.overall.axes[axis.key]?.value ?? null)}`}</title>
                </g> : null}
                {points.map(point => {
                  const stateAxis = point.stateAxis
                  if (!point.normalized || !stateAxis) return null
                  const x = xFor(point.normalized.position)
                  const sparse = stateAxis.reliability === 'sparse' || stateAxis.reliability === 'unavailable'
                  const description = `${point.item.label} · ${axis.label}: ${formatValue(axis, stateAxis.value)} · ${stateAxis.reliability}${point.normalized.direction ? ` · outside ${point.normalized.direction === 'low' ? 'P10' : 'P90'}` : ''}`
                  return (
                    <g key={point.item.key} tabIndex={0} role="img" aria-label={description}>
                      <title>{description}</title>
                      <StateMarker x={x} y={y} color={point.item.color} shape={point.item.shape} hollow={sparse} opacity={sparse ? 0.4 : 1} />
                      {point.normalized.direction ? <EdgeIndicator x={x} y={y} direction={point.normalized.direction} color={point.item.color} /> : null}
                    </g>
                  )
                })}
              </g>
            )
          })}
        </svg>
      </div>
      <RadialLegend comparison={comparison} />
      <p className="text-[9px] leading-relaxed text-ink-muted">Position is a linear location within this metric's all-state P10–P90 range, not a percentile or quality score. The diamond is the all-state reference; sparse observations are shown hollow.</p>
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

const STYLE_METHOD_NOTES = [
  {
    title: 'State exposure',
    description: 'Each cohort is divided by verified seconds spent in its selected game state. A rate uses that exposure as its denominator, so a short state sample is not treated like a full match.',
    formula: 'per90 rate = count × 5400 / verified state exposure seconds',
  },
  {
    title: 'Defensive-action height',
    description: 'This includes every qualified, located defensive action from the focal team, including transition defending. The location is measured from that team’s own goal.',
    formula: 'median(qualified defensive action x / 100)',
  },
  {
    title: 'Settled block height',
    description: 'This describes organised defending only. An opponent possession is settled after its third control action or 10 seconds; the average defensive location in each settled possession is then summarised. Transition defending is excluded.',
    formula: 'median(mean(settled defensive action x) / 100)',
  },
  {
    title: 'Counter starts',
    description: 'A counter starts with a non-restart recovery or control change at or behind x=60. The next 12 seconds are inspected; final-third and shot outcomes require at least 21 metres of forward progress. Provider FastBreak tags remain separate observations.',
    formula: 'counter starts × 5400 / verified state exposure seconds',
  },
]

function MethodDetails({ definitions }: { definitions: TeamStyleAxisDefinition[] }) {
  return (
    <details className="border border-line-bright bg-raised/35 px-3 py-2 text-[10px] leading-relaxed text-ink-dim">
      <summary className="cursor-pointer text-control-fg hover:text-ink">Definitions &amp; calculation</summary>
      <div className="mt-2 space-y-3">
        <p>These are calculation definitions, not live team data. Values describe how often a behaviour appears; they are not quality or outcome grades.</p>
        {definitions.map(definition => {
          return (
            <div key={definition.key} className="border-t border-line pt-2">
              <p className="font-medium text-ink">{definition.label} <span className="font-normal text-ink-muted">· {definition.unit}</span></p>
              <p className="mt-1">{definition.description}</p>
              <p className="mt-1">Calculation: <span className="font-mono text-ink">{definition.formula}</span></p>
              <p className="mt-1">Higher values mean {definition.higherMeans}. Evidence: {definition.evidenceType}; the minimum is {definition.minimumEvidence.events} qualifying observations and {definition.minimumEvidence.exposureSeconds} seconds of verified exposure.</p>
            </div>
          )
        })}
        {STYLE_METHOD_NOTES.map(note => (
          <div key={note.title} className="border-t border-line pt-2">
            <p className="font-medium text-ink">{note.title}</p>
            <p className="mt-1">{note.description}</p>
            <p className="mt-1">Calculation: <span className="font-mono text-ink">{note.formula}</span></p>
          </div>
        ))}
      </div>
    </details>
  )
}

export type TeamStyleShapeView = 'profile' | 'states'

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
  view?: TeamStyleShapeView
  onViewChange?: (view: TeamStyleShapeView) => void
  /** Parent should refetch with include_game_states=1 when this is called. */
  onGameStateViewRequest?: () => void
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
  view: controlledView,
  onViewChange,
  onGameStateViewRequest,
}: TeamStyleShapePanelProps) {
  const defaultAxisKeys = payload ? defaultAxisSelection(payload.axisDefinitions) : []
  const [localAxisSelection, setLocalAxisSelection] = useState<string[]>(() => defaultAxisKeys)
  const localKeys = payload && localAxisSelection.length && localAxisSelection.every(key => payload.axisKeys.includes(key))
    ? localAxisSelection
    : defaultAxisKeys
  const activeAxisKeys = axisSelection ?? localKeys
  const setAxisSelection = (keys: string[]) => {
    if (onAxisSelectionChange) onAxisSelectionChange(keys)
    else setLocalAxisSelection(keys)
  }
  const activeDefinitions = useMemo(() => {
    const activeKeys = new Set(activeAxisKeys)
    return payload?.axisDefinitions.filter(definition => activeKeys.has(definition.key)) ?? []
  }, [activeAxisKeys, payload])
  const activeAxes = useMemo(
    () => activeDefinitions.map(definition => payload?.selected.axes[definition.key]).filter((axis): axis is TeamStyleAxis => axis != null),
    [activeDefinitions, payload],
  )
  const [localView, setLocalView] = useState<TeamStyleShapeView>('profile')

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
  const comparisonView = payload.comparison.enabled && payload.baseline != null
  const requestedView = controlledView ?? localView
  const activeView = comparisonView ? 'states' : requestedView
  const changeView = (nextView: TeamStyleShapeView) => {
    setLocalView(nextView)
    onViewChange?.(nextView)
    if (nextView === 'states' && !payload.gameStates && !comparisonView) onGameStateViewRequest?.()
  }

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
        <section className="border border-line-bright bg-panel p-3" aria-labelledby="style-view-heading">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 id="style-view-heading" className="text-[10px] font-bold uppercase tracking-[0.15em] text-ink">{activeView === 'states' ? 'Style by game state' : 'Style profile'}</h4>
              <p className="mt-1 text-[10px] leading-relaxed text-ink-dim">{payload.canonicalTeamName} · {scopeLabel(payload.selected.scope)}</p>
            </div>
            <div className="inline-flex border border-control-border bg-raised p-0.5" role="tablist" aria-label="Style chart view">
              {([
                ['profile', 'Profile'],
                ['states', 'By game state'],
              ] as const).map(([key, label]) => {
                const selected = activeView === key
                return (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    className={`px-2.5 py-1 text-[9px] font-semibold transition-colors ${selected ? 'bg-control text-control-fg' : 'text-ink-dim hover:text-ink'}`}
                    onClick={() => {
                      changeView(key)
                    }}
                  >{label}</button>
                )
              })}
            </div>
          </div>
          <div className="mt-3">
            {activeView === 'states'
              ? <StateComparisonChart payload={payload} axes={activeAxes} />
              : <PrevalenceRadial axes={activeAxes} overallAxes={payload.overall.axes} />}
          </div>
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
            <MethodDetails definitions={activeDefinitions} />
          </section>
          </div>
        </details>
        {payload.selected.reliability.sparseAxes.length || (payload.baseline?.reliability.sparseAxes.length ?? 0) ? (
          <EventMapNotice kind="sparse" title="Comparison contains sparse axes">
            Raw selected and baseline evidence remains available. State positions are withheld for axes below their family-specific minimum evidence rule.
          </EventMapNotice>
        ) : null}
      </div>
    </EventMapCard>
  )
}
