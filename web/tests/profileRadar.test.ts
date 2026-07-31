// @vitest-environment jsdom

import { beforeEach, describe, expect, it } from 'vitest'
import { distributionBenchmark } from '../src/lib/profileDistributions'
import { parseStatsParam } from '../src/lib/comparisonUrl'
import {
  parseDataVisualiserParams,
  writeDataVisualiserParams,
} from '../src/lib/dataVisualiserUrl'
import {
  buildDefaultProfileExportPreset,
  hydrateProfileExportPreset,
} from '../src/lib/profileExport'
import {
  LEGACY_PIZZA_STORAGE_KEY,
  PIZZA_STORAGE_KEY,
  canonicalProfileMetricKey,
  dedupeCanonicalMetricKeys,
  defaultPizzaMetricKeys,
  moveMetricKey,
  radarLabelLines,
  resolveRadarMetricKeys,
} from '../src/lib/profileMetrics'
import {
  loadPizzaMetricKeys,
  savePizzaMetricKeys,
} from '../src/lib/profilePizzaStorage'
import type {
  PlayerRow,
  PositionGroup,
  ProfileMetricDistribution,
  StatMeta,
} from '../src/types/api'

const POSITIONS: PositionGroup[] = ['FWD', 'MID', 'DEF', 'GK', 'UNK']

function mockProfile(position: PositionGroup): { player: PlayerRow; meta: StatMeta } {
  const keys = defaultPizzaMetricKeys(position)
  const metrics = Object.fromEntries(
    keys.map(key => [
      key,
      {
        label: key,
        group: 'attacking',
        unit: key.endsWith('_per_90') ? 'per90' : 'ratio',
        sources_used: ['test'],
        description: '',
        caveat: '',
        semantic_color: 'positive',
      },
    ]),
  ) as StatMeta['metrics']
  const values = Object.fromEntries(keys.map(key => [key, 1]))
  const percentiles = Object.fromEntries(keys.map(key => [key, 50]))
  return {
    meta: {
      formula_version: 'test',
      minimum_eligible_minutes: 600,
      metric_groups: { attacking: 'Attacking' },
      metrics,
    },
    player: {
      canonical_player_id: 1,
      canonical_player_name: 'Test Player',
      canonical_team_id: 1,
      canonical_team_name: 'Test FC',
      competition_season: 1,
      competition_code: 'ENG1',
      season_label: '2025-26',
      position_group: position,
      native_position: position,
      minutes: 900,
      formula_version: 'test',
      derived_run_id: 1,
      eligibility: {
        percentiles_eligible: true,
        percentiles_ineligibility_reason: null,
        scores_eligible: true,
        scores_ineligibility_reason: null,
      },
      metrics: values,
      percentiles,
      scores: {},
      score_raw: {},
    },
  }
}

describe('profile radar templates and canonical state', () => {
  it('defines stable unique role defaults and fills twelve axes where the metric contract is sufficient', () => {
    for (const position of POSITIONS) {
      const first = defaultPizzaMetricKeys(position)
      const second = defaultPizzaMetricKeys(position)
      expect(second).toEqual(first)
      expect(dedupeCanonicalMetricKeys(first)).toEqual(first)
      if (position !== 'GK') expect(first).toHaveLength(12)
    }
  })

  it('deduplicates logical aliases while preserving first occurrence', () => {
    expect(dedupeCanonicalMetricKeys(['xg', 'xg_per_90', 'xa_per_90', 'xa'])).toEqual([
      'xg',
      'xa_per_90',
    ])
    expect(canonicalProfileMetricKey('xg')).toBe(canonicalProfileMetricKey('xg_per_90'))
  })

  it('uses deterministic unique fallbacks for unavailable metrics', () => {
    const available = [
      'goals_per_90',
      'xa_per_90',
      'shots_per_90',
      'key_passes_per_90',
      'successful_dribbles_per_90',
      'chance_involvement_per_90',
      'xgchain_per_90',
      'pass_accuracy',
      'ball_recoveries_per_90',
      'ground_duels_won_per_90',
      'interceptions_per_90',
      'aerial_duels_won_per_90',
    ]
    const resolved = resolveRadarMetricKeys({
      position: 'FWD',
      current: ['missing', 'goals_per_90', 'goals_per_90'],
      available,
      targetCount: 12,
    })
    expect(resolved).toHaveLength(12)
    expect(new Set(resolved.map(canonicalProfileMetricKey)).size).toBe(12)
    expect(resolveRadarMetricKeys({
      position: 'FWD',
      current: ['missing', 'goals_per_90', 'goals_per_90'],
      available,
      targetCount: 12,
    })).toEqual(resolved)
  })

  it('reorders without mutating the source selection', () => {
    const source = ['a', 'b', 'c']
    expect(moveMetricKey(source, 'b', -1)).toEqual(['b', 'a', 'c'])
    expect(source).toEqual(['a', 'b', 'c'])
  })

  it('keeps short labels on one line and balances long labels across two', () => {
    expect(radarLabelLines('xG')).toEqual(['xG'])
    expect(radarLabelLines('Defensive Action Density')).toEqual([
      'Defensive',
      'Action Density',
    ])
    expect(radarLabelLines('  Defensive   Action Density  ')).toEqual([
      'Defensive',
      'Action Density',
    ])
  })

  it('deduplicates visualiser and comparison URL state', () => {
    const parsed = parseDataVisualiserParams(
      new URLSearchParams('chart=radar&radar=xg_per_90,xg,xa_per_90'),
    )
    expect(parsed.radarMetrics).toEqual(['xg_per_90', 'xa_per_90'])
    expect(writeDataVisualiserParams({
      ...parsed,
      radarMetrics: ['xg', 'xg_per_90', 'xa_per_90'],
    }).get('radar')).toBe('xg,xa_per_90')
    expect(parseStatsParam('xg,xg_per_90,xa_per_90')).toEqual(['xg', 'xa_per_90'])
  })
})

