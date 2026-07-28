import { describe, expect, it } from 'vitest'
import {
  actionGridCellBounds,
  createPitchTransform,
  fitPortraitPitch,
  PITCH_ASPECT_RATIO,
} from './pitchGeometry'

describe('portrait pitch transforms', () => {
  const transform = createPitchTransform(680, 1050)

  it.each([
    [{ x: 0, y: 0 }, { x: 0, y: 1050 }],
    [{ x: 0, y: 100 }, { x: 680, y: 1050 }],
    [{ x: 100, y: 0 }, { x: 0, y: 0 }],
    [{ x: 100, y: 100 }, { x: 680, y: 0 }],
    [{ x: 50, y: 50 }, { x: 340, y: 525 }],
  ])('maps source point %o to portrait screen point %o', (source, expected) => {
    expect(transform.toScreen(source)).toEqual(expected)
  })

  it('keeps the acting team attacking bottom-to-top', () => {
    const defensiveEvent = transform.toScreen({ x: 15, y: 50 })
    const attackingEvent = transform.toScreen({ x: 90, y: 50 })

    expect(attackingEvent.y).toBeLessThan(defensiveEvent.y)
  })

  it.each([
    [{ x: 83.5, y: 21.1 }, { x: 143.48, y: 173.25 }],
    [{ x: 83.5, y: 78.9 }, { x: 536.52, y: 173.25 }],
    [{ x: 100, y: 21.1 }, { x: 143.48, y: 0 }],
    [{ x: 100, y: 78.9 }, { x: 536.52, y: 0 }],
  ])('aligns opposition penalty-area boundary %o', (source, expected) => {
    const result = transform.toScreen(source)
    expect(result.x).toBeCloseTo(expected.x)
    expect(result.y).toBeCloseTo(expected.y)
  })

  it('round-trips coordinates without changing orientation', () => {
    const source = { x: 71.35, y: 18.6 }
    const result = transform.toPitch(transform.toScreen(source))

    expect(result.x).toBeCloseTo(source.x)
    expect(result.y).toBeCloseTo(source.y)
  })

  it.each([
    [390, 844],
    [1024, 768],
    [680, 1050],
  ])('fits without pitch distortion at %d by %d', (width, height) => {
    const bounds = fitPortraitPitch(width, height)

    expect(bounds.width / bounds.height).toBeCloseTo(PITCH_ASPECT_RATIO)
    expect(bounds.left).toBeGreaterThanOrEqual(0)
    expect(bounds.top).toBeGreaterThanOrEqual(0)
    expect(bounds.right).toBeLessThanOrEqual(width)
    expect(bounds.bottom).toBeLessThanOrEqual(height)
  })

  it('maps all 12x8 grid boundaries to source coordinate ranges', () => {
    const firstCell = actionGridCellBounds(0, 0)
    expect(firstCell.xMin).toBe(0)
    expect(firstCell.xMax).toBeCloseTo(100 / 12)
    expect(firstCell.yMin).toBe(0)
    expect(firstCell.yMax).toBe(12.5)
    expect(actionGridCellBounds(7, 11)).toEqual({
      xMin: (11 / 12) * 100,
      xMax: 100,
      yMin: 87.5,
      yMax: 100,
    })
  })
})
