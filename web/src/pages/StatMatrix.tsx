import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { SortingState } from '@tanstack/react-table'
import { AlertCircle, BarChart3, Loader2, X } from 'lucide-react'
import { FilterBar } from '../components/matrix/FilterBar'
import { MatrixTable } from '../components/matrix/MatrixTable'
import { HudFrame } from '../components/hud/Hud'
import { cn } from '../lib/utils'
import { useStatMatrix, DEFAULT_FILTERS, applyClientFilters } from '../hooks/useStatMatrix'
import { COLUMN_GROUPS, type ColDef, type ColGroupDef } from '../lib/columns'
import { COLUMN_GROUPS_GK, buildMatrixVisibilityAll } from '../lib/gkColumns'
import { logMatrixPerfPhases } from '../lib/perfDebug'
import { buildMatrixCreateChartsPath, buildMatrixMetricCreateChartsPath } from '../lib/createChartsUrl'
import {
  starterViewsForVariant,
  visibilityForStarterView,
  type MatrixStarterView,
  type MatrixStarterVariant,
} from '../lib/matrixStarterViews'
import type { MatrixRateMode } from '../lib/matrixRateMode'
import type { MatrixFilters, MetricAvailability, PlayerRow } from '../types/api'
import { useScope } from '../context/ScopeContext'

const EMPTY_PLAYER_ROWS: PlayerRow[] = []
const DEFAULT_MATRIX_SORT: SortingState = [{ id: 'minutes', desc: true }]

interface MatrixChartCtaState {
  key: string
  metricId: string
  metricLabel: string
  window: 'top' | 'bottom'
}

function listIncludes(value: unknown, key: string): boolean {
  return Array.isArray(value) && value.includes(key)
}

function metricAvailable(
  availability: MetricAvailability | undefined,
  key: string,
): boolean {
  if (!availability) return true
  if (listIncludes(availability.unavailable_metrics, key)) return false
  if (Array.isArray(availability.ui_available_metrics)) {
    return availability.ui_available_metrics.includes(key)
  }
  return true
}

function columnAvailable(
  col: ColDef,
  availability: MetricAvailability | undefined,
  position: MatrixFilters['position_group'],
): boolean {
  void position
  if (col.isMeta) return true
  return metricAvailable(availability, col.id)
}

function filterAvailableColumnGroups(
  groups: ColGroupDef[],
  availability: MetricAvailability | undefined,
  position: MatrixFilters['position_group'],
): ColGroupDef[] {
  return groups.flatMap(group => {
    const next = {
      ...group,
      cols: group.cols.filter(col => columnAvailable(col, availability, position)),
    }
    return next.cols.length > 0 ? [next] : []
  })
}

