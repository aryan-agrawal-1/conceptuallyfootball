import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { fetchCompetitionSeasonsCatalog } from '../lib/api'
import type {
  CompetitionCatalogEntry,
  CompetitionSeasonOption,
  CompetitionSeasonsCatalogResponse,
  MetricAvailability,
} from '../types/api'

export interface Scope {
  competition: string
  season: string
}

export const PREFERRED_DEFAULT_SCOPE: Scope = {
  competition: 'ENG1',
  season: '2025-26',
}

interface ScopeContextValue {
  scope: Scope
  setScope: (scope: Scope) => void
  catalog: CompetitionSeasonsCatalogResponse | undefined
  competitions: CompetitionCatalogEntry[]
  seasonOptions: CompetitionSeasonOption[]
  currentCompetition: CompetitionCatalogEntry | undefined
  currentSeason: CompetitionSeasonOption | undefined
  metricAvailability: MetricAvailability | undefined
  scopeLabel: string
  isLoading: boolean
  isError: boolean
  buildScopedPath: (path: string, override?: Scope) => string
}

const ScopeContext = createContext<ScopeContextValue | null>(null)

function findDefaultScope(catalog: CompetitionSeasonsCatalogResponse | undefined): Scope {
  const preferred = catalog?.competitions
    .find(c => c.code === PREFERRED_DEFAULT_SCOPE.competition)
    ?.seasons.find(s => s.label === PREFERRED_DEFAULT_SCOPE.season)
  if (preferred) return PREFERRED_DEFAULT_SCOPE

  const firstCompetition = catalog?.competitions[0]
  const firstSeason = firstCompetition?.seasons[0]
  if (firstCompetition && firstSeason) {
    return { competition: firstCompetition.code, season: firstSeason.label }
  }
  return PREFERRED_DEFAULT_SCOPE
}

function findScopeInCatalog(
  catalog: CompetitionSeasonsCatalogResponse | undefined,
  competition: string | null,
  season: string | null,
): Scope | null {
  if (!catalog || !competition || !season) return null
  const comp = catalog.competitions.find(c => c.code === competition)
  if (!comp) return null
  return comp.seasons.some(s => s.label === season)
    ? { competition, season }
    : null
}

function withScopeParams(path: string, scope: Scope): string {
  const [pathname, rawSearch = ''] = path.split('?')
  const p = new URLSearchParams(rawSearch)
  p.set('competition', scope.competition)
  p.set('season', scope.season)
  return `${pathname}?${p.toString()}`
}

export function ScopeProvider({ children }: { children: ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams()
  const catalogQuery = useQuery({
    queryKey: ['competition-seasons-catalog'],
    queryFn: fetchCompetitionSeasonsCatalog,
    staleTime: 30 * 60 * 1000,
  })

  const catalog = catalogQuery.data
  const urlCompetition = searchParams.get('competition')
  const urlSeason = searchParams.get('season')
  const defaultScope = useMemo(() => findDefaultScope(catalog), [catalog])
  const scope = useMemo(
    () => findScopeInCatalog(catalog, urlCompetition, urlSeason) ?? defaultScope,
    [catalog, defaultScope, urlCompetition, urlSeason],
  )

  useEffect(() => {
    if (!catalog) return
    const valid = findScopeInCatalog(catalog, urlCompetition, urlSeason)
    if (valid) return
    setSearchParams(
      prev => {
        const p = new URLSearchParams(prev)
        p.set('competition', defaultScope.competition)
        p.set('season', defaultScope.season)
        return p
      },
      { replace: true },
    )
  }, [catalog, defaultScope.competition, defaultScope.season, setSearchParams, urlCompetition, urlSeason])

  const setScope = useCallback(
    (next: Scope) => {
      setSearchParams(
        prev => {
          const p = new URLSearchParams(prev)
          p.set('competition', next.competition)
          p.set('season', next.season)
          return p
        },
        { replace: false },
      )
    },
    [setSearchParams],
  )

  const currentCompetition = useMemo(
    () => catalog?.competitions.find(c => c.code === scope.competition),
    [catalog, scope.competition],
  )
  const seasonOptions = currentCompetition?.seasons ?? []
  const currentSeason = useMemo(
    () => seasonOptions.find(s => s.label === scope.season),
    [scope.season, seasonOptions],
  )

  const buildScopedPath = useCallback(
    (path: string, override?: Scope) => withScopeParams(path, override ?? scope),
    [scope],
  )

  const value = useMemo<ScopeContextValue>(
    () => ({
      scope,
      setScope,
      catalog,
      competitions: catalog?.competitions ?? [],
      seasonOptions,
      currentCompetition,
      currentSeason,
      metricAvailability: currentSeason?.metric_availability,
      scopeLabel: `${scope.competition} ${scope.season}`,
      isLoading: catalogQuery.isLoading,
      isError: catalogQuery.isError,
      buildScopedPath,
    }),
    [
      buildScopedPath,
      catalog,
      catalogQuery.isError,
      catalogQuery.isLoading,
      currentCompetition,
      currentSeason,
      scope,
      seasonOptions,
      setScope,
    ],
  )

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>
}

export function useScope() {
  const value = useContext(ScopeContext)
  if (!value) throw new Error('useScope must be used inside ScopeProvider')
  return value
}

export function scopeMatches(a: Scope, b: Scope) {
  return a.competition === b.competition && a.season === b.season
}
