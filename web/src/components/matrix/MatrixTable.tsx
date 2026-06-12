import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode, type RefObject } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useVirtualizer } from '@tanstack/react-virtual'
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type ColumnDef,
} from '@tanstack/react-table'
import { ChevronUp, ChevronDown, ChevronsUpDown } from 'lucide-react'
import { cn } from '../../lib/utils'
import { formatValue } from '../../lib/format'
import {
  getHeatmapStyle,
  getMinutesHeatRangeFromPlayers,
  minutesHeatPercentileFromRange,
} from '../../lib/heatmap'
import { getTeamLogoPath } from '../../lib/teamLogos'
import {
  COLUMN_GROUPS,
  STAT_CELL_PX,
  type ColDef,
  type ColGroupDef,
  type ColumnUnit,
} from '../../lib/columns'
import { COLUMN_GROUPS_GK } from '../../lib/gkColumns'
import {
  buildGkCohortPercentileMaps,
  getGkSortValue,
  headerTooltipGkMetricKey,
  resolveGkMatrixMetric,
} from '../../lib/gkMatrixRateMode'
import {
  buildCohortPercentileMaps,
  headerTooltipMetricKey,
  type MatrixRateMode,
  type ResolvedMatrixMetric,
  resolveMatrixMetric,
} from '../../lib/matrixRateMode'
import { getGroupHeaderTooltip, getStatHeaderTooltip } from '../../lib/statTooltips'
import { logMatrixPerfPhases } from '../../lib/perfDebug'
import { playerNameTitle, shortPlayerName } from '../../lib/entityLabels'
import { MatrixDisplayContext, useMatrixDisplay, type MatrixVariant } from './MatrixDisplayContext'
import { useMatrixHeaderTooltip } from './MatrixHeaderTooltipPortal'
import type { PlayerRow, PositionGroup } from '../../types/api'

const POSITION_COLORS: Record<PositionGroup, string> = {
  FWD: '#F05A28',
  MID: '#4A9EF5',
  DEF: '#1FD17C',
  GK: '#A855F7',
  UNK: '#4E5878',
}

/** Sum of thead row heights in pixels (`group` + `leaf`). */
const TABLE_HEADER_TOTAL_PX = 28 + 34

/**
 * Applied to the sorted column's leaf header and every cell in that column.
 * Paints a thin electric line just inside the left and right edges so the
 * column reads as an "active scanline" while the data flows down it.
 * `inset` keeps the lines within each cell so the heatmap fill and sticky
 * column backgrounds still render underneath.
 */
const SORTED_COL_STYLE: CSSProperties = {
  boxShadow:
    'inset 1px 0 0 rgba(74,158,245,0.35), inset -1px 0 0 rgba(74,158,245,0.35)',
}

const teamAcronym = (name: string | null | undefined): string =>
  (name ?? '').replace(/[^a-zA-Z0-9]/g, '').slice(0, 3).toUpperCase() || '---'

/**
 * The row-hover "target lock" decoration: two L-brackets at one side of a
 * row. We mount the `left` variant in the first (sticky) cell — which is
 * always on screen — and the `right` variant in the last cell. Opacity is
 * driven by `.group-hover` on the parent `<tr>`, so both sides light up in
 * sync as the pointer enters any cell in the row.
 */
function TargetBrackets({ side }: { side: 'left' | 'right' }) {
  const horiz = side === 'left' ? 'left-0' : 'right-0'
  const borderHoriz = side === 'left' ? 'border-l' : 'border-r'
  return (
    <>
      <span
        aria-hidden
        className={cn(
          'pointer-events-none absolute top-0 size-1.5 border-t border-electric opacity-0 group-hover:opacity-100 transition-opacity',
          horiz,
          borderHoriz,
        )}
      />
      <span
        aria-hidden
        className={cn(
          'pointer-events-none absolute bottom-0 size-1.5 border-b border-electric opacity-0 group-hover:opacity-100 transition-opacity',
          horiz,
          borderHoriz,
        )}
      />
    </>
  )
}

