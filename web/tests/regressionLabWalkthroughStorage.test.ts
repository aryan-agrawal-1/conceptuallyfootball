import { describe, expect, it } from 'vitest'
import {
  REGRESSION_LAB_WALKTHROUGH_STEPS,
  REGRESSION_LAB_WALKTHROUGH_STORAGE_KEY,
  readRegressionLabWalkthrough,
  saveRegressionLabWalkthroughStatus,
  shouldOfferRegressionLabWalkthrough,
} from '../src/lib/regressionLabWalkthrough'

function memoryStorage(): Storage {
  const values = new Map<string, string>()
  return {
    get length() {
      return values.size
    },
    clear() {
      values.clear()
    },
    getItem(key) {
      return values.get(key) ?? null
    },
    key(index) {
      return [...values.keys()][index] ?? null
    },
    removeItem(key) {
      values.delete(key)
    },
    setItem(key, value) {
      values.set(key, value)
    },
  }
}

describe('Regression Lab walkthrough persistence', () => {
  it('defines the eight agreed live-interface steps with responsible interpretation copy', () => {
    expect(REGRESSION_LAB_WALKTHROUGH_STEPS).toHaveLength(8)
    expect(new Set(REGRESSION_LAB_WALKTHROUGH_STEPS.map(step => step.id)).size).toBe(8)
    expect(REGRESSION_LAB_WALKTHROUGH_STEPS[2].body).toMatch(
      /recommended predictor pack/i,
    )
    expect(REGRESSION_LAB_WALKTHROUGH_STEPS[5].body).toMatch(
      /cross-validation evaluates held-out players/i,
    )
    expect(REGRESSION_LAB_WALKTHROUGH_STEPS[5].body).toMatch(/training R²/i)
    expect(REGRESSION_LAB_WALKTHROUGH_STEPS[6].body).toMatch(
      /exploratory, not causal/i,
    )
  })

  it('offers the walkthrough when no valid record exists', () => {
    const storage = memoryStorage()

    expect(shouldOfferRegressionLabWalkthrough(1, storage)).toBe(true)
    storage.setItem(REGRESSION_LAB_WALKTHROUGH_STORAGE_KEY, '{broken')
    expect(shouldOfferRegressionLabWalkthrough(1, storage)).toBe(true)
  })

  it.each(['skipped', 'completed'] as const)(
    'suppresses a same-version %s walkthrough',
    status => {
      const storage = memoryStorage()

      expect(saveRegressionLabWalkthroughStatus(status, 4, storage)).toBe(true)
      expect(readRegressionLabWalkthrough(storage)).toEqual({ version: 4, status })
      expect(shouldOfferRegressionLabWalkthrough(4, storage)).toBe(false)
    },
  )

  it('offers a materially revised walkthrough version again', () => {
    const storage = memoryStorage()
    saveRegressionLabWalkthroughStatus('completed', 1, storage)

    expect(shouldOfferRegressionLabWalkthrough(1, storage)).toBe(false)
    expect(shouldOfferRegressionLabWalkthrough(2, storage)).toBe(true)
  })

  it('fails safely when browser storage is unavailable', () => {
    const unavailableStorage = {
      ...memoryStorage(),
      getItem() {
        throw new Error('blocked')
      },
      setItem() {
        throw new Error('blocked')
      },
    } as Storage

    expect(shouldOfferRegressionLabWalkthrough(1, unavailableStorage)).toBe(true)
    expect(saveRegressionLabWalkthroughStatus('skipped', 1, unavailableStorage)).toBe(false)
  })
})
