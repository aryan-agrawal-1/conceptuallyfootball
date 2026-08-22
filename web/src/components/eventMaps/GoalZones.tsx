import type { ReactNode } from 'react'
import type { ShotZoneGrid, ShotZoneVariant } from '../../types/eventMaps'
import { GOAL_CROSSBAR_Z, GOAL_Z_LOW_MAX } from '../../lib/eventMaps/goalMouth'

export type GoalZoneMode = 'shooter' | 'keeper'

function rateLabel(rate: number | null) {
  return rate == null ? '—' : `${Math.round(rate * 100)}%`
}

export function GoalZoneTotals({ variant, mode }: { variant: ShotZoneVariant; mode: GoalZoneMode }) {
  const totals = variant.totals
  if (mode === 'keeper') {
    return (
      <dl className="grid grid-cols-4 gap-px bg-line-bright" aria-label="Goalkeeper shot-facing totals">
        <Total label="Faced" value={totals.shots_faced ?? 0} />
        <Total label="Saves" value={totals.saves ?? 0} />
        <Total label="Conceded" value={totals.goals_conceded ?? 0} />
        <Total label="Save %">{rateLabel(totals.save_rate ?? null)}</Total>
      </dl>
    )
  }
  return (
    <dl className="grid grid-cols-3 gap-px bg-line-bright sm:grid-cols-6" aria-label="Shooting totals">
      <Total label="Shots" value={totals.shots ?? 0} />
      <Total label="Goals" value={totals.goals ?? 0} />
      <Total label="Conv %">{rateLabel(totals.conversion ?? null)}</Total>
      <Total label="On target %">
        {rateLabel(totals.shots ? (totals.on_target ?? 0) / totals.shots : null)}
      </Total>
      <Total label="Blocked" value={totals.blocked ?? 0} />
      <Total label="Woodwork" value={totals.woodwork ?? 0} />
    </dl>
  )
}

function Total({ label, value, children }: {
  label: string
  value?: number
  children?: ReactNode
}) {
  return (
    <div className="bg-panel px-2 py-2 text-center">
      <dt className="text-[7.5px] font-bold uppercase tracking-[0.14em] text-ink-dim">{label}</dt>
      <dd className="mt-0.5 font-mono text-[13px] tabular-nums text-ink">
        {children ?? (value ?? 0).toLocaleString()}
      </dd>
    </div>
  )
}

// Goal-frame geometry in viewBox units (7.32m x 2.44m proportions, stretched
// vertically so cell labels stay readable).
const FRAME_LEFT = 46
const FRAME_RIGHT = 854
const FRAME_CROSSBAR = 56
const FRAME_GROUND = 372

