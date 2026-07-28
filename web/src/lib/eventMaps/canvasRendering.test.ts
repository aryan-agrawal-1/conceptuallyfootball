import { describe, expect, it } from 'vitest'
import {
  eventActionGridFixture,
  eventMapVisualViewportFixtures,
  eventPassFixture,
  teamPassFlowFixture,
} from './fixtures'
import {
  configureHiDPICanvas,
  drawDensePitchLayers,
  type CanvasViewport,
} from './canvasRendering'
import { createPitchTransform } from './pitchGeometry'

function createRecordingContext() {
  const commands: string[] = []
  const context = {
    fillStyle: '',
    globalAlpha: 1,
    lineCap: 'butt',
    lineWidth: 1,
    strokeStyle: '',
    arc: () => commands.push('arc'),
    beginPath: () => commands.push('beginPath'),
    clearRect: () => commands.push('clearRect'),
    fill: () => commands.push('fill'),
    fillRect: () => commands.push('fillRect'),
    lineTo: () => commands.push('lineTo'),
    moveTo: () => commands.push('moveTo'),
    quadraticCurveTo: () => commands.push('quadraticCurveTo'),
    restore: () => commands.push('restore'),
    save: () => commands.push('save'),
    setTransform: (...values: number[]) => commands.push(`setTransform:${values.join(',')}`),
    stroke: () => commands.push('stroke'),
  }

  return { commands, context: context as unknown as CanvasRenderingContext2D }
}

describe('hybrid canvas rendering', () => {
  it('creates a DPR-correct backing store without changing CSS dimensions', () => {
    const { commands, context } = createRecordingContext()
    const canvas = {
      width: 0,
      height: 0,
      style: {},
      getContext: () => context,
    } as unknown as HTMLCanvasElement
    const viewport: CanvasViewport = { width: 340, height: 525, devicePixelRatio: 2 }

    configureHiDPICanvas(canvas, viewport)

    expect(canvas.width).toBe(680)
    expect(canvas.height).toBe(1050)
    expect(canvas.style.width).toBe('340px')
    expect(canvas.style.height).toBe('525px')
    expect(commands).toContain('setTransform:2,0,0,2,0,0')
  })

  it('paints nonblank pass, density, and flow layers', () => {
    const { commands, context } = createRecordingContext()

    drawDensePitchLayers(
      context,
      { width: 680, height: 1050 },
      {
        passes: eventPassFixture,
        densityCells: eventActionGridFixture,
        flows: teamPassFlowFixture,
      },
    )

    expect(commands).toContain('fillRect')
    expect(commands).toContain('quadraticCurveTo')
    expect(commands).toContain('stroke')
    expect(commands).toContain('fill')
    expect(commands.filter((command) => command !== 'clearRect').length).toBeGreaterThan(20)
  })

  it.each([
    [
      eventMapVisualViewportFixtures.mobile.width,
      eventMapVisualViewportFixtures.mobile.height,
      eventMapVisualViewportFixtures.mobile.devicePixelRatio,
    ],
    [
      eventMapVisualViewportFixtures.desktop.width,
      eventMapVisualViewportFixtures.desktop.height,
      eventMapVisualViewportFixtures.desktop.devicePixelRatio,
    ],
    [408, 630, 1],
  ])('keeps canvas events aligned with SVG overlays at %dx%d DPR %d', (width, height, dpr) => {
    const logicalTransform = createPitchTransform(680, 1050)
    const canvasTransform = createPitchTransform(width, height)
    const source = eventPassFixture[1].end
    const svgPoint = logicalTransform.toScreen(source)
    const scaledSvgPoint = {
      x: (svgPoint.x / 680) * width,
      y: (svgPoint.y / 1050) * height,
    }
    const canvasPoint = canvasTransform.toScreen(source)

    expect(canvasPoint.x).toBeCloseTo(scaledSvgPoint.x)
    expect(canvasPoint.y).toBeCloseTo(scaledSvgPoint.y)
    expect(canvasPoint.x * dpr).toBeCloseTo(scaledSvgPoint.x * dpr)
    expect(canvasPoint.y * dpr).toBeCloseTo(scaledSvgPoint.y * dpr)
  })
})