export function StatMatrix() {
  const matrixScrollParentRef = useRef<HTMLDivElement>(null)
  const filterInteractionStartRef = useRef<number | null>(null)
  const { scope, metricAvailability } = useScope()
  const [filters, setFilters] = useState<MatrixFilters>(() => ({
    ...DEFAULT_FILTERS,
    competition: scope.competition,
    season: scope.season,
  }))
  const [heatmapEnabled, setHeatmapEnabled] = useState(true)
  const [rateMode, setRateMode] = useState<MatrixRateMode>('per90')
  const [visibleCols, setVisibleCols] = useState<Record<string, boolean>>(buildMatrixVisibilityAll)
  const [sorting, setSorting] = useState<SortingState>(DEFAULT_MATRIX_SORT)
  const [activeStarterViewId, setActiveStarterViewId] = useState<string | null>(null)
  const [chartCta, setChartCta] = useState<MatrixChartCtaState | null>(null)
  const [dismissedChartCtaKey, setDismissedChartCtaKey] = useState<string | null>(null)
  const [closingChartCtaKey, setClosingChartCtaKey] = useState<string | null>(null)

  useEffect(() => {
    setFilters(prev => {
      if (prev.competition === scope.competition && prev.season === scope.season) return prev
      return {
        ...prev,
        competition: scope.competition,
        season: scope.season,
        teams: undefined,
      }
    })
  }, [scope.competition, scope.season])

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
    const names = new Set<string>()
    for (const player of allPlayers) {
      if (player.canonical_team_name) names.add(player.canonical_team_name)
    }
    return [...names].toSorted()
  }, [allPlayers])

  const activeColumnGroups = useMemo(
    () =>
      filters.position_group === 'GK'
        ? COLUMN_GROUPS_GK
        : filterAvailableColumnGroups(COLUMN_GROUPS, metricAvailability, filters.position_group),
    [filters.position_group, metricAvailability],
  )

  const effectiveVisibleCols = visibleCols
  const matrixVariant: MatrixStarterVariant = filters.position_group === 'GK' ? 'gk' : 'outfield'

  const columnsById = useMemo(
    () =>
      new Map(
        activeColumnGroups.flatMap(group => group.cols.map(col => [col.id, col] as const)),
      ),
    [activeColumnGroups],
  )

  const metricColumnsById = useMemo(
    () =>
      new Map(
        activeColumnGroups.flatMap(group =>
          group.cols.flatMap(col => (col.isMeta ? [] : [[col.id, col] as const])),
        ),
      ),
    [activeColumnGroups],
  )

  const starterViews = useMemo(
    () =>
      starterViewsForVariant(matrixVariant)
        .map(view => ({
          ...view,
          columnIds: view.columnIds.filter(columnId => metricColumnsById.has(columnId)),
        }))
        .filter(view => metricColumnsById.has(view.sortId) && view.columnIds.length > 0),
    [matrixVariant, metricColumnsById],
  )

  const effectiveSorting = useMemo<SortingState>(() => {
    const sortedColumnId = sorting[0]?.id
    return !sortedColumnId || columnsById.has(sortedColumnId) ? sorting : DEFAULT_MATRIX_SORT
  }, [columnsById, sorting])

  const effectiveActiveStarterViewId =
    activeStarterViewId && starterViews.some(view => view.id === activeStarterViewId)
      ? activeStarterViewId
      : null

  const effectiveChartCta = chartCta && metricColumnsById.has(chartCta.metricId) ? chartCta : null

  useEffect(() => {
    if (!chartCta) return
    const key = chartCta.key
    const timeout = window.setTimeout(() => {
      setDismissedChartCtaKey(key)
      setClosingChartCtaKey(key)
      window.setTimeout(() => {
        setChartCta(current => (current?.key === key ? null : current))
        setClosingChartCtaKey(current => (current === key ? null : current))
      }, 240)
    }, 8000)
    return () => window.clearTimeout(timeout)
  }, [chartCta])

  const createChartHref = useMemo(
    () => buildMatrixCreateChartsPath(filters, rateMode),
    [filters, rateMode],
  )
  const chartCtaHref = useMemo(
    () =>
      effectiveChartCta
        ? buildMatrixMetricCreateChartsPath({
            filters,
            mode: rateMode,
            metric: effectiveChartCta.metricId,
            barWindow: effectiveChartCta.window,
          })
        : null,
    [effectiveChartCta, filters, rateMode],
  )

  function handleFiltersChange(partial: Partial<MatrixFilters>) {
    filterInteractionStartRef.current = performance.now()
    if (Object.hasOwn(partial, 'position_group')) {
      setSorting(DEFAULT_MATRIX_SORT)
      setActiveStarterViewId(null)
      setChartCta(null)
      setDismissedChartCtaKey(null)
      setClosingChartCtaKey(null)
    }
    setFilters(prev => ({ ...prev, ...partial }))
  }

  function handleColGroupToggle(groupId: string) {
    const group = activeColumnGroups.find(g => g.id === groupId)
    if (!group) return
    const allVisible = group.cols.every(c => visibleCols[c.id])
    setActiveStarterViewId(null)
    setVisibleCols(prev => ({
      ...prev,
      ...Object.fromEntries(group.cols.map(c => [c.id, !allVisible])),
    }))
  }

  function handleStarterViewApply(view: MatrixStarterView) {
    setVisibleCols(prev => ({
      ...prev,
      ...visibilityForStarterView(view, activeColumnGroups),
    }))
    setSorting([{ id: view.sortId, desc: view.sortDesc }])
    setActiveStarterViewId(view.id)
    setChartCta(null)
    setDismissedChartCtaKey(null)
    setClosingChartCtaKey(null)
  }

  function handleSortingChange(nextSorting: SortingState) {
    setSorting(nextSorting)
    setActiveStarterViewId(null)

    const primary = nextSorting[0]
    if (!primary) {
      setChartCta(null)
      return
    }

    const metricColumn = metricColumnsById.get(primary.id)
    if (!metricColumn) {
      setChartCta(null)
      return
    }

    const key = `${primary.id}:${primary.desc ? 'desc' : 'asc'}`
    if (key === dismissedChartCtaKey) {
      setChartCta(null)
      return
    }

    setChartCta({
      key,
      metricId: primary.id,
      metricLabel: metricColumn.label,
      window: primary.desc ? 'top' : 'bottom',
    })
    setClosingChartCtaKey(null)
  }

  function closeChartCta(key: string, dismissForSort: boolean) {
    if (dismissForSort) setDismissedChartCtaKey(key)
    setClosingChartCtaKey(key)
    window.setTimeout(() => {
      setChartCta(current => (current?.key === key ? null : current))
      setClosingChartCtaKey(current => (current === key ? null : current))
    }, 240)
  }

  function handleChartCtaDismiss() {
    if (chartCta) closeChartCta(chartCta.key, true)
  }

  return (
    <div className="flex h-[calc(100svh-132px)] flex-col lg:h-[calc(100svh-52px)]">
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
        createChartHref={createChartHref}
        starterViews={starterViews}
        activeStarterViewId={effectiveActiveStarterViewId}
        onStarterViewApply={handleStarterViewApply}
      />

      <div className="flex-1 min-h-0 flex flex-col">
        {isLoading && <LoadingState />}
        {isError && <ErrorState message={error?.message} />}
        {!isLoading && !isError && (
          <MatrixTable
            players={filteredPlayers}
            visibleCols={effectiveVisibleCols}
            columnGroups={activeColumnGroups}
            heatmapEnabled={heatmapEnabled}
            rateMode={rateMode}
            sorting={effectiveSorting}
            onSortingChange={handleSortingChange}
            scrollParentRef={matrixScrollParentRef}
            variant={matrixVariant}
          />
        )}
      </div>

      {effectiveChartCta && chartCtaHref && (
        <MatrixChartCta
          cta={effectiveChartCta}
          closing={closingChartCtaKey === effectiveChartCta.key}
          href={chartCtaHref}
          onDismiss={handleChartCtaDismiss}
        />
      )}
    </div>
  )
}

