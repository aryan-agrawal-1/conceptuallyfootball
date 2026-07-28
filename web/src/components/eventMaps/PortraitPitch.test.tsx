// @vitest-environment jsdom

import { act, cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { eventPassFixture, eventShotFixture } from '../../lib/eventMaps/fixtures'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import { PortraitPitch } from './PortraitPitch'

type ResizeCallback = ResizeObserverCallback

let resizeCallback: ResizeCallback | null = null
let measuredWidth = 340
let measuredHeight = 525

const canvasContext = {
  fillStyle: '',
  globalAlpha: 1,
  lineCap: 'butt',
  lineWidth: 1,
  strokeStyle: '',
  arc: vi.fn(),
  beginPath: vi.fn(),
  clearRect: vi.fn(),
  fill: vi.fn(),
  fillRect: vi.fn(),
  lineTo: vi.fn(),
  moveTo: vi.fn(),
  quadraticCurveTo: vi.fn(),
  restore: vi.fn(),
  save: vi.fn(),
  setTransform: vi.fn(),
  stroke: vi.fn(),
} as unknown as CanvasRenderingContext2D

class TestResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback
  }

  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  measuredWidth = 340
  measuredHeight = 525
  resizeCallback = null
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    () =>
      ({
        left: 0,
        top: 0,
        right: measuredWidth,
        bottom: measuredHeight,
        width: measuredWidth,
        height: measuredHeight,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }) as DOMRect,
  )
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext as never)
  vi.stubGlobal('ResizeObserver', TestResizeObserver)
  Object.defineProperty(window, 'devicePixelRatio', { configurable: true, value: 2 })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('PortraitPitch', () => {
  it('offers keyboard event inspection and accessible shot targets', () => {
    const onSelect = vi.fn<(event: SelectablePitchEvent | null) => void>()
    const view = render(
      <PortraitPitch
        passes={eventPassFixture}
        shots={eventShotFixture}
        onSelectedEventChange={onSelect}
      />,
    )
    const pitch = view.getByRole('application')

    expect(view.getAllByRole('button', { name: /shot, minute/i })).toHaveLength(
      eventShotFixture.length,
    )
    fireEvent.keyDown(pitch, { key: 'ArrowUp' })

    expect(onSelect).toHaveBeenCalled()
    expect(view.getByText(/pass, minute/i)).toBeTruthy()

    fireEvent.keyDown(pitch, { key: 'Escape' })
    expect(view.getByText('No event selected.')).toBeTruthy()
  })

  it('supports pointer and touch nearest-event selection', () => {
    const onSelect = vi.fn<(event: SelectablePitchEvent | null) => void>()
    const view = render(
      <PortraitPitch
        passes={eventPassFixture}
        shots={eventShotFixture}
        onSelectedEventChange={onSelect}
      />,
    )
    const pitch = view.getByRole('application')
    vi.spyOn(pitch, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      top: 0,
      right: measuredWidth,
      bottom: measuredHeight,
      width: measuredWidth,
      height: measuredHeight,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    })

    fireEvent(
      pitch,
      new MouseEvent('pointerdown', {
        bubbles: true,
        clientX: 245,
        clientY: 431,
      }),
    )

    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'pass-01' }))
  })

  it('updates its backing store after resize without changing the pitch aspect box', () => {
    const view = render(<PortraitPitch passes={eventPassFixture} />)
    const canvas = view.container.querySelector('canvas')
    const frame = canvas?.parentElement

    expect(canvas?.width).toBe(680)
    expect(canvas?.height).toBe(1050)
    expect(frame?.className).toContain('aspect-[68/105]')

    measuredWidth = 408
    measuredHeight = 630
    act(() => resizeCallback?.([], {} as ResizeObserver))

    expect(canvas?.width).toBe(816)
    expect(canvas?.height).toBe(1260)
  })
})
