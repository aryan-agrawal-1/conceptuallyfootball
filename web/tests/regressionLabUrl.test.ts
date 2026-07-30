import { describe, expect, it } from 'vitest'
import {
  parseRegressionLabParams,
  writeRegressionLabParams,
} from '../src/lib/regressionLabUrl'

describe('Regression Lab URL state', () => {
  it('repairs target leakage and duplicate predictors deterministically', () => {
    const parsed = parseRegressionLabParams(
      new URLSearchParams(
        'competition=EPL&season=2025-26&position=MID&min_minutes=900' +
          '&target=xa_per_90&predictors=key_passes_per_90,xa_per_90,' +
          '%20key_passes_per_90%20,xgchain_per_90',
      ),
    )

    expect(parsed.predictors).toEqual(['key_passes_per_90', 'xgchain_per_90'])
  })

  it('omits a predictor list that contained only the target', () => {
    const parsed = parseRegressionLabParams(
      new URLSearchParams(
        'competition=EPL&season=2025-26&target=xa_per_90' +
          '&predictors=xa_per_90,%20xa_per_90%20',
      ),
    )

    expect(parsed.predictors).toBeUndefined()
  })

  it('writes only canonical, leak-free predictor combinations', () => {
    const written = writeRegressionLabParams({
      competition: 'EPL',
      season: '2025-26',
      position_group: 'MID',
      min_minutes: 900,
      target: ' xa_per_90 ',
      predictors: [
        'key_passes_per_90',
        ' xa_per_90 ',
        'key_passes_per_90',
        'xgchain_per_90',
      ],
    })

    expect(written.get('target')).toBe('xa_per_90')
    expect(written.get('predictors')).toBe('key_passes_per_90,xgchain_per_90')
  })

  it('round-trips repaired invalid shared state', () => {
    const invalid = new URLSearchParams(
      'competition=EPL&season=2025-26&position=MID&min_minutes=900' +
        '&target=xa_per_90&predictors=xa_per_90,key_passes_per_90,' +
        'key_passes_per_90,xgchain_per_90&run=1',
    )
    const repaired = parseRegressionLabParams(invalid)
    const canonical = writeRegressionLabParams(repaired, {
      includeRunFlag: repaired.autoRun,
    })

    expect(parseRegressionLabParams(canonical)).toEqual(repaired)
    expect(canonical.get('predictors')).toBe('key_passes_per_90,xgchain_per_90')
  })
})
