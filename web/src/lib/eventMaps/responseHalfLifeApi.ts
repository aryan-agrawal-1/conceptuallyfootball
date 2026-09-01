import type { ResponseHalfLifeCohort, ResponseHalfLifePayload } from '../../types/responseHalfLife'
import { BASE, readJson, requestParams } from './api'
import { appendStateLens, type StateLensRequest } from './stateLensApi'

type ApiSummary = {
  sample_size: number
  mean_seconds: number | null
  median_seconds: number | null
}

type ApiCohort = {
  reliability: ResponseHalfLifeCohort['reliability']
  qualifying_concessions: number
  qualifying_windows: number
  qualifying_matches: number
  censored_episodes: number
  attacking: { half_life_seconds: ApiSummary; recovered_concessions: number }
  structural: { half_life_seconds: ApiSummary; recovered_concessions: number }
}

type ApiPayload = {
  definitions: { window_seconds: number }
  selected: ApiCohort
}

function mapSummary(value: ApiSummary) {
  return {
    sampleSize: value.sample_size,
    meanSeconds: value.mean_seconds,
    medianSeconds: value.median_seconds,
  }
}

function mapCohort(value: ApiCohort): ResponseHalfLifeCohort {
  return {
    reliability: value.reliability,
    qualifyingConcessions: value.qualifying_concessions,
    qualifyingWindows: value.qualifying_windows,
    qualifyingMatches: value.qualifying_matches,
    censoredEpisodes: value.censored_episodes,
    attacking: {
      halfLifeSeconds: mapSummary(value.attacking.half_life_seconds),
      recoveredConcessions: value.attacking.recovered_concessions,
    },
    structural: {
      halfLifeSeconds: mapSummary(value.structural.half_life_seconds),
      recoveredConcessions: value.structural.recovered_concessions,
    },
  }
}

export async function fetchTeamResponseHalfLife(
  teamId: number,
  competition: string,
  season: string,
  matchRef: string | null,
  stateLens: StateLensRequest,
): Promise<ResponseHalfLifePayload> {
  const params = requestParams(competition, season, undefined, matchRef)
  appendStateLens(params, stateLens)
  const raw = await readJson<ApiPayload>(
    `${BASE}/team-seasons/response-half-life/${teamId}?${params}`,
  )
  return {
    definitions: { windowSeconds: raw.definitions.window_seconds },
    selected: mapCohort(raw.selected),
  }
}
