import type { EventPass, EventShot, PitchCoordinate } from '../../types/eventMaps'

export type SelectablePitchEvent =
  | {
      id: string
      kind: 'pass'
      start: PitchCoordinate
      end: PitchCoordinate
      ariaLabel: string
      event: EventPass
    }
  | {
      id: string
      kind: 'shot'
      point: PitchCoordinate
      ariaLabel: string
      event: EventShot
    }

export type DirectionKey = 'ArrowUp' | 'ArrowDown' | 'ArrowLeft' | 'ArrowRight'

function squaredDistance(first: PitchCoordinate, second: PitchCoordinate) {
  const deltaX = first.x - second.x
  const deltaY = first.y - second.y
  return deltaX * deltaX + deltaY * deltaY
}

function distanceToSegment(point: PitchCoordinate, start: PitchCoordinate, end: PitchCoordinate) {
  const segmentX = end.x - start.x
  const segmentY = end.y - start.y
  const lengthSquared = segmentX * segmentX + segmentY * segmentY

  if (lengthSquared === 0) return Math.sqrt(squaredDistance(point, start))

  const projection = Math.min(
    1,
    Math.max(
      0,
      ((point.x - start.x) * segmentX + (point.y - start.y) * segmentY) / lengthSquared,
    ),
  )

  return Math.sqrt(
    squaredDistance(point, {
      x: start.x + projection * segmentX,
      y: start.y + projection * segmentY,
    }),
  )
}

export function selectableEventAnchor(event: SelectablePitchEvent): PitchCoordinate {
  if (event.kind === 'shot') return event.point

  return {
    x: (event.start.x + event.end.x) / 2,
    y: (event.start.y + event.end.y) / 2,
  }
}

export function findNearestPitchEvent(
  events: SelectablePitchEvent[],
  point: PitchCoordinate,
  maximumDistance = Number.POSITIVE_INFINITY,
) {
  let nearest: SelectablePitchEvent | null = null
  let nearestDistance = maximumDistance

  for (const event of events) {
    const distance =
      event.kind === 'pass'
        ? distanceToSegment(point, event.start, event.end)
        : Math.sqrt(squaredDistance(point, event.point))

    if (distance <= nearestDistance) {
      nearest = event
      nearestDistance = distance
    }
  }

  return nearest
}

function directionVector(key: DirectionKey): PitchCoordinate {
  if (key === 'ArrowUp') return { x: 1, y: 0 }
  if (key === 'ArrowDown') return { x: -1, y: 0 }
  if (key === 'ArrowLeft') return { x: 0, y: -1 }
  return { x: 0, y: 1 }
}

export function findDirectionalPitchEvent(
  events: SelectablePitchEvent[],
  currentId: string | null,
  key: DirectionKey,
) {
  if (events.length === 0) return null

  const current = events.find((event) => event.id === currentId)
  if (!current) {
    if (key === 'ArrowUp') {
      return events.reduce((candidate, event) =>
        selectableEventAnchor(event).x < selectableEventAnchor(candidate).x ? event : candidate,
      )
    }
    if (key === 'ArrowDown') {
      return events.reduce((candidate, event) =>
        selectableEventAnchor(event).x > selectableEventAnchor(candidate).x ? event : candidate,
      )
    }
    if (key === 'ArrowLeft') {
      return events.reduce((candidate, event) =>
        selectableEventAnchor(event).y > selectableEventAnchor(candidate).y ? event : candidate,
      )
    }
    return events.reduce((candidate, event) =>
      selectableEventAnchor(event).y < selectableEventAnchor(candidate).y ? event : candidate,
    )
  }

  const origin = selectableEventAnchor(current)
  const direction = directionVector(key)
  let best: SelectablePitchEvent | null = null
  let bestScore = Number.POSITIVE_INFINITY

  for (const event of events) {
    if (event.id === current.id) continue

    const candidate = selectableEventAnchor(event)
    const deltaX = candidate.x - origin.x
    const deltaY = candidate.y - origin.y
    const forwardDistance = deltaX * direction.x + deltaY * direction.y
    if (forwardDistance <= 0) continue

    const lateralDistance = Math.abs(deltaX * direction.y - deltaY * direction.x)
    const score = forwardDistance + lateralDistance * 2.5

    if (score < bestScore) {
      best = event
      bestScore = score
    }
  }

  return best
}
