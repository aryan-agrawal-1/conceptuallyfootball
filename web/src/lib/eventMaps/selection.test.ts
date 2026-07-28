import { describe, expect, it } from 'vitest'
import type { EventPass, EventShot } from '../../types/eventMaps'
import {
  findDirectionalPitchEvent,
  findNearestPitchEvent,
  type SelectablePitchEvent,
} from './selection'

const pass: EventPass = {
  id: 'pass',
  matchRef: 'match',
  minute: 14,
  start: { x: 20, y: 50 },
  end: { x: 80, y: 50 },
  outcome: 'successful',
  length: 60,
  progressive: true,
  finalThirdEntry: true,
  boxEntry: false,
  keyPass: false,
  cross: false,
  longBall: true,
}

const shot: EventShot = {
  id: 'shot',
  matchRef: 'match',
  minute: 44,
  location: { x: 88, y: 30 },
  outcome: 'saved',
  bodyPart: 'right_foot',
  situation: 'open_play',
  bigChance: false,
  assisted: true,
  perspective: 'for',
}

const events: SelectablePitchEvent[] = [
  {
    id: pass.id,
    kind: 'pass',
    start: pass.start,
    end: pass.end,
    ariaLabel: 'Pass',
    event: pass,
  },
  {
    id: shot.id,
    kind: 'shot',
    point: shot.location,
    ariaLabel: 'Shot',
    event: shot,
  },
]

describe('pitch event selection', () => {
  it('selects a pass by distance to its entire segment', () => {
    expect(findNearestPitchEvent(events, { x: 52, y: 51 }, 3)?.id).toBe('pass')
  })

  it('selects point events and respects the interaction threshold', () => {
    expect(findNearestPitchEvent(events, { x: 87, y: 31 }, 3)?.id).toBe('shot')
    expect(findNearestPitchEvent(events, { x: 5, y: 5 }, 3)).toBeNull()
  })

  it('moves in attack-relative and lateral directions for keyboard users', () => {
    expect(findDirectionalPitchEvent(events, 'pass', 'ArrowUp')?.id).toBe('shot')
    expect(findDirectionalPitchEvent(events, 'shot', 'ArrowDown')?.id).toBe('pass')
  })

  it('starts keyboard inspection at the directional edge', () => {
    expect(findDirectionalPitchEvent(events, null, 'ArrowUp')?.id).toBe('pass')
    expect(findDirectionalPitchEvent(events, null, 'ArrowDown')?.id).toBe('shot')
  })
})
