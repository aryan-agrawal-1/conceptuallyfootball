import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { fetchGkStatMatrix, fetchPlayerCohort, fetchStatMatrix } from '../lib/api'
import type { MatrixFilters, MatrixResponse } from '../types/api'
import type { SortingState } from '@tanstack/react-table'
import type { MatrixRateMode } from '../lib/matrixRateMode'

export const DEFAULT_FILTERS: MatrixFilters = {
  competition: 'ENG1',
  season: '2025-26',
  min_minutes: 0,
}


export function usePlayerCohort(
  filters: MatrixFilters,
  metrics: string[],
  enabled = true,
  includePercentiles = true,
) {
  return useQuery<MatrixResponse, Error>({
    queryKey: ['player-cohort', filters, metrics, includePercentiles],
    queryFn: () => fetchPlayerCohort(filters, metrics, includePercentiles),
    staleTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
    enabled,
  })
}

interface StatMatrixQueryOptions {
  enabled?: boolean
  sorting?: SortingState
  rateMode?: MatrixRateMode
  page?: number
  pageSize?: number
  includeScopePercentiles?: boolean
}

export function useStatMatrix(filters: MatrixFilters, options: StatMatrixQueryOptions = {}) {
  const isGk = filters.position_group === 'GK'
  const sorting = options.sorting ?? [{ id: 'canonical_player_name', desc: false }]
  const primarySort = sorting[0]
  const sort = primarySort ? `${primarySort.desc ? '-' : ''}${primarySort.id}` : 'canonical_player_name'
  const request = {
    ...filters,
    sort,
    rate_mode: options.rateMode ?? 'per90',
    page: options.page ?? 1,
    page_size: options.pageSize ?? 200,
  }
  const includeScopePercentiles = options.includeScopePercentiles !== false
  return useQuery<MatrixResponse, Error>({
    queryKey: ['stat-matrix', isGk ? 'gk' : 'outfield', request],
    queryFn: () =>
      isGk
        ? fetchGkStatMatrix(request, includeScopePercentiles ? 'meta,scope_percentiles' : 'meta')
        : fetchStatMatrix(request, includeScopePercentiles ? 'meta,scope_percentiles' : 'meta'),
    staleTime: 10 * 60 * 1000,
    placeholderData: keepPreviousData,
    enabled: options.enabled ?? true,
  })
}