const helper = createColumnHelper<PlayerRow>()
type SortValue = number | string | null
const MATRIX_SORT_COLLATOR = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: 'base',
})

function getSortValue(
  row: PlayerRow,
  columnId: string,
  rateMode: MatrixRateMode,
  variant: MatrixVariant,
): SortValue {
  if (variant === 'gk') return getGkSortValue(row, columnId, rateMode)
  switch (columnId) {
    case 'canonical_player_name':
      return row.canonical_player_name
    case 'canonical_team_name':
      return row.canonical_team_name ?? ''
    case 'minutes':
      return row.minutes
    default:
      break
  }
  return resolveMatrixMetric(row, columnId, rateMode).value
}

function compareSortValues(a: SortValue, b: SortValue): number {
  if (typeof a === 'string' && typeof b === 'string') {
    return MATRIX_SORT_COLLATOR.compare(a, b)
  }
  return Number(a) - Number(b)
}

function MatrixGroupHeaderTitle({
  columnId,
  title,
  onEnterTip,
  onLeaveTip,
}: {
  columnId: string
  title: ReactNode
  onEnterTip: (kind: 'group' | 'leaf', id: string, el: HTMLElement) => void
  onLeaveTip: () => void
}) {
  const gTip = getGroupHeaderTooltip(columnId)
  const label = (
    <span className="text-center text-[9px] font-bold tracking-[0.14em] uppercase text-electric/60">
      {title}
    </span>
  )
  if (!gTip) return label
  return (
    <span
      className="cursor-help border-b border-dotted border-electric/35"
      onPointerEnter={e => onEnterTip('group', columnId, e.currentTarget)}
      onPointerLeave={onLeaveTip}
    >
      {label}
    </span>
  )
}

function MatrixLeafHeaderInner({
  columnId,
  sorted,
  isSortable,
  isPlayerCol,
  label,
  onEnterTip,
  onLeaveTip,
}: {
  columnId: string
  sorted: false | 'asc' | 'desc'
  isSortable: boolean
  isPlayerCol: boolean
  label: ReactNode
  onEnterTip: (kind: 'group' | 'leaf', id: string, el: HTMLElement) => void
  onLeaveTip: () => void
}) {
  const { rateMode, matrixVariant } = useMatrixDisplay()
  const tipKey =
    matrixVariant === 'gk'
      ? headerTooltipGkMetricKey(columnId, rateMode)
      : headerTooltipMetricKey(columnId, rateMode)
  const tip = getStatHeaderTooltip(tipKey)
  const title = (
    <span
      className={cn(
        'text-[10px] font-medium tracking-wide',
        sorted ? 'text-electric' : 'text-ink-muted',
      )}
    >
      {label}
    </span>
  )
  const sortIcon = isSortable ? (
    <span className="text-ink-muted/50 shrink-0">
      {sorted === 'asc' ? (
        <ChevronUp size={9} className="text-electric" />
      ) : sorted === 'desc' ? (
        <ChevronDown size={9} className="text-electric" />
      ) : (
        <ChevronsUpDown size={9} />
      )}
    </span>
  ) : null

  return (
    <div
      className={cn(
        'flex items-center gap-1',
        tip && 'cursor-help',
        isPlayerCol ? 'px-4 justify-start' : 'px-1 justify-center',
      )}
      onPointerEnter={tip ? e => onEnterTip('leaf', columnId, e.currentTarget) : undefined}
      onPointerLeave={tip ? onLeaveTip : undefined}
    >
      {title}
      {sortIcon}
    </div>
  )
}

// Shared shell for numeric cells. Centered value, optional heatmap fill, and the value color flips to black when a background is painted so it stays
// readable against the bright heatmap palette.
function StatCellBody({
  hStyle,
  children,
}: {
  hStyle: CSSProperties
  children: ReactNode
}) {
  return (
    <div
      className="flex items-center justify-center w-full h-full text-[12px] font-normal tabular-nums"
      style={hStyle}
    >
      <span
        style={
          !hStyle.backgroundColor
            ? { color: 'rgba(220,225,245,0.9)' }
            : { color: '#000000' }
        }
      >
        {children}
      </span>
    </div>
  )
}

