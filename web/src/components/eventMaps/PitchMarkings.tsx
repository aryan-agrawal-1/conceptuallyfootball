import { memo } from 'react'
import {
  createPitchTransform,
  PITCH_LENGTH_METRES,
  PITCH_VIEWBOX_HEIGHT,
  PITCH_VIEWBOX_WIDTH,
  PITCH_WIDTH_METRES,
} from '../../lib/eventMaps/pitchGeometry'

const transform = createPitchTransform(PITCH_VIEWBOX_WIDTH, PITCH_VIEWBOX_HEIGHT)
const centre = transform.toScreen({ x: 50, y: 50 })
const centreCircleRadius = (9.15 / PITCH_WIDTH_METRES) * PITCH_VIEWBOX_HEIGHT
const penaltySpotDistance = (11 / PITCH_LENGTH_METRES) * 100
const sixYardDepth = (5.5 / PITCH_LENGTH_METRES) * 100
const sixYardWidthInset = ((PITCH_WIDTH_METRES - 18.32) / 2 / PITCH_WIDTH_METRES) * 100
const goalWidthInset = ((PITCH_WIDTH_METRES - 7.32) / 2 / PITCH_WIDTH_METRES) * 100

function areaRectangle(
  nearGoalX: number,
  fieldX: number,
  yMin: number,
  yMax: number,
) {
  const first = transform.toScreen({ x: nearGoalX, y: yMin })
  const second = transform.toScreen({ x: fieldX, y: yMax })

  return {
    x: Math.min(first.x, second.x),
    y: Math.min(first.y, second.y),
    width: Math.abs(second.x - first.x),
    height: Math.abs(second.y - first.y),
  }
}

const topPenaltyArea = areaRectangle(100, 83.5, 21.1, 78.9)
const bottomPenaltyArea = areaRectangle(0, 16.5, 21.1, 78.9)
const topSixYardArea = areaRectangle(100, 100 - sixYardDepth, sixYardWidthInset, 100 - sixYardWidthInset)
const bottomSixYardArea = areaRectangle(0, sixYardDepth, sixYardWidthInset, 100 - sixYardWidthInset)
const topGoal = areaRectangle(100, 99.2, goalWidthInset, 100 - goalWidthInset)
const bottomGoal = areaRectangle(0, 0.8, goalWidthInset, 100 - goalWidthInset)
const topPenaltySpot = transform.toScreen({ x: 100 - penaltySpotDistance, y: 50 })
const bottomPenaltySpot = transform.toScreen({ x: penaltySpotDistance, y: 50 })

export const PitchMarkings = memo(function PitchMarkings() {
  return (
    <g
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      vectorEffect="non-scaling-stroke"
      className="text-ink/34"
      aria-hidden="true"
    >
      <rect x={0.7} y={0.7} width={PITCH_VIEWBOX_WIDTH - 1.4} height={PITCH_VIEWBOX_HEIGHT - 1.4} />
      <line x1={centre.x} y1={0} x2={centre.x} y2={PITCH_VIEWBOX_HEIGHT} />
      <circle cx={centre.x} cy={centre.y} r={centreCircleRadius} />
      <circle cx={centre.x} cy={centre.y} r={2.6} fill="currentColor" stroke="none" />

      <rect {...topPenaltyArea} />
      <rect {...bottomPenaltyArea} />
      <rect {...topSixYardArea} />
      <rect {...bottomSixYardArea} />
      <rect {...topGoal} className="text-electric/55" />
      <rect {...bottomGoal} className="text-electric/55" />
      <circle cx={topPenaltySpot.x} cy={topPenaltySpot.y} r={2.6} fill="currentColor" stroke="none" />
      <circle
        cx={bottomPenaltySpot.x}
        cy={bottomPenaltySpot.y}
        r={2.6}
        fill="currentColor"
        stroke="none"
      />
    </g>
  )
})
