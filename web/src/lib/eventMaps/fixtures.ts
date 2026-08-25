import type {
  ActionGridCell,
  EventMatchLookup,
  EventPass,
  EventShot,
  PlayerEventProfilePayload,
  PlayerPassMapPayload,
  TeamEventProfilePayload,
  TeamPassFlow,
} from '../../types/eventMaps'

export const eventMapVisualViewportFixtures = {
  mobile: {
    name: 'Mobile portrait baseline',
    width: 340,
    height: 525,
    devicePixelRatio: 3,
  },
  desktop: {
    name: 'Desktop portrait baseline',
    width: 476,
    height: 735,
    devicePixelRatio: 2,
  },
} as const

export const eventMapMatchFixture: EventMatchLookup = {
  mci_ars_2026_02_21: {
    matchId: 'mci_ars_2026_02_21',
    opponent: 'Arsenal',
    matchDate: '2026-02-21',
    venue: 'home',
  },
  liv_mci_2026_03_08: {
    matchId: 'liv_mci_2026_03_08',
    opponent: 'Liverpool',
    matchDate: '2026-03-08',
    venue: 'away',
  },
}

export const eventPassFixture: EventPass[] = [
  {
    id: 'pass-01',
    matchRef: 'mci_ars_2026_02_21',
    teamId: 101,
    minute: 8,
    second: 14,
    start: { x: 18, y: 72 },
    end: { x: 43, y: 63 },
    outcome: 'successful',
    length: 27.4,
    progressive: true,
    finalThirdEntry: false,
    boxEntry: false,
    keyPass: false,
    cross: false,
    longBall: false,
  },
  {
    id: 'pass-02',
    matchRef: 'mci_ars_2026_02_21',
    teamId: 101,
    minute: 26,
    second: 41,
    start: { x: 55, y: 48 },
    end: { x: 84, y: 32 },
    outcome: 'successful',
    length: 33.1,
    progressive: true,
    finalThirdEntry: true,
    boxEntry: true,
    keyPass: true,
    cross: false,
    longBall: false,
  },
  {
    id: 'pass-03',
    matchRef: 'liv_mci_2026_03_08',
    teamId: 101,
    minute: 49,
    second: 3,
    start: { x: 36, y: 12 },
    end: { x: 68, y: 27 },
    outcome: 'unsuccessful',
    length: 35.2,
    progressive: false,
    finalThirdEntry: true,
    boxEntry: false,
    keyPass: false,
    cross: true,
    longBall: true,
  },
  {
    id: 'pass-04',
    matchRef: 'liv_mci_2026_03_08',
    teamId: 101,
    minute: 77,
    second: 52,
    start: { x: 71, y: 83 },
    end: { x: 92, y: 57 },
    outcome: 'successful',
    length: 31.8,
    progressive: true,
    finalThirdEntry: false,
    boxEntry: true,
    keyPass: true,
    cross: true,
    longBall: false,
  },
]

export const eventShotFixture: EventShot[] = [
  {
    id: 'shot-01',
    matchRef: 'mci_ars_2026_02_21',
    teamId: 101,
    minute: 27,
    location: { x: 88, y: 46 },
    outcome: 'goal',
    bodyPart: 'left_foot',
    situation: 'open_play',
    bigChance: true,
    assisted: true,
    perspective: 'for',
    goalMouth: { y: 48.1, z: 12 },
  },
  {
    id: 'shot-02',
    matchRef: 'mci_ars_2026_02_21',
    teamId: 101,
    minute: 64,
    second: 19,
    location: { x: 79, y: 68 },
    outcome: 'blocked',
    bodyPart: 'right_foot',
    situation: 'corner',
    bigChance: false,
    assisted: true,
    perspective: 'for',
    blockedAt: { x: 84, y: 61 },
  },
  {
    id: 'shot-03',
    matchRef: 'liv_mci_2026_03_08',
    teamId: 202,
    minute: 83,
    location: { x: 91, y: 37 },
    outcome: 'saved',
    bodyPart: 'head',
    situation: 'set_piece',
    bigChance: true,
    assisted: true,
    perspective: 'against',
  },
]

export const eventActionGridFixture: ActionGridCell[] = Array.from(
  { length: 384 },
  (_, index): ActionGridCell => {
    const column = index % 24
    const row = Math.floor(index / 24)
    const centrality = 1 - Math.abs(row - 7.5) / 8.5
    const advancement = (column + 2) / 25
    const rawCount = Math.max(0, Math.round(centrality * advancement * 8) - ((index * 7) % 3))

    return {
      column,
      row,
      rawCount,
      per90Count: Number((rawCount / 11.3).toFixed(2)),
      share: Number((rawCount / 680).toFixed(4)),
    }
  },
)