function MinutesMatrixCell({ minutes }: { minutes: number }) {
  const { heatmapEnabled, minutesRange } = useMatrixDisplay()
  const percentile = minutesHeatPercentileFromRange(minutes, minutesRange)
  const hStyle = getHeatmapStyle(percentile, heatmapEnabled)
  return <StatCellBody hStyle={hStyle}>{formatValue(minutes, 'integer')}</StatCellBody>
}

function MetricMatrixCell({
  unit,
  value,
  percentilesEligible,
  percentile,
}: {
  unit: ColumnUnit
  value: number | null
  percentilesEligible: boolean
  percentile: number | null | undefined
}) {
  const { heatmapEnabled } = useMatrixDisplay()
  const p = percentilesEligible ? (percentile ?? null) : null
  const hStyle = getHeatmapStyle(p, heatmapEnabled)
  return <StatCellBody hStyle={hStyle}>{formatValue(value, unit)}</StatCellBody>
}

function buildTableColumns(
  columnGroups: ColGroupDef[],
  visibleCols: Record<string, boolean>,
  rateMode: MatrixRateMode,
  cohortMaps: Map<string, Map<number, number>>,
  resolveMetricFn: (row: PlayerRow, columnId: string, rateMode: MatrixRateMode) => ResolvedMatrixMetric,
): ColumnDef<PlayerRow, unknown>[] {
  return columnGroups.flatMap(group => {
    const visibleGroupCols = group.cols.filter(c => visibleCols[c.id])
    if (!visibleGroupCols.length) return []
    return [{
      id: `group_${group.id}`,
      header: group.label.toUpperCase(),
      columns: visibleGroupCols.map((col): ColumnDef<PlayerRow, unknown> => {
        if (col.isMeta) return buildMetaColumn(col)
        return buildMetricColumn(col, rateMode, cohortMaps, resolveMetricFn)
      }),
    }]
  })
}

// ── Meta columns

function buildMetaColumn(col: ColDef): ColumnDef<PlayerRow, unknown> {
  switch (col.id) {
    case 'canonical_player_name':
      return helper.accessor('canonical_player_name', {
        id: col.id,
        header: col.label,
        size: col.width,
        enableSorting: true,
        meta: { sticky: true },
        cell: info => {
          const row = info.row.original
          const pos = row.position_group
          const team = row.canonical_team_name ?? ''
          const name = info.getValue() as string
          return (
            <div
              className="flex flex-col justify-center px-3 h-full"
              style={{ minHeight: 'var(--matrix-row-h)', gap: 2 }}
            >
              <span className="text-[12px] font-normal text-ink leading-none truncate" title={playerNameTitle(name)}>
                {shortPlayerName(name)}
              </span>
              <span className="text-[10px] font-normal leading-none truncate" style={{ color: 'rgba(138,149,184,0.7)' }}>
                <span style={{ color: POSITION_COLORS[pos] }}>{pos}</span>
                {' · '}
                {team}
              </span>
            </div>
          )
        },
      }) as ColumnDef<PlayerRow, unknown>

    case 'canonical_team_name':
      return helper.accessor('canonical_team_name', {
        id: col.id,
        header: col.label,
        size: col.width,
        enableSorting: true,
        sortingFn: 'alphanumeric',
        cell: info => {
          const row = info.row.original
          const name = info.getValue() as string | null
          const tid = row.canonical_team_id
          const logo = getTeamLogoPath(tid, name)
          const inner =
            logo != null ? (
              <img
                src={logo}
                alt={name ?? ''}
                title={name ?? ''}
                style={{ width: 30, height: 30, objectFit: 'contain' }}
              />
            ) : (
              <span
                className="flex h-[30px] w-[30px] items-center justify-center text-[10px] font-bold text-ink-muted"
                title={name ?? undefined}
              >
                {teamAcronym(name)}
              </span>
            )
          return (
            <div className="flex items-center justify-center w-full h-full">
              {tid != null && name ? (
                <Link
                  to={`/team/${tid}?competition=${encodeURIComponent(row.competition_code)}&season=${encodeURIComponent(row.season_label)}`}
                  className="flex items-center justify-center rounded-sm ring-offset-2 ring-offset-mat hover:ring-1 hover:ring-electric/50"
                  aria-label={`Open ${name} team profile`}
                  onClick={e => e.stopPropagation()}
                >
                  {inner}
                </Link>
              ) : (
                inner
              )}
            </div>
          )
        },
      }) as ColumnDef<PlayerRow, unknown>

    case 'minutes':
      return helper.accessor('minutes', {
        id: col.id,
        header: col.label,
        size: col.width,
        enableSorting: true,
        sortDescFirst: true,
        cell: info => <MinutesMatrixCell minutes={info.getValue() as number} />,
      }) as ColumnDef<PlayerRow, unknown>

    case 'appearances':
      return helper.accessor(
        row => row.appearances ?? null,
        {
          id: col.id,
          header: col.label,
          size: col.width,
          enableSorting: true,
          sortDescFirst: true,
          cell: info => (
            <div className="flex items-center justify-center w-full h-full text-[12px] font-normal tabular-nums text-ink">
              {formatValue(info.getValue() as number | null, 'integer')}
            </div>
          ),
        },
      ) as ColumnDef<PlayerRow, unknown>

    default:
      return helper.display({ id: col.id, header: col.label, size: col.width }) as ColumnDef<PlayerRow, unknown>
  }
}

