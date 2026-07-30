import { describe, expect, it } from 'vitest'
import {
  hasTargetPredictorLeakage,
  isPredictorSelectableForTarget,
  predictorsForTargetChange,
  recommendedPredictorsForTarget,
  sanitizePredictorsForTarget,
  TARGETS_BY_POSITION,
  type LabPosition,
} from '../src/lib/regressionLabConfig'

describe('recommendedPredictorsForTarget', () => {
  for (const [position, targets] of Object.entries(TARGETS_BY_POSITION) as [
    LabPosition,
    string[],
  ][]) {
    for (const targetKey of targets) {
      it(`never recommends ${targetKey} as its own ${position} predictor`, () => {
        const recommendations = recommendedPredictorsForTarget(targetKey, position)

        expect(recommendations).not.toContain(targetKey)
        expect(new Set(recommendations).size).toBe(recommendations.length)
        expect(recommendations).toHaveLength(5)
      })
    }
  }

  it.each([
    ['MID', 'xa_per_90'],
    ['DEF', 'tackles_per_90'],
    ['DEF', 'interceptions_per_90'],
  ] as const)('repairs the affected %s %s pack', (position, targetKey) => {
    expect(recommendedPredictorsForTarget(targetKey, position)).not.toContain(targetKey)
  })

  it('pads an undersized filtered pack without the target or duplicates', () => {
    const available = [
      'shots_per_90',
      'shots_per_90',
      'goals_per_90',
      'key_passes_per_90',
      'xgchain_per_90',
      'pass_accuracy',
      'tackles_per_90',
    ]

    const recommendations = recommendedPredictorsForTarget(
      'shots_per_90',
      'FWD',
      available,
    )

    expect(recommendations).toHaveLength(5)
    expect(recommendations).not.toContain('shots_per_90')
    expect(new Set(recommendations).size).toBe(recommendations.length)
    expect(recommendations.every(key => available.includes(key))).toBe(true)
  })

  it('keeps fallback recommendations leak-free and unique', () => {
    const recommendations = recommendedPredictorsForTarget('custom_target', 'DEF', [
      'custom_target',
      'tackles_per_90',
      'interceptions_per_90',
      'ball_recoveries_per_90',
      'pass_accuracy',
      'xgbuildup_per_90',
    ])

    expect(recommendations).toEqual([
      'tackles_per_90',
      'interceptions_per_90',
      'ball_recoveries_per_90',
      'pass_accuracy',
      'xgbuildup_per_90',
    ])
  })
})

describe('predictor leakage sanitisation', () => {
  it('canonicalises, deduplicates, and removes the active target', () => {
    expect(
      sanitizePredictorsForTarget(' xa_per_90 ', [
        ' key_passes_per_90 ',
        'xa_per_90',
        'key_passes_per_90',
        ' ',
        'xgchain_per_90',
      ]),
    ).toEqual(['key_passes_per_90', 'xgchain_per_90'])
  })

  it('detects invalid frontend model specifications after canonicalisation', () => {
    expect(hasTargetPredictorLeakage('xa_per_90', ['key_passes_per_90', ' xa_per_90 ']))
      .toBe(true)
    expect(hasTargetPredictorLeakage('xa_per_90', ['key_passes_per_90'])).toBe(false)
  })

  it('prevents manually selecting the target while allowing other metrics', () => {
    expect(isPredictorSelectableForTarget('xa_per_90', ' xa_per_90 ')).toBe(false)
    expect(isPredictorSelectableForTarget('xa_per_90', 'key_passes_per_90')).toBe(true)
  })
})

describe('predictorsForTargetChange', () => {
  it('removes only the new target when preserving custom predictors', () => {
    expect(
      predictorsForTargetChange(
        'xgchain_per_90',
        'MID',
        ['key_passes_per_90', 'xgchain_per_90', 'pass_accuracy'],
        true,
      ),
    ).toEqual(['key_passes_per_90', 'pass_accuracy'])
  })

  it('uses valid recommendations when sanitisation empties the custom set', () => {
    const recommendations = predictorsForTargetChange(
      'xa_per_90',
      'MID',
      ['xa_per_90', ' xa_per_90 '],
      true,
    )

    expect(recommendations.length).toBeGreaterThan(0)
    expect(recommendations).not.toContain('xa_per_90')
  })
})
