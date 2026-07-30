// @vitest-environment jsdom

import React from 'react'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { LabHelpHover } from '../src/components/regression/LabHelpHover'
import { RegressionLabWalkthrough } from '../src/components/regression/RegressionLabWalkthrough'
import {
  REGRESSION_LAB_WALKTHROUGH_STEPS,
  readRegressionLabWalkthrough,
  saveRegressionLabWalkthroughStatus,
} from '../src/lib/regressionLabWalkthrough'

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

function rect(
  left: number,
  top: number,
  width: number,
  height: number,
): DOMRect {
  return {
    left,
    top,
    right: left + width,
    bottom: top + height,
    width,
    height,
    x: left,
    y: top,
    toJSON: () => ({}),
  }
}

function AnchoredWalkthrough({ withInput = false }: { withInput?: boolean }) {
  return (
    <div>
      {withInput ? <input aria-label="Model note" defaultValue="unchanged" /> : null}
      {REGRESSION_LAB_WALKTHROUGH_STEPS.map((step, index) => (
        <div
          key={step.id}
          data-regression-walkthrough={step.id}
          data-test-index={index}
        >
          {step.title}
        </div>
      ))}
      <RegressionLabWalkthrough />
    </div>
  )
}

beforeEach(() => {
  window.localStorage.clear()
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: 1024 })
  Object.defineProperty(window, 'innerHeight', { configurable: true, value: 768 })
  vi.stubGlobal('ResizeObserver', TestResizeObserver)
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation(() => ({
      matches: false,
      media: '(prefers-reduced-motion: reduce)',
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    })),
  )
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockImplementation(function (
    this: HTMLElement,
  ) {
    const index = Number(this.dataset.testIndex ?? 0)
    return this.dataset.regressionWalkthrough
      ? rect(40, 100 + index * 20, 220, 36)
      : rect(0, 0, 360, 260)
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('RegressionLabWalkthrough', () => {
  it('waits for explicit Start and persists first-visit Skip', async () => {
    const view = render(<AnchoredWalkthrough />)

    expect(
      screen.getByRole('heading', { name: 'Learn the workflow in eight short steps' }),
    ).toBeTruthy()
    expect(screen.queryByRole('status')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: 'Skip' }))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(readRegressionLabWalkthrough()).toEqual({ version: 1, status: 'skipped' })

    view.unmount()
    render(<AnchoredWalkthrough />)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('provides all eight steps, Back, Next, Finish, and permanent restart', async () => {
    render(<AnchoredWalkthrough withInput />)
    fireEvent.click(screen.getByRole('button', { name: 'Start walkthrough' }))

    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Step 1 of 8'))
    expect((screen.getByRole('button', { name: 'Back' }) as HTMLButtonElement).disabled).toBe(
      true,
    )
    expect((screen.getByLabelText('Model note') as HTMLInputElement).value).toBe('unchanged')

    for (let step = 2; step <= 8; step += 1) {
      fireEvent.click(screen.getByRole('button', { name: 'Next' }))
      await waitFor(() =>
        expect(screen.getByRole('status').textContent).toContain(`Step ${step} of 8`),
      )
    }

    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Step 7 of 8'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    fireEvent.click(screen.getByRole('button', { name: 'Finish' }))

    const launcher = screen.getByRole('button', {
      name: 'Open Regression Lab walkthrough',
    })
    await waitFor(() => expect(document.activeElement).toBe(launcher))
    expect(readRegressionLabWalkthrough()).toEqual({ version: 1, status: 'completed' })
    expect((screen.getByLabelText('Model note') as HTMLInputElement).value).toBe('unchanged')

    fireEvent.click(launcher)
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Step 1 of 8'))
  })

  it('announces unavailable anchors and continues without breaking', async () => {
    render(<RegressionLabWalkthrough />)
    fireEvent.click(screen.getByRole('button', { name: 'Start walkthrough' }))

    await waitFor(() => {
      expect(screen.getByText(/cohort controls are not available yet/i)).toBeTruthy()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Step 2 of 8'))
  })

  it('traps focus, restores the launcher, and supports Escape dismissal', async () => {
    saveRegressionLabWalkthroughStatus('completed')
    render(<AnchoredWalkthrough />)
    const launcher = screen.getByRole('button', {
      name: 'Open Regression Lab walkthrough',
    })
    launcher.focus()
    fireEvent.click(launcher)

    const title = await screen.findByRole('heading', { name: 'Define the cohort' })
    await waitFor(() => expect(document.activeElement).toBe(title))

    const next = screen.getByRole('button', { name: 'Next' })
    next.focus()
    fireEvent.keyDown(document, { key: 'Tab' })
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Skip' }))

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(launcher))
    expect(readRegressionLabWalkthrough()?.status).toBe('skipped')
  })

  it('uses non-animated scrolling when reduced motion is requested', async () => {
    vi.stubGlobal(
      'matchMedia',
      vi.fn().mockImplementation(() => ({
        matches: true,
        media: '(prefers-reduced-motion: reduce)',
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    )
    render(<AnchoredWalkthrough />)
    fireEvent.click(screen.getByRole('button', { name: 'Start walkthrough' }))

    await waitFor(() => {
      expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalledWith(
        expect.objectContaining({ behavior: 'auto' }),
      )
    })
  })

  it('places a narrow-screen callout away from its live anchor', async () => {
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 844 })
    render(<AnchoredWalkthrough />)
    fireEvent.click(screen.getByRole('button', { name: 'Start walkthrough' }))

    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.style.left).toBe('12px'))
    expect(Number.parseFloat(dialog.style.top)).toBeGreaterThan(136)
  })
})

describe('LabHelpHover keyboard access', () => {
  it('exposes help on focus and dismisses it with Escape', async () => {
    render(
      <LabHelpHover label="Model readiness">
        <p>Readiness detail</p>
      </LabHelpHover>,
    )
    const button = screen.getByRole('button', { name: 'Model readiness' })

    button.focus()
    expect((await screen.findByRole('tooltip')).textContent).toContain('Readiness detail')
    expect(button.getAttribute('aria-describedby')).toBeTruthy()

    fireEvent.keyDown(button, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('tooltip')).toBeNull())
    expect(document.activeElement).toBe(button)
  })
})