// Metric columns

function buildMetricColumn(
  col: ColDef,
  rateMode: MatrixRateMode,
  cohortMaps: Map<string, Map<number, number>>,
  resolveMetricFn: (row: PlayerRow, columnId: string, rateMode: MatrixRateMode) => ResolvedMatrixMetric,
): ColumnDef<PlayerRow, unknown> {
  return helper.accessor(
    row => resolveMetricFn(row, col.id, rateMode).value,
    {
      id: col.id,
      header: col.label,
      size: col.width,
      enableSorting: true,
      sortingFn: 'basic',
      sortDescFirst: true,
      cell: info => {
        const row = info.row.original
        const resolved = resolveMetricFn(row, col.id, rateMode)
        let percentile: number | null = null
        if (row.eligibility.percentiles_eligible) {
          if (resolved.useCohortPercentile) {
            const p = cohortMaps.get(col.id)?.get(row.canonical_player_id)
            percentile = p != null && !Number.isNaN(p) ? p : null
          } else if (resolved.percentileKey) {
            percentile = row.percentiles[resolved.percentileKey] ?? null
          }
        }
        return (
          <MetricMatrixCell
            unit={resolved.formatUnit}
            value={resolved.value}
            percentilesEligible={row.eligibility.percentiles_eligible}
            percentile={percentile}
          />
        )
      },
    },
  ) as ColumnDef<PlayerRow, unknown>
}

// Table time

interface MatrixTableProps {
  players: PlayerRow[]
  visibleCols: Record<string, boolean>
  columnGroups?: ColGroupDef[]
  heatmapEnabled: boolean
  rateMode: MatrixRateMode
  sorting: SortingState
  onSortingChange: (sorting: SortingState) => void
  /** Vertical scroll container (StatMatrix main pane) — hides header tooltip on scroll. */
  scrollParentRef?: RefObject<HTMLDivElement | null>
  /** Outfield stat matrix vs goalkeeper-only columns and metrics. */
  variant?: MatrixVariant
}