export const teamPassFlowFixture: TeamPassFlow[] = [
  {
    id: 'flow-01',
    bin: { column: 0, row: 1 },
    origin: { x: 8, y: 37 },
    destination: { x: 31, y: 42 },
    completedCount: 118,
    share: 0.12,
    meanLength: 25.2,
  },
  {
    id: 'flow-02',
    bin: { column: 1, row: 1 },
    origin: { x: 24, y: 39 },
    destination: { x: 48, y: 43 },
    completedCount: 84,
    share: 0.085,
    meanLength: 26.1,
  },
  {
    id: 'flow-03',
    bin: { column: 2, row: 0 },
    origin: { x: 42, y: 14 },
    destination: { x: 63, y: 35 },
    completedCount: 43,
    share: 0.044,
    meanLength: 26.5,
  },
  {
    id: 'flow-04',
    bin: { column: 3, row: 2 },
    origin: { x: 59, y: 64 },
    destination: { x: 78, y: 48 },
    completedCount: 31,
    share: 0.032,
    meanLength: 23.2,
  },
]

const fixtureMetadata = {
  formulaVersion: 'event_profiles_v3',
  materialisationVersion: 'fixture-2026-07-28',
  updatedAt: '2026-07-28T12:00:00Z',
}

const fixtureCoverage = {
  matchesIncluded: 38,
  matchesExpected: 38,
  minutes: 2948,
  complete: true,
}

export const playerEventProfileFixture: PlayerEventProfilePayload = {
  playerId: 9001,
  playerName: 'Fixture Midfielder',
  competition: 'ENG1',
  season: '2025-26',
  teamId: 101,
  teamName: 'Fixture City',
  splitType: 'team',
  coverage: fixtureCoverage,
  metadata: fixtureMetadata,
  summary: { pass_attempts: 1984, shots: 38, valid_location_actions: 2814 },
  modules: {
    passMap: { available: true, sparse: false },
    shotMap: { available: true, sparse: true },
    actionGrid: { available: true, sparse: false },
  },
  averageTouchLocation: { x: 58.2, y: 51.4, sampleSize: 1984 },
  touchGrid: eventActionGridFixture,
  shots: eventShotFixture,
  matches: eventMapMatchFixture,
}

export const playerPassMapFixture: PlayerPassMapPayload = {
  playerId: 9001,
  competition: 'ENG1',
  season: '2025-26',
  filter: 'all',
  outcome: 'completed',
  truncated: false,
  totalMatching: eventPassFixture.length,
  carriesTruncated: false,
  totalCarries: 0,
  totalAllCarries: 0,
  passes: eventPassFixture,
  carries: [],
  matches: eventMapMatchFixture,
}

export const teamEventProfileFixture: TeamEventProfilePayload = {
  teamId: 101,
  teamName: 'Fixture City',
  competition: 'ENG1',
  season: '2025-26',
  coverage: fixtureCoverage,
  metadata: fixtureMetadata,
  summary: { pass_attempts: 19840, shots_for: 428, shots_against: 312 },
  passFlows: teamPassFlowFixture,
  shots: eventShotFixture,
  actionTerritory: eventActionGridFixture,
  opponentActionTerritory: eventActionGridFixture,
  matches: eventMapMatchFixture,
  stateLens: {
    contractVersion: 'state_lens_v1',
    selected: { state: 'all', goalDifference: null, phase: null, drawProvenance: null, minimumStateAgeSeconds: null, maximumStateAgeSeconds: null },
    evidence: { exposureSeconds: 205200, exposureMinutes: 3420, episodeCount: 96, matchCount: 38, matchesIncluded: 38, matchesExcluded: 0, exclusionReasons: {}, formulaVersion: 'team_game_state_v1', empty: false },
    eligibleRefinements: {
      states: ['drawing', 'winning', 'losing'],
      goalDifferences: [-2, -1, 0, 1, 2],
      phases: ['first_half', 'second_half'],
      drawProvenances: ['none', 'neutral', 'restored', 'surrendered'],
      stateAgeSeconds: { minimum: 0, maximum: 2700 },
    },
    comparison: { enabled: false, baseline: null, baselineEvidence: null, comparison: { state: 'all', goalDifference: null, phase: null, drawProvenance: null, minimumStateAgeSeconds: null, maximumStateAgeSeconds: null }, comparisonEvidence: { exposureSeconds: 205200, exposureMinutes: 3420, episodeCount: 96, matchCount: 38, matchesIncluded: 38, matchesExcluded: 0, exclusionReasons: {}, formulaVersion: 'team_game_state_v1', empty: false } },
  },
}
