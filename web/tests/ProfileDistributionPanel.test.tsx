// @vitest-environment jsdom

import React from 'react'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { ProfileDistributionPanel } from '../src/components/profile/ProfileDistributionPanel'
import type {
  PlayerRow,
  ProfileDistributionPayload,
  StatMeta,
} from '../src/types/api'

const player: PlayerRow = {
  canonical_player_id: 1,
  canonical_player_name: 'Test Forward',
  canonical_team_id: 1,
  canonical_team_name: 'Test FC',
  competition_season: 1,
  competition_code: 'ENG1',
  season_label: '2025-26',
  position_group: 'FWD',
  native_position: 'Forward',
  minutes: 900,
  formula_version: 'test',
  derived_run_id: 1,
  eligibility: {
    percentiles_eligible: true,
    percentiles_ineligibility_reason: null,
    scores_eligible: true,
    scores_ineligibility_reason: null,
  },
  metrics: { xg_per_90: 0.4 },
  percentiles: { xg_per_90: 75 },
  scores: {},
  score_raw: {},
}

const meta: StatMeta = {
  formula_version: 'test',
  minimum_eligible_minutes: 600,
  metric_groups: { attacking: 'Attacking' },
  metrics: {
    xg_per_90: {
      label: 'xG/90',
      group: 'attacking',
      unit: 'per90',
      sources_used: ['test'],
      description: '',
      caveat: '',
      semantic_color: 'positive',
    },
  },
}

const distributions: ProfileDistributionPayload = {
  position_group: 'FWD',
  cohort_count: 100,
  bin_limit: 16,
  context: {
    competition_code: 'ENG1',
    season_label: '2025-26',
  },
  metrics: {
    xg_per_90: {
      count: 100,
      min: 0,
      max: 0.8,
      p25: 0.2,
      median: 0.35,
      p75: 0.5,
      bins: [
        { start: 0, end: 0.4, count: 60 },
        { start: 0.4, end: 0.8, count: 40 },
      ],
    },
  },
}

afterEach(cleanup)

describe('ProfileDistributionPanel', () => {
  it('explains the cohort, histogram, player marker, percentile, quartiles, and benchmark', () => {
    render(
      <ProfileDistributionPanel
        player={player}
        rateMode="per90"
        meta={meta}
        metricKeys={['xg_per_90']}
        distributions={distributions}
      />,
    )

    expect(screen.getByText('How to read these')).toBeTruthy()
    expect(screen.getByText(/taller bars mean more players/i)).toBeTruthy()
    expect(screen.getByText(/this player's value/i)).toBeTruthy()
    expect(screen.getByText(/percentile within this exact cohort/i)).toBeTruthy()
    expect(screen.getByText(/middle 50% of players/i)).toBeTruthy()
    expect(screen.getByText(/favourable quartile for directional metrics/i)).toBeTruthy()
  })
})