function MatrixChartCta({
  cta,
  closing,
  href,
  onDismiss,
}: {
  cta: MatrixChartCtaState
  closing: boolean
  href: string
  onDismiss: () => void
}) {
  const directionLabel = cta.window === 'top' ? 'Top' : 'Bottom'

  return (
    <div
      aria-live="polite"
      className="pointer-events-none fixed inset-x-0 bottom-5 z-50 flex justify-center px-4 lg:bottom-7"
    >
      <HudFrame
        className={cn(
          'pointer-events-auto w-[min(560px,calc(100vw-2rem))] bg-panel/95 shadow-[0_18px_48px_-14px_rgba(74,158,245,0.65)]',
          closing ? 'matrix-cta-exit' : 'matrix-cta-enter',
        )}
        bodyClassName="p-3 lg:p-4"
        header={<span>Chart Current Sort</span>}
      >
        <div className="flex items-center gap-3 lg:gap-4">
          <div className="hidden size-10 shrink-0 items-center justify-center border border-electric/25 bg-electric/10 text-electric lg:flex">
            <BarChart3 size={18} />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold text-ink lg:text-[15px]">
              Chart {directionLabel} 12 by {cta.metricLabel}
            </p>
            <p className="mt-1 text-[10px] uppercase tracking-[0.18em] text-ink-dim">
              Uses current Matrix filters
            </p>
          </div>
          <Link
            to={href}
            className="flex shrink-0 items-center gap-1.5 border border-electric/40 bg-electric/10 px-2.5 py-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-electric transition-colors hover:bg-electric/20 lg:px-3 lg:py-2"
          >
            <BarChart3 size={13} />
            Create Chart
          </Link>
          <button
            type="button"
            aria-label="Dismiss chart suggestion"
            onClick={onDismiss}
            className="flex size-8 shrink-0 items-center justify-center border border-electric/15 text-ink-muted transition-colors hover:border-electric/35 hover:text-electric"
          >
            <X size={14} />
          </button>
        </div>
      </HudFrame>
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