export function GoalZoneGridView({ grid, variant, mode }: {
  grid: ShotZoneGrid
  variant: ShotZoneVariant
  mode: GoalZoneMode
}) {
  const maxShots = Math.max(1, ...variant.cells.map(cell => cell.shots))
  const innerWidth = FRAME_RIGHT - FRAME_LEFT
  const innerHeight = FRAME_GROUND - FRAME_CROSSBAR
  // The low band is the bottom half of the goal height (see GOAL_CROSSBAR_Z).
  const lowFraction = GOAL_Z_LOW_MAX / GOAL_CROSSBAR_Z
  const lowHeight = innerHeight * lowFraction
  const highHeight = innerHeight - lowHeight
  const base = mode === 'keeper' ? '74, 158, 245' : '31, 209, 124'

  const cellGeometry = (columnIndex: number, rowIndex: number) => {
    // Columns are indexed by ascending pitch y (right-to-left from the
    // shooter's view); mirror so the shooter's left renders on the left.
    const displayColumn = grid.columns - 1 - columnIndex
    const x = FRAME_LEFT + (displayColumn / grid.columns) * innerWidth
    const width = innerWidth / grid.columns
    const isHighRow = rowIndex === 1
    const height = isHighRow ? highHeight : lowHeight
    const y = isHighRow ? FRAME_CROSSBAR : FRAME_GROUND - lowHeight
    return { x, y, width, height }
  }

  return (
    <div className="w-full space-y-2" role="table" aria-label={`Goal-mouth zones, ${mode} view`}>
      <div className="flex items-center justify-between px-1 text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim">
        <span>Shooter&rsquo;s left</span>
        <span aria-hidden>· Goal mouth ·</span>
        <span>Shooter&rsquo;s right</span>
      </div>
      <svg
        viewBox={`0 0 900 ${FRAME_GROUND + 28}`}
        className="w-full"
        role="img"
        aria-label={`${mode === 'keeper' ? 'Save rates' : 'Conversion rates'} by goal-mouth zone`}
      >
        {/* net depth hint */}
        <g stroke="rgba(138, 149, 184, 0.16)" strokeWidth={1}>
          {Array.from({ length: 13 }, (_, index) => {
            const x = FRAME_LEFT + (index / 12) * innerWidth
            return <line key={index} x1={x} y1={FRAME_CROSSBAR} x2={x - 18} y2={FRAME_GROUND + 14} />
          })}
          <line x1={FRAME_LEFT} y1={FRAME_CROSSBAR} x2={FRAME_LEFT - 18} y2={FRAME_GROUND + 14} strokeOpacity={0.6} />
          <line x1={FRAME_RIGHT} y1={FRAME_CROSSBAR} x2={FRAME_RIGHT - 18} y2={FRAME_GROUND + 14} strokeOpacity={0.6} />
          <line x1={FRAME_LEFT - 18} y1={FRAME_GROUND + 14} x2={FRAME_RIGHT - 18} y2={FRAME_GROUND + 14} strokeOpacity={0.6} />
        </g>

        {/* zone cells */}
        {variant.cells.map(cell => {
          if (cell.column >= grid.columns || cell.row >= grid.rows) return null
          const geometry = cellGeometry(cell.column, cell.row)
          const intensity = Math.sqrt(cell.shots / maxShots)
          return (
            <g key={`${cell.column}-${cell.row}`}>
              <rect
                x={geometry.x}
                y={geometry.y}
                width={geometry.width}
                height={geometry.height}
                fill={`rgba(${base}, ${0.05 + intensity * 0.38})`}
                stroke="rgba(255,255,255,0.09)"
                strokeWidth={1}
              />
              <text
                x={geometry.x + geometry.width / 2}
                y={geometry.y + geometry.height / 2 - 8}
                textAnchor="middle"
                className="fill-ink font-mono text-[30px] font-bold"
              >
                {cell.shots}
              </text>
              <text
                x={geometry.x + geometry.width / 2}
                y={geometry.y + geometry.height / 2 + 20}
                textAnchor="middle"
                className="fill-ink-dim font-mono text-[17px]"
              >
                {rateLabel(cell.rate)}
              </text>
            </g>
          )
        })}

        {/* frame drawn above cells so posts and crossbar read as woodwork */}
        <g stroke="#E4EAF8" strokeWidth={9} strokeLinecap="square" fill="none">
          <line x1={FRAME_LEFT} y1={FRAME_CROSSBAR} x2={FRAME_LEFT} y2={FRAME_GROUND} />
          <line x1={FRAME_RIGHT} y1={FRAME_CROSSBAR} x2={FRAME_RIGHT} y2={FRAME_GROUND} />
          <line x1={FRAME_LEFT} y1={FRAME_CROSSBAR} x2={FRAME_RIGHT} y2={FRAME_CROSSBAR} />
        </g>
        {/* ground line */}
        <line
          x1={FRAME_LEFT - 30}
          y1={FRAME_GROUND}
          x2={FRAME_RIGHT + 30}
          y2={FRAME_GROUND}
          stroke="rgba(228, 234, 248, 0.35)"
          strokeWidth={3}
        />
        <text
          x={450}
          y={FRAME_GROUND + 22}
          textAnchor="middle"
          className="fill-ink-muted text-[12px] font-bold uppercase tracking-[0.14em]"
        >
          {mode === 'keeper' ? 'On-target shots faced · save rate' : 'On-target shots · conversion'}
        </text>
      </svg>
    </div>
  )
}
