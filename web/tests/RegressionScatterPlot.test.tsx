// @vitest-environment jsdom

import React from 'react'
import { act, cleanup, fireEvent, render, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RegressionLabPredictionRow } from '../src/types/api'
import { RegressionScatterPlot } from '../src/components/regression/RegressionScatterPlot'
import {
  buildRegressionScatterDomain,
  REGRESSION_SCATTER_MAX_HEIGHT,
  REGRESSION_SCATTER_MIN_HEIGHT,
} from '../src/components/regression/RegressionScatterPlot.utils'

let measuredWidth = 320
let resizeCallback: ResizeObserverCallback | null = null

class TestResizeObserver {
  constructor(callback: ResizeObserverCallback) {
    resizeCallback = callback
  }

  observe() {}
  unobserve() {}
  disconnect() {}
}

function prediction(
  id: number,
  name: string,
  predicted: number,
  actual: number,
): RegressionLabPredictionRow {
  return {
    actual,
    canonical_player_id: id,
    canonical_player_name: name,
    canonical_team_name: 'Test FC',
    predicted_oof: predicted,
    residual: actual - predicted,
  }
}

const rows = [
  prediction(1, 'Ada Striker', 4.5, 6),
  prediction(2, 'Bea Winger', -2, -3.25),
  prediction(3, 'Cia Keeper', 11, 8),
]

beforeEach(() => {
  measuredWidth = 320
  resizeCallback = null
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(
    () =>
      ({
        bottom: REGRESSION_SCATTER_MIN_HEIGHT,
        height: REGRESSION_SCATTER_MIN_HEIGHT,
        left: 0,
        right: measuredWidth,
        toJSON: () => ({}),
        top: 0,
        width: measuredWidth,
        x: 0,
        y: 0,
      }) as DOMRect,
  )
  vi.stubGlobal('ResizeObserver', TestResizeObserver)
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('buildRegressionScatterDomain', () => {
  it('uses one padded extent across predicted and actual mixed-sign values', () => {
    const domain = buildRegressionScatterDomain([
      prediction(1, 'Low', -20, 5),
      prediction(2, 'High', 10, 50),
    ])

    expect(domain[0]).toBeLessThan(-20)
    expect(domain[1]).toBeGreaterThan(50)
    expect(-20 - domain[0]).toBeCloseTo(domain[1] - 50)
  })

  it('creates stable symmetric domains for zero and non-zero constant ranges', () => {
    expect(buildRegressionScatterDomain([prediction(1, 'Zero', 0, 0)])).toEqual([-1, 1])
    expect(buildRegressionScatterDomain([prediction(1, 'Constant', 25, 25)])).toEqual([
      24,
      26,
    ])
  })

  it('keeps narrow ranges and outliers finite and inside the padded domain', () => {
    const narrow = buildRegressionScatterDomain([
      prediction(1, 'Narrow A', 0.001, 0.00105),
      prediction(2, 'Narrow B', 0.0011, 0.00108),
    ])
    const outlier = buildRegressionScatterDomain([
      prediction(1, 'Typical', 2, 3),
      prediction(2, 'Outlier', 1_000_000, -500_000),
    ])

    expect(narrow.every(Number.isFinite)).toBe(true)
    expect(narrow[0]).toBeLessThan(0.001)
    expect(narrow[1]).toBeGreaterThan(0.0011)
    expect(outlier.every(Number.isFinite)).toBe(true)
    expect(outlier[0]).toBeLessThan(-500_000)
    expect(outlier[1]).toBeGreaterThan(1_000_000)
  })
})

describe('RegressionScatterPlot', () => {
  it('responds to its measured container and enforces its height bounds', () => {
    const view = render(<RegressionScatterPlot rows={rows} targetLabel="Goals" />)
    const svg = view.container.querySelector('svg')

    expect(svg?.getAttribute('width')).toBe('320')
    expect(svg?.getAttribute('height')).toBe(String(REGRESSION_SCATTER_MIN_HEIGHT))

    measuredWidth = 540
    act(() => resizeCallback?.([], {} as ResizeObserver))

    expect(svg?.getAttribute('width')).toBe('540')
    expect(svg?.getAttribute('height')).toBe('300')

    measuredWidth = 1_200
    act(() => resizeCallback?.([], {} as ResizeObserver))

    expect(svg?.getAttribute('width')).toBe('1200')
    expect(svg?.getAttribute('height')).toBe(String(REGRESSION_SCATTER_MAX_HEIGHT))
    expect(svg?.getAttribute('viewBox')).toBe(
      `0 0 1200 ${REGRESSION_SCATTER_MAX_HEIGHT}`,
    )
  })

  it('offers the same diagnostic values on keyboard focus and pointer hover', () => {
    const view = render(<RegressionScatterPlot rows={rows} targetLabel="Goals" />)
    const point = view.getByRole('button', {
      name: /Ada Striker.*Predicted 4\.5.*Actual 6.*Residual 1\.5/i,
    })

    fireEvent.focus(point)
    const focusedTooltip = view.getByRole('status')
    expect(within(focusedTooltip).getByText('Predicted (OOF)')).toBeTruthy()
    expect(within(focusedTooltip).getByText('4.5')).toBeTruthy()
    expect(within(focusedTooltip).getByText('6')).toBeTruthy()
    expect(within(focusedTooltip).getByText('1.5')).toBeTruthy()

    fireEvent.blur(point)
    expect(view.queryByRole('status')).toBeNull()

    fireEvent.pointerEnter(point)
    expect(view.getByRole('status')).toBeTruthy()
  })

  it('keeps a detailed edge-point tooltip within a narrow chart', () => {
    measuredWidth = 240
    const view = render(
      <RegressionScatterPlot
        rows={[
          prediction(1, 'Left Edge', -100, -100),
          prediction(2, 'Right Edge', 100, 100),
        ]}
        targetLabel="Rating"
      />,
    )
    fireEvent.focus(view.getByRole('button', { name: /Left Edge/i }))

    const tooltip = view.getByRole('status')
    expect(tooltip.style.width).toBe('224px')
    expect(tooltip.style.left).toBe('120px')
    expect(tooltip.style.transform).toMatch(/translate\(-50%/)
  })

  it('keeps the identity reference aligned to the shared plot corners', () => {
    const view = render(<RegressionScatterPlot rows={rows} targetLabel="Goals" />)
    const identity = view.container.querySelector('line[stroke-dasharray="5 5"]')

    expect(identity?.getAttribute('x1')).toBe('42')
    expect(identity?.getAttribute('y1')).toBe('192')
    expect(identity?.getAttribute('x2')).toBe('308')
    expect(identity?.getAttribute('y2')).toBe('34')
  })

  it('retains a clear empty state without instantiating a chart', () => {
    const view = render(<RegressionScatterPlot rows={[]} targetLabel="Goals" />)

    expect(view.getByText('No points to plot.')).toBeTruthy()
    expect(view.container.querySelector('svg')).toBeNull()
  })
})