export function MatrixTable({
  players,
  visibleCols,
  columnGroups: columnGroupsOverride,
  heatmapEnabled,
  rateMode,
  sorting,
  onSortingChange,
  scrollParentRef,
  variant = 'outfield',
}: MatrixTableProps) {
  const navigate = useNavigate()
  const sortInteractionStartRef = useRef<number | null>(null)

  const { portal: headerTipPortal, show: showHeaderTip, scheduleHide: scheduleHeaderTipHide, hide: hideHeaderTip } =
    useMatrixHeaderTooltip()

  useEffect(() => {
    const el = scrollParentRef?.current
    if (!el) return
    const onScroll = () => hideHeaderTip()
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [scrollParentRef, hideHeaderTip])

  const minutesRange = useMemo(() => getMinutesHeatRangeFromPlayers(players), [players])

  const rawColumnGroups = columnGroupsOverride ?? (variant === 'gk' ? COLUMN_GROUPS_GK : COLUMN_GROUPS)

  // Measure the scroll container so the GK matrix (far fewer columns) can stretch to fill the viewport while keeping every cell a square. Outfield already overflows, so we leave it alone.
  // I kinda hate this idk what to do tho
  const [containerWidth, setContainerWidth] = useState(0)
  useLayoutEffect(() => {
    const el = scrollParentRef?.current
    if (!el) return
    const measure = () => setContainerWidth(el.clientWidth)
    measure()
    const ro = new ResizeObserver(measure)
    ro.observe(el)
    return () => ro.disconnect()
  }, [scrollParentRef])

  const visibleFlexColumnCount = useMemo(
    () =>
      rawColumnGroups.reduce(
        (count, group) =>
          count + group.cols.filter(c => c.id !== 'canonical_player_name' && visibleCols[c.id]).length,
        0,
      ),
    [rawColumnGroups, visibleCols],
  )

  const cellSize = useMemo(() => {
    if (variant !== 'gk' || !containerWidth || !visibleFlexColumnCount) return STAT_CELL_PX
    const playerColWidth =
      rawColumnGroups
        .flatMap(g => g.cols)
        .find(c => c.id === 'canonical_player_name')?.width ?? 152
    const fit = Math.floor((containerWidth - playerColWidth) / visibleFlexColumnCount)
    return Math.max(STAT_CELL_PX, fit)
  }, [variant, containerWidth, visibleFlexColumnCount, rawColumnGroups])

  // Stretch every non-Player column to `cellSize` on the GK matrix. Outfield keeps its original
  // widths so it still overflows horizontally where appropriate.
  const columnGroups = useMemo(() => {
    if (variant !== 'gk' || cellSize === STAT_CELL_PX) return rawColumnGroups
    return rawColumnGroups.map(group => ({
      ...group,
      cols: group.cols.map(col =>
        col.id === 'canonical_player_name' ? col : { ...col, width: cellSize },
      ),
    }))
  }, [rawColumnGroups, variant, cellSize])

  const resolveMetricFn = variant === 'gk' ? resolveGkMatrixMetric : resolveMatrixMetric

  const cohortMaps = useMemo(
    () =>
      variant === 'gk'
        ? buildGkCohortPercentileMaps(players, rateMode)
        : buildCohortPercentileMaps(players, rateMode),
    [variant, players, rateMode],
  )

  const displayValue = useMemo(
    () => ({ heatmapEnabled, minutesRange, rateMode, matrixVariant: variant }),
    [heatmapEnabled, minutesRange, rateMode, variant],
  )

  const columns = useMemo(
    () =>
      buildTableColumns(columnGroups, visibleCols, rateMode, cohortMaps, resolveMetricFn),
    [columnGroups, visibleCols, rateMode, cohortMaps, resolveMetricFn],
  )

  const sortedPlayers = useMemo(() => {
    const [primarySort] = sorting
    if (!primarySort) return players

    const sorted = players
      .map(player => ({
        player,
        sortValue: getSortValue(player, primarySort.id, rateMode, variant),
      }))
      .sort((a, b) => {
      const aValue = a.sortValue
      const bValue = b.sortValue
      if (aValue == null && bValue == null) return 0
      if (aValue == null) return 1
      if (bValue == null) return -1
      const cmp = compareSortValues(aValue, bValue)
      return primarySort.desc ? -cmp : cmp
    })
      .map(entry => entry.player)

    return sorted
  }, [players, sorting, rateMode, variant])

  const table = useReactTable({
    data: sortedPlayers,
    columns,
    state: { sorting },
    manualSorting: true,
    getRowId: row => String(row.canonical_player_id),
    onSortingChange: updater => {
      sortInteractionStartRef.current = performance.now()
      const nextSorting = typeof updater === 'function' ? updater(sorting) : updater
      onSortingChange(nextSorting)
    },
    getCoreRowModel: getCoreRowModel(),
  })
  const rowModel = table.getRowModel()

  const virtualizer = useVirtualizer({
    count: sortedPlayers.length,
    getScrollElement: () => scrollParentRef?.current ?? null,
    estimateSize: () => cellSize,
    overscan: 10,
    paddingStart: TABLE_HEADER_TOTAL_PX,
    getItemKey: index => String(sortedPlayers[index]?.canonical_player_id ?? index),
  })

  // Invalidate the virtualizer's cached row metrics when the dynamic cell size changes so the total scroll height and row offsets recompute from the new `estimateSize`.
  useLayoutEffect(() => {
    virtualizer.measure()
  }, [cellSize, virtualizer])

  useLayoutEffect(() => {
    if (sortInteractionStartRef.current === null) return
    const t0 = sortInteractionStartRef.current
    sortInteractionStartRef.current = null
    logMatrixPerfPhases('sort → first layout', t0)
  }, [sorting, sortedPlayers])

  const [groupRow, leafRow] = table.getHeaderGroups()

  const leafCols = table.getVisibleLeafColumns()

  const groupHeaderBorderLeft = (() => {
    if (!groupRow) return new Map<string, boolean>()
    const real = groupRow.headers.filter(h => !h.isPlaceholder && h.colSpan > 0)
    return new Map(real.map((h, i) => [h.id, i > 0]))
  })()

  const sortedColumnId = sorting[0]?.id ?? null

  const tableWidthPx = leafCols.reduce((s, c) => s + c.getSize(), 0)

  return (
    <MatrixDisplayContext.Provider value={displayValue}>
      <div ref={scrollParentRef} className="flex-1 min-h-0 overflow-auto">
        {headerTipPortal}
        <div className="overflow-x-auto min-h-0" onScroll={hideHeaderTip}>
          {sortedPlayers.length === 0 ? (
            <div className="flex items-center justify-center py-24 text-ink-muted text-[13px]">
              No players match the current filters.
            </div>
          ) : (
            <div
              style={{
                height: `${virtualizer.getTotalSize()}px`,
                position: 'relative',
                // Exposed so module-scoped cell renderers (Player, metric cells) can match the
                // dynamic row height without threading a prop through every builder.
                ['--matrix-row-h' as string]: `${cellSize}px`,
              }}
            >
              <table
                style={{
                  borderCollapse: 'collapse',
                  tableLayout: 'fixed',
                  width: tableWidthPx,
                }}
              >
                <colgroup>
                  {leafCols.map(col => (
                    <col key={col.id} style={{ width: col.getSize() }} />
                  ))}
                </colgroup>
                <thead>
                  {groupRow && (
                    <tr style={{ height: 28 }}>
                      {groupRow.headers.map(header => {
                        const isSticky = header.column.columnDef.meta?.sticky
                        const showSectionLine = groupHeaderBorderLeft.get(header.id)
                        return (
                          <th
                            key={header.id}
                            colSpan={header.colSpan}
                            style={{
                              height: 28,
                              ...(isSticky ? { position: 'sticky', left: 0, zIndex: 20 } : {}),
                            }}
                            className={cn(
                              'bg-raised border-b border-line align-middle',
                              showSectionLine && 'border-l-2 border-l-line-bright',
                            )}
                          >
                            {!header.isPlaceholder && header.colSpan > 0 && (
                              <div className="flex h-[28px] w-full items-center justify-center px-2">
                                <MatrixGroupHeaderTitle
                                  columnId={header.column.id}
                                  title={flexRender(header.column.columnDef.header, header.getContext())}
                                  onEnterTip={showHeaderTip}
                                  onLeaveTip={scheduleHeaderTipHide}
                                />
                              </div>
                            )}
                          </th>
                        )
                      })}
                    </tr>
                  )}

                  {leafRow && (
                    <tr style={{ height: 34 }}>
                      {leafRow.headers.map(header => {
                        const isSticky = header.column.columnDef.meta?.sticky
                        const sorted = header.column.getIsSorted()
                        const isSortable = header.column.getCanSort()
                        const isPlayerCol = header.column.id === 'canonical_player_name'
                        const isSortedCol = header.column.id === sortedColumnId
                        return (
                          <th
                            key={header.id}
                            onClick={isSortable ? header.column.getToggleSortingHandler() : undefined}
                            style={{
                              width: header.getSize(),
                              minWidth: header.getSize(),
                              height: 34,
                              ...(isSticky ? { position: 'sticky', left: 0, zIndex: 20 } : {}),
                              ...(isSortedCol ? SORTED_COL_STYLE : {}),
                            }}
                            className={cn(
                              'bg-panel border-b-2 border-line select-none whitespace-nowrap',
                              isSortable && 'cursor-pointer hover:bg-raised transition-colors',
                            )}
                          >
                            <MatrixLeafHeaderInner
                              columnId={header.column.id}
                              sorted={sorted}
                              isSortable={isSortable}
                              isPlayerCol={isPlayerCol}
                              label={flexRender(header.column.columnDef.header, header.getContext())}
                              onEnterTip={showHeaderTip}
                              onLeaveTip={scheduleHeaderTipHide}
                            />
                          </th>
                        )
                      })}
                    </tr>
                  )}
                </thead>

                <tbody>
                  {virtualizer.getVirtualItems().map((virtualRow, virtualIndex) => {
                    const row = rowModel.rows[virtualRow.index]
                    if (!row) return null
                    const rowIdx = virtualRow.index
                    return (
                      <tr
                        key={row.id}
                        onClick={() =>
                          navigate(
                            `/player/${row.original.canonical_player_id}?competition=${encodeURIComponent(row.original.competition_code)}&season=${encodeURIComponent(row.original.season_label)}`,
                          )
                        }
                        className="group cursor-pointer"
                        style={{
                          height: `${virtualRow.size}px`,
                          // `paddingStart` aligns virtual scroll math with thead height; tbody rows already start below thead,
                          // so subtract that offset (TanStack table virtual example uses 0 padding — we reuse the same transform).
                          transform: `translateY(${
                            virtualRow.start -
                            TABLE_HEADER_TOTAL_PX -
                            virtualIndex * virtualRow.size
                          }px)`,
                        }}
                      >
                        {row.getVisibleCells().map((cell, cellIdx, cellArr) => {
                          const isSticky = cell.column.columnDef.meta?.sticky
                          const isFirst = cellIdx === 0
                          const isLast = cellIdx === cellArr.length - 1
                          const isSortedCol = cell.column.id === sortedColumnId
                          const baseBg = rowIdx % 2 === 0 ? 'var(--color-panel)' : 'var(--color-mat)'
                          return (
                            <td
                              key={cell.id}
                              style={{
                                width: cell.column.getSize(),
                                minWidth: cell.column.getSize(),
                                height: cellSize,
                                padding: 0,
                                border: '1px solid var(--color-line)',
                                position: isSticky ? 'sticky' : 'relative',
                                ...(isSticky
                                  ? {
                                      left: 0,
                                      zIndex: 10,
                                      backgroundColor: baseBg,
                                    }
                                  : {}),
                                ...(isSortedCol ? SORTED_COL_STYLE : {}),
                              }}
                              className="group-hover:brightness-110"
                            >
                              <div className="w-full h-full" style={{ height: 'var(--matrix-row-h)' }}>
                                {flexRender(cell.column.columnDef.cell, cell.getContext())}
                              </div>
                              {isFirst && <TargetBrackets side="left" />}
                              {isLast && <TargetBrackets side="right" />}
                            </td>
                          )
                        })}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </MatrixDisplayContext.Provider>
  )
}