describe('radar persistence and export migration', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
  })

  it('migrates legacy session axes, pads them, and scopes new state by position', () => {
    sessionStorage.setItem(
      LEGACY_PIZZA_STORAGE_KEY,
      JSON.stringify(['xg', 'xg_per_90', 'xa_per_90', 'shots_per_90']),
    )
    const migrated = loadPizzaMetricKeys('FWD')
    expect(migrated).toHaveLength(12)
    expect(new Set(migrated.map(canonicalProfileMetricKey)).size).toBe(12)

    savePizzaMetricKeys('MID', defaultPizzaMetricKeys('MID').slice(0, 6))
    const stored = JSON.parse(sessionStorage.getItem(PIZZA_STORAGE_KEY) ?? '{}')
    expect(stored.version).toBe(2)
    expect(stored.positions.FWD).toEqual(migrated)
    expect(stored.positions.MID).toHaveLength(6)
  })

  it('defaults exports to the fuller radar and migrates duplicate v1 axes', () => {
    const { player, meta } = mockProfile('FWD')
    expect(buildDefaultProfileExportPreset(player, meta, 'per90').chartMetricKeys).toHaveLength(12)

    const defaults = defaultPizzaMetricKeys('FWD')
    localStorage.setItem(
      'conceptually-football:profile-export:v1',
      JSON.stringify({
        'player:FWD': {
          version: 1,
          theme: 'conceptually-football',
          rateMode: 'per90',
          stats: defaults.slice(0, 4).map(key => ({ key, label: key })),
          chartEnabled: true,
          chartMetricKeys: ['xg', 'xg_per_90', 'xa_per_90', ...defaults.slice(2, 8)],
          notesEnabled: false,
          similarEnabled: false,
          showPercentiles: true,
        },
      }),
    )
    const hydrated = hydrateProfileExportPreset(player, meta, 'per90')
    expect(hydrated.chartMetricKeys).toHaveLength(12)
    expect(new Set(hydrated.chartMetricKeys.map(canonicalProfileMetricKey)).size).toBe(12)
    expect(hydrated.distributionEnabled).toBe(false)
  })
})

describe('distribution benchmark semantics', () => {
  const distribution: ProfileMetricDistribution = {
    count: 10,
    min: 0,
    max: 9,
    p25: 2.25,
    median: 4.5,
    p75: 6.75,
    bins: [],
  }

  it('uses the favourable quartile in the correct direction', () => {
    expect(distributionBenchmark(distribution, 'positive')).toEqual({
      label: 'Favourable quartile',
      value: 6.75,
    })
    expect(distributionBenchmark(distribution, 'negative')).toEqual({
      label: 'Favourable quartile',
      value: 2.25,
    })
    expect(distributionBenchmark(distribution, 'contextual')).toBeNull()
  })
})
