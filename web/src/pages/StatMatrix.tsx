import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import { AlertCircle, Loader2 } from 'lucide-react'
import { FilterBar } from '../components/matrix/FilterBar'
import { MatrixTable } from '../components/matrix/MatrixTable'
import { HudFrame } from '../components/hud/Hud'
import { useStatMatrix, DEFAULT_FILTERS, applyClientFilters } from '../hooks/useStatMatrix'
import { COLUMN_GROUPS, SCORE_COLUMN_IDS, SCORE_GROUP_ID } from '../lib/columns'
import { COLUMN_GROUPS_GK, buildMatrixVisibilityAll } from '../lib/gkColumns'
import { logMatrixPerfPhases } from '../lib/perfDebug'
import { isLabPosition } from '../lib/regressionLabConfig'
import { buildRegressionLabHandoff } from '../lib/regressionLabUrl'
import type { MatrixRateMode } from '../lib/matrixRateMode'
import type { MatrixFilters, PlayerRow } from '../types/api'

const EMPTY_PLAYER_ROWS: PlayerRow[] = []

export function StatMatrix() {
  const matrixScrollParentRef = useRef<HTMLDivElement>(null)
  const filterInteractionStartRef = useRef<number | null>(null)
  const [filters, setFilters] = useState<MatrixFilters>(DEFAULT_FILTERS)
  const [heatmapEnabled, setHeatmapEnabled] = useState(true)
  const [rateMode, setRateMode] = useState<MatrixRateMode>('per90')
  const [visibleCols, setVisibleCols] = useState<Record<string, boolean>>(buildMatrixVisibilityAll)

  // Only competition + season determine what we fetch. Everything else is local.
  const { data, isLoading, isFetching, isError, error, isPlaceholderData } =
    useStatMatrix(filters)

  const allPlayers = data?.results ?? EMPTY_PLAYER_ROWS

  // Client-side: instant, no network
  const filteredPlayers = useMemo(
    () => applyClientFilters(allPlayers, filters),
    [allPlayers, filters],
  )

  useLayoutEffect(() => {
    if (filterInteractionStartRef.current === null) return
    const t0 = filterInteractionStartRef.current
    filterInteractionStartRef.current = null
    logMatrixPerfPhases('filter → first layout', t0)
  }, [filteredPlayers])

  // Derived from ALL players so the club list doesn't shrink when you filter by position/minutes
  const teams = useMemo(() => {
    const names = allPlayers
      .map(p => p.canonical_team_name)
      .filter((t): t is string => t !== null)
    return [...new Set(names)].sort()
  }, [allPlayers])

  const activeColumnGroups = filters.position_group === 'GK' ? COLUMN_GROUPS_GK : COLUMN_GROUPS

  // Hide score columns when no position is selected (cross-position percentiles are meaningless)
  const effectiveVisibleCols = useMemo(() => {
    if (filters.position_group === 'GK') return visibleCols
    if (filters.position_group) return visibleCols
    return {
      ...visibleCols,
      ...Object.fromEntries(SCORE_COLUMN_IDS.map(id => [id, false])),
    }
  }, [visibleCols, filters.position_group])

  const regressionLabHref = useMemo(() => {
    if (!filters.position_group || !isLabPosition(filters.position_group)) return null
    return buildRegressionLabHandoff(filters)
  }, [filters])

  function handleFiltersChange(partial: Partial<MatrixFilters>) {
    filterInteractionStartRef.current = performance.now()
    setFilters(prev => ({ ...prev, ...partial }))
  }

  function handleColGroupToggle(groupId: string) {
    if (!filters.position_group && groupId === SCORE_GROUP_ID) return
    const group = activeColumnGroups.find(g => g.id === groupId)
    if (!group) return
    const allVisible = group.cols.every(c => visibleCols[c.id])
    setVisibleCols(prev => ({
      ...prev,
      ...Object.fromEntries(group.cols.map(c => [c.id, !allVisible])),
    }))
  }

  return (
    <div className="flex flex-col h-[calc(100svh-52px)]">
      <FilterBar
        filters={filters}
        teams={teams}
        heatmapEnabled={heatmapEnabled}
        rateMode={rateMode}
        columnGroups={activeColumnGroups}
        visibleCols={effectiveVisibleCols}
        onFiltersChange={handleFiltersChange}
        onHeatmapToggle={() => setHeatmapEnabled(e => !e)}
        onRateModeChange={setRateMode}
        onColGroupToggle={handleColGroupToggle}
        playerCount={filteredPlayers.length}
        totalCount={allPlayers.length}
        refetching={isFetching && isPlaceholderData}
        regressionLabHref={regressionLabHref}
      />

      <div className="flex-1 min-h-0 flex flex-col">
        {isLoading && <LoadingState />}
        {isError && <ErrorState message={error?.message} />}
        {!isLoading && !isError && (
          <MatrixTable
            players={filteredPlayers}
            visibleCols={effectiveVisibleCols}
            heatmapEnabled={heatmapEnabled}
            rateMode={rateMode}
            scrollParentRef={matrixScrollParentRef}
            variant={filters.position_group === 'GK' ? 'gk' : 'outfield'}
          />
        )}
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center h-64 px-6">
      <HudFrame className="w-[min(360px,100%)]" header="Acquiring Signal">
        <div className="flex items-center gap-3 p-4">
          <Loader2 size={20} className="text-electric animate-spin" />
          <p className="text-[11px] text-electric/80 tracking-[0.2em] uppercase">
            Loading season data
          </p>
        </div>
      </HudFrame>
    </div>
  )
}

function ErrorState({ message }: { message?: string }) {
  return (
    <div className="flex items-center justify-center h-64 px-6">
      <HudFrame
        className="w-[min(440px,100%)] border-ember/40 shadow-[0_0_40px_-12px_rgba(239,68,68,0.35)]"
        header={
          <span className="text-ember">Signal Lost // Error</span>
        }
      >
        <div className="flex items-start gap-3 p-4">
          <AlertCircle size={20} className="text-ember shrink-0 mt-0.5" />
          <div>
            <p className="text-[12px] text-ink font-medium mb-1 tracking-wide">
              Failed to load data
            </p>
            <p className="text-[11px] text-ink-muted leading-relaxed">
              {message ??
                'Check the backend is running at localhost:8000 and the season/competition params are correct.'}
            </p>
          </div>
        </div>
      </HudFrame>
    </div>
  )
}
