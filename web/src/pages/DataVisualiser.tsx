import { useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { fetchTeamStatMatrix } from '../lib/api'
import { applyClientFilters, useStatMatrix } from '../hooks/useStatMatrix'
import {
  DEFAULT_BAR_COUNT,
  MAX_BAR_COUNT,
  MIN_BAR_COUNT,
  parseDataVisualiserParams,
  writeDataVisualiserParams,
  type DataVisualiserUrlState,
  type VisualiserBarWindow,
  type VisualiserChartType,
  type VisualiserPlayerPosition,
} from '../lib/dataVisualiserUrl'
import {
  barKindForMetricKey,
  defaultPizzaMetricKeys,
  groupMetricsForPizzaPicker,
  resolveProfileMetric,
  stripPer90Suffix,
} from '../lib/profileMetrics'
import type {
  PlayerRow,
  StatMeta,
  TeamSeasonRow,
  TeamStatMeta,
} from '../types/api'
import { useScope } from '../context/ScopeContext'
import { formatValue } from '../lib/format'
import { HudActionButton, HudFrame, HudLabel, HudPill, HudVSep } from '../components/hud/Hud'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import { formatTeamStatMode, teamKeyStatLabel, teamStatValueForMode } from '../lib/teamProfileMetrics'
import { ChartShareCard } from '../components/visualizer/ChartShareCard'
import { VisualiserEntityPicker, type VisualiserEntityOption } from '../components/visualizer/VisualiserEntityPicker'
import { VisualiserScatterPlot, type VisualiserScatterDatum } from '../components/visualizer/VisualiserScatterPlot'
import { VisualiserBarChart, type VisualiserBarDatum } from '../components/visualizer/VisualiserBarChart'
import { VisualiserRadarChart } from '../components/visualizer/VisualiserRadarChart'
import { filterMetricGroups, usablePlayerMetricKeys, usableTeamMetricKeys } from '../lib/metricAvailability'
import { HudMultiSelectDropdown, HudSelectDropdown, type HudDropdownGroup } from '../components/hud/HudDropdown'

const MINUTE_OPTIONS = [0, 450, 900, 1350]
const CHART_TYPES: Array<{ value: VisualiserChartType; label: string }> = [
  { value: 'scatter', label: 'Scatter' },
  { value: 'bar', label: 'Bar' },
  { value: 'radar', label: 'Radar' },
]
const PLAYER_POSITION_OPTIONS: Array<{ value: VisualiserPlayerPosition; label: string }> = [
  { value: 'ALL', label: 'Outfield' },
  { value: 'FWD', label: 'FWD' },
  { value: 'MID', label: 'MID' },
  { value: 'DEF', label: 'DEF' },
  { value: 'GK', label: 'GK' },
]
const BAR_WINDOWS: Array<{ value: VisualiserBarWindow; label: string }> = [
  { value: 'top', label: 'Top performers' },
  { value: 'bottom', label: 'Bottom performers' },
]
const RADAR_STROKES = ['#4A9EF5', '#FFBE5C', '#7FE2B8']
const RADAR_FILLS = ['rgba(74,158,245,0.18)', 'rgba(255,190,92,0.18)', 'rgba(127,226,184,0.18)']

type PickerKind = 'compare' | 'pins' | null

export function DataVisualiser() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const [pickerKind, setPickerKind] = useState<PickerKind>(null)
  const { scopeLabel, buildScopedPath } = useScope()
  const state = useMemo(() => parseDataVisualiserParams(searchParams), [searchParams])

  const playerFetchFilters = useMemo(
    () => ({
      competition: state.competition,
      season: state.season,
      min_minutes: 0,
      position_group: state.position === 'GK' ? 'GK' : undefined,
    }),
    [state.competition, state.season, state.position],
  )
  const playerQuery = useStatMatrix(playerFetchFilters, state.tab === 'players')
  const teamQuery = useQuery({
    queryKey: ['team-stat-matrix', state.competition, state.season],
    queryFn: () => fetchTeamStatMatrix({ competition: state.competition, season: state.season, include: 'meta' }),
    staleTime: 10 * 60 * 1000,
    enabled: state.tab === 'teams',
  })

  const playerRows = useMemo(() => {
    const raw = playerQuery.data?.results ?? []
    return applyClientFilters(raw, {
      teams: state.playerTeams.length ? state.playerTeams : undefined,
      position_group: state.position === 'ALL' || state.position === 'GK' ? undefined : state.position,
      min_minutes: state.minMinutes,
    })
  }, [playerQuery.data?.results, state.playerTeams, state.position, state.minMinutes])

  const playerTeamOptions = useMemo(() => {
    const all = playerQuery.data?.results ?? []
    const names = new Set<string>()
    for (const row of all) {
      if (row.canonical_team_name) names.add(row.canonical_team_name)
    }
    return [...names].toSorted()
  }, [playerQuery.data?.results])

  const activeLoading = state.tab === 'players' ? playerQuery.isLoading : teamQuery.isLoading
  const activeError = state.tab === 'players' ? playerQuery.error : teamQuery.error
  const activeIsError = state.tab === 'players' ? playerQuery.isError : teamQuery.isError
  const playerMeta = playerQuery.data?.meta
  const teamMeta = teamQuery.data?.meta

  const rawPlayerMetricGroups = useMemo(() => {
    if (!playerMeta) return []
    const grouped = groupMetricsForPizzaPicker(playerMeta)
    return dedupeMetricGroups(
      Object.keys(playerMeta.metric_groups).map(groupKey => ({
        key: groupKey,
        label: playerMeta.metric_groups[groupKey] ?? groupKey,
        items: grouped[groupKey] ?? [],
      })),
    )
  }, [playerMeta])
  const rawPlayerMetricKeys = useMemo(
    () => rawPlayerMetricGroups.flatMap(group => group.items.map(item => item.key)),
    [rawPlayerMetricGroups],
  )
  const usablePlayerKeys = useMemo(
    () =>
      playerMeta
        ? usablePlayerMetricKeys(rawPlayerMetricKeys, playerRows, state.mode, playerMeta)
        : [],
    [playerMeta, playerRows, rawPlayerMetricKeys, state.mode],
  )
  const playerMetricGroups = useMemo(
    () => filterMetricGroups(rawPlayerMetricGroups, usablePlayerKeys),
    [rawPlayerMetricGroups, usablePlayerKeys],
  )
  const playerMetricKeys = useMemo(
    () => playerMetricGroups.flatMap(group => group.items.map(item => item.key)),
    [playerMetricGroups],
  )
  const rawTeamMetricGroups = useMemo(() => dedupeMetricGroups(buildTeamMetricGroups(teamMeta)), [teamMeta])
  const rawTeamMetricKeys = useMemo(
    () => rawTeamMetricGroups.flatMap(group => group.items.map(item => item.key)),
    [rawTeamMetricGroups],
  )
  const teamRows = useMemo(() => teamQuery.data?.results ?? [], [teamQuery.data?.results])
  const usableTeamKeys = useMemo(
    () => usableTeamMetricKeys(rawTeamMetricKeys, teamRows, state.mode),
    [rawTeamMetricKeys, state.mode, teamRows],
  )
  const teamMetricGroups = useMemo(
    () => filterMetricGroups(rawTeamMetricGroups, usableTeamKeys),
    [rawTeamMetricGroups, usableTeamKeys],
  )
  const teamMetricKeys = useMemo(
    () => teamMetricGroups.flatMap(group => group.items.map(item => item.key)),
    [teamMetricGroups],
  )

  const playerDefaults = useMemo(() => playerMetricDefaults(state.position), [state.position])
  const teamDefaults = useMemo(() => teamMetricDefaults(), [])

  const xMetric = state.tab === 'players'
    ? coerceMetricKey(state.xMetric, playerMetricKeys, playerDefaults.x)
    : coerceMetricKey(state.xMetric, teamMetricKeys, teamDefaults.x)
  const yMetric = state.tab === 'players'
    ? coerceMetricKey(state.yMetric, playerMetricKeys, playerDefaults.y)
    : coerceMetricKey(state.yMetric, teamMetricKeys, teamDefaults.y)
  const barMetric = state.tab === 'players'
    ? coerceMetricKey(state.metric, playerMetricKeys, playerDefaults.bar)
    : coerceMetricKey(state.metric, teamMetricKeys, teamDefaults.bar)
  const radarMetrics = state.tab === 'players'
    ? coerceMetricKeys(
        state.radarMetrics,
        playerMetricKeys,
        playerDefaults.radar,
      ).slice(0, 8)
    : coerceMetricKeys(state.radarMetrics, teamMetricKeys, teamDefaults.radar).slice(0, 8)

  const playerScatterPoints = useMemo(() => {
    if (!playerMeta || !xMetric || !yMetric) return []
    return playerRows.flatMap<VisualiserScatterDatum>(row => {
      const x = resolveProfileMetric(row, state.mode, barKindForMetricKey(xMetric), playerMeta)
      const y = resolveProfileMetric(row, state.mode, barKindForMetricKey(yMetric), playerMeta)
      if (x.value == null || y.value == null) return []
      return [
        {
          id: row.canonical_player_id,
          label: row.canonical_player_name,
          sublabel: row.canonical_team_name ?? undefined,
          x: x.value,
          y: y.value,
          xText: formatValue(x.value, x.formatUnit),
          yText: formatValue(y.value, y.formatUnit),
          tieBreak: row.minutes,
        },
      ]
    })
  }, [playerMeta, playerRows, state.mode, xMetric, yMetric])

  const teamScatterPoints = useMemo(() => {
    if (!xMetric || !yMetric) return []
    return (teamQuery.data?.results ?? []).flatMap<VisualiserScatterDatum>(row => {
      const xValue = teamStatValueForMode(xMetric, row.stats[xMetric], row.stats.matches ?? null, state.mode)
      const yValue = teamStatValueForMode(yMetric, row.stats[yMetric], row.stats.matches ?? null, state.mode)
      if (xValue == null || yValue == null) return []
      return [
        {
          id: row.canonical_team_id,
          label: row.canonical_team_name,
          x: xValue,
          y: yValue,
          xText: formatTeamStatMode(xMetric, row.stats[xMetric], row.stats.matches ?? null, state.mode),
          yText: formatTeamStatMode(yMetric, row.stats[yMetric], row.stats.matches ?? null, state.mode),
          tieBreak: row.stats.matches ?? 0,
        },
      ]
    })
  }, [teamQuery.data?.results, state.mode, xMetric, yMetric])

  const activeScatterPoints = state.tab === 'players' ? playerScatterPoints : teamScatterPoints

  const autoHighlightItems = useMemo(
    () => rankHighHighPoints(activeScatterPoints).slice(0, 3),
    [activeScatterPoints],
  )
  const autoPinnedIds = useMemo(
    () => autoHighlightItems.map(item => item.point.id),
    [autoHighlightItems],
  )

  const validManualPinnedIds = useMemo(() => {
    const available = new Set(activeScatterPoints.map(point => point.id))
    return state.pinnedIds.filter(id => available.has(id))
  }, [activeScatterPoints, state.pinnedIds])
  const effectivePinnedIds = state.pinMode === 'manual' ? validManualPinnedIds : autoPinnedIds
  const effectivePinnedIdSet = useMemo(() => new Set(effectivePinnedIds), [effectivePinnedIds])

  const labelIds = useMemo(() => {
    if (!state.labels) return []
    if (activeScatterPoints.length <= 20) return activeScatterPoints.map(point => point.id)
    return effectivePinnedIds
  }, [activeScatterPoints, state.labels, effectivePinnedIds])

  const playerBarRows = useMemo(() => {
    if (!playerMeta || !barMetric) return []
    const rows = playerRows.flatMap<VisualiserBarDatum>(row => {
      const resolved = resolveProfileMetric(row, state.mode, barKindForMetricKey(barMetric), playerMeta)
      if (resolved.value == null) return []
      return [
        {
          id: row.canonical_player_id,
          label: row.canonical_player_name,
          sublabel: row.canonical_team_name ?? undefined,
          value: resolved.value,
          valueText: formatValue(resolved.value, resolved.formatUnit),
        },
      ]
    })
    return finalizeBarRows(rows, state.barWindow, state.barCount, effectivePinnedIds)
  }, [barMetric, playerMeta, playerRows, state.mode, state.barWindow, state.barCount, effectivePinnedIds])

  const teamBarRows = useMemo(() => {
    if (!barMetric) return []
    const rows = (teamQuery.data?.results ?? []).flatMap<VisualiserBarDatum>(row => {
      const value = teamStatValueForMode(barMetric, row.stats[barMetric], row.stats.matches ?? null, state.mode)
      if (value == null) return []
      return [
        {
          id: row.canonical_team_id,
          label: row.canonical_team_name,
          value,
          valueText: formatTeamStatMode(barMetric, row.stats[barMetric], row.stats.matches ?? null, state.mode),
        },
      ]
    })
    return finalizeBarRows(rows, state.barWindow, state.barCount, effectivePinnedIds)
  }, [barMetric, state.barCount, state.barWindow, state.mode, teamQuery.data?.results, effectivePinnedIds])

  const activeBarRows = state.tab === 'players' ? playerBarRows : teamBarRows

  const autoPlayerCompareIds = useMemo(() => {
    if (!playerMeta || !radarMetrics.length) return playerRows.slice(0, 3).map(row => row.canonical_player_id)
    return rankPlayerRowsByRadar(playerRows, radarMetrics, state.mode, playerMeta).slice(0, 3).map(item => item.id)
  }, [playerMeta, playerRows, radarMetrics, state.mode])
  const autoTeamCompareIds = useMemo(() => {
    if (!teamMeta || !radarMetrics.length) return (teamQuery.data?.results ?? []).slice(0, 3).map(row => row.canonical_team_id)
    return rankTeamRowsByRadar(teamQuery.data?.results ?? [], radarMetrics, state.mode).slice(0, 3).map(item => item.id)
  }, [radarMetrics, state.mode, teamMeta, teamQuery.data?.results])
  const compareIds = useMemo(() => {
    const available =
      state.tab === 'players'
        ? new Set(playerRows.map(row => row.canonical_player_id))
        : new Set((teamQuery.data?.results ?? []).map(row => row.canonical_team_id))
    const explicit = state.compareIds.filter(id => available.has(id))
    if (state.compareMode === 'manual') return explicit.slice(0, 3)
    return (state.tab === 'players' ? autoPlayerCompareIds : autoTeamCompareIds).filter(id => available.has(id)).slice(0, 3)
  }, [autoPlayerCompareIds, autoTeamCompareIds, playerRows, state.compareIds, state.compareMode, state.tab, teamQuery.data?.results])
  const playerCompareRows = useMemo(
    () => resolvePlayerCompareRows(playerRows, compareIds),
    [compareIds, playerRows],
  )
  const teamCompareRows = useMemo(
    () => resolveTeamCompareRows(teamQuery.data?.results ?? [], compareIds),
    [compareIds, teamQuery.data?.results],
  )

  const playerRadar = useMemo(() => {
    if (!playerMeta || radarMetrics.length === 0) return null
    const selectedRows = playerCompareRows.length ? playerCompareRows : playerRows.slice(0, 3)
    if (!selectedRows.length) return null
    const axisLabels = radarMetrics.map(key => stripPer90Suffix(playerMeta.metrics[key]?.label ?? key))
    const series = selectedRows.slice(0, 3).map((row, index) => ({
      id: row.canonical_player_id,
      label: row.canonical_player_name,
      sublabel: row.canonical_team_name ?? undefined,
      stroke: RADAR_STROKES[index % RADAR_STROKES.length],
      fill: RADAR_FILLS[index % RADAR_FILLS.length],
      values: radarMetrics.map(key => {
        const resolved = resolveProfileMetric(row, state.mode, barKindForMetricKey(key), playerMeta)
        return {
          pct: resolved.percentile ?? 0,
          text: `${stripPer90Suffix(playerMeta.metrics[key]?.label ?? key)} · ${formatValue(
            resolved.value,
            resolved.formatUnit,
          )}`,
        }
      }),
    }))
    return { axisLabels, series }
  }, [playerCompareRows, playerMeta, playerRows, radarMetrics, state.mode])

  const teamRadar = useMemo(() => {
    if (!teamMeta || radarMetrics.length === 0) return null
    const selectedRows = teamCompareRows.length ? teamCompareRows : (teamQuery.data?.results ?? []).slice(0, 3)
    if (!selectedRows.length) return null
    const teamCount = Math.max(teamQuery.data?.results?.length ?? 0, 1)
    const axisLabels = radarMetrics.map(key => teamKeyStatLabel(key, teamMeta))
    const series = selectedRows.slice(0, 3).map((row, index) => ({
      id: row.canonical_team_id,
      label: row.canonical_team_name,
      stroke: RADAR_STROKES[index % RADAR_STROKES.length],
      fill: RADAR_FILLS[index % RADAR_FILLS.length],
      values: radarMetrics.map(key => {
        const rankMap = state.mode === 'full' ? row.ranks : row.ranks_per_match
        const rank = rankMap[key] ?? null
        return {
          pct: teamRankToPercent(rank, teamCount),
          text: `${teamKeyStatLabel(key, teamMeta)} · ${formatTeamStatMode(
            key,
            row.stats[key],
            row.stats.matches ?? null,
            state.mode,
          )}`,
        }
      }),
    }))
    return { axisLabels, series }
  }, [radarMetrics, state.mode, teamCompareRows, teamMeta, teamQuery.data?.results])

  const radarModel = state.tab === 'players' ? playerRadar : teamRadar

  const pickerOptions = useMemo((): VisualiserEntityOption[] => {
    if (state.tab === 'players') {
      return playerRows.map(row => ({
        id: row.canonical_player_id,
        label: row.canonical_player_name,
        sublabel: row.canonical_team_name ?? undefined,
        meta: `${row.minutes.toLocaleString()}′`,
      }))
    }
    return (teamQuery.data?.results ?? []).map(row => ({
      id: row.canonical_team_id,
      label: row.canonical_team_name,
      meta: `Rank ${row.ranks.rank ?? '—'}`,
    }))
  }, [playerRows, state.tab, teamQuery.data?.results])

  const chartTitle = useMemo(
    () => buildChartTitle(state, xMetric, yMetric, barMetric, radarMetrics, playerMeta, teamMeta),
    [barMetric, playerMeta, radarMetrics, state, teamMeta, xMetric, yMetric],
  )
  const chartSubtitle = useMemo(
    () => buildChartSubtitle(state),
    [state],
  )
  const pageShareUrl = typeof window !== 'undefined' ? window.location.href : undefined

  function update(next: Partial<DataVisualiserUrlState>) {
    writeState(state, setSearchParams, next)
  }

  function renderChart(exportMode: boolean) {
    if (state.chart === 'scatter') {
      return (
        <VisualiserScatterPlot
          points={activeScatterPoints.map(point => ({
            ...point,
            highlighted: effectivePinnedIdSet.has(point.id),
          }))}
          xLabel={metricLabel(state.tab, xMetric, playerMeta, teamMeta)}
          yLabel={metricLabel(state.tab, yMetric, playerMeta, teamMeta)}
          showLabels={state.labels}
          labelIds={labelIds}
          shortenLabels={state.tab === 'players'}
          showTrendline={state.trendline}
          exportMode={exportMode}
          onSelect={
            exportMode
              ? undefined
              : id => navigate(buildScopedPath(state.tab === 'players' ? `/player/${id}` : `/team/${id}`))
          }
        />
      )
    }
    if (state.chart === 'bar') {
      return (
        <VisualiserBarChart
          rows={activeBarRows.map(row => ({
            ...row,
            highlighted: effectivePinnedIdSet.has(row.id),
          }))}
          metricLabel={metricLabel(state.tab, barMetric, playerMeta, teamMeta)}
          shortenLabels={state.tab === 'players'}
          exportMode={exportMode}
          onSelect={
            exportMode
              ? undefined
              : id => navigate(buildScopedPath(state.tab === 'players' ? `/player/${id}` : `/team/${id}`))
          }
        />
      )
    }
    return (
      <VisualiserRadarChart
        axisLabels={radarModel?.axisLabels ?? []}
        series={radarModel?.series ?? []}
        shortenLabels={state.tab === 'players'}
        exportMode={exportMode}
      />
    )
  }

  return (
    <div className="mx-auto max-w-[1440px] px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:px-10 lg:pb-20">
      <div className="mb-6 flex flex-col gap-5 lg:mb-8 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <div className="mb-3 flex items-center gap-2">
            <HudLabel>Create Charts</HudLabel>
            <span className="text-[10px] uppercase tracking-[0.22em] text-electric/55">Share-ready charts</span>
          </div>
          <h1 className="text-[28px] font-black leading-tight tracking-tight text-ink sm:text-[40px] sm:leading-none">
            <span className="sm:hidden">Create player and team charts.</span>
            <span className="hidden sm:inline">Create player and team charts from the Conceptually Football dataset.</span>
          </h1>
          <p className="mt-3 max-w-3xl text-[12px] leading-relaxed text-ink-dim">
            Pick a chart type, tune the cohort and metrics, then share or export the view. Scatter works best for
            landscape exploration, bar for top and bottom ranked slices, and radar for 1-3 entity shape comparisons.
          </p>
        </div>
      </div>

      <div className="mb-5 flex flex-wrap items-center gap-2 border border-electric/20 bg-panel/70 px-3 py-3 backdrop-blur-md sm:mb-6 sm:gap-3 sm:px-4">
        <HudLabel>Scope</HudLabel>
        <HudVSep />
        <span className="text-[11px] font-mono uppercase tracking-[0.16em] text-electric/85">
          {scopeLabel}
        </span>
        <div className="min-w-[8px] flex-1" />
        <div className="flex flex-wrap items-center gap-2">
          <HudPill active={state.tab === 'players'} onClick={() => update({ tab: 'players', chart: 'scatter' })}>
            Players
          </HudPill>
          <HudPill active={state.tab === 'teams'} onClick={() => update({ tab: 'teams', chart: 'bar' })}>
            Teams
          </HudPill>
        </div>
      </div>

      <div className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)] xl:gap-6">
        <div className="flex flex-col gap-6">
          <HudFrame header={<span>Builder // Config</span>}>
            <div className="flex flex-col gap-5 p-4">
              <div>
                <p className="mb-2 text-[10px] uppercase tracking-[0.22em] text-electric/75">Chart type</p>
                <div className="flex flex-wrap gap-2">
                  {CHART_TYPES.map(option => (
                    <HudPill key={option.value} active={state.chart === option.value} onClick={() => update({ chart: option.value })}>
                      {option.label}
                    </HudPill>
                  ))}
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-3">
                <ProfileRateToggle
                  value={state.mode}
                  onChange={mode => update({ mode })}
                  per90Label={state.tab === 'players' ? 'Per 90' : 'Per match'}
                  fullLabel="Season"
                  ariaLabel={state.tab === 'players' ? 'Player rate mode' : 'Team rate mode'}
                />
                {state.tab === 'players' && (
                  <>
                    <div className="flex flex-wrap gap-2">
                      {PLAYER_POSITION_OPTIONS.map(option => (
                        <HudPill
                          key={option.value}
                          active={state.position === option.value}
                          onClick={() => update({ position: option.value })}
                        >
                          {option.label}
                        </HudPill>
                      ))}
                    </div>
                  </>
                )}
              </div>

              {state.tab === 'players' && (
                <>
                  <div>
                    <p className="mb-2 text-[10px] uppercase tracking-[0.22em] text-electric/75">Club filter</p>
                    <TeamFilterDropdown
                      teams={playerTeamOptions}
                      selected={state.playerTeams}
                      onChange={teams => update({ playerTeams: teams })}
                    />
                  </div>
                  <div>
                    <p className="mb-2 text-[10px] uppercase tracking-[0.22em] text-electric/75">Minimum minutes</p>
                    <div className="flex flex-wrap gap-2">
                      {MINUTE_OPTIONS.map(minutes => (
                        <HudPill
                          key={minutes}
                          active={state.minMinutes === minutes}
                          onClick={() => update({ minMinutes: minutes })}
                          className="font-mono"
                        >
                          {minutes === 0 ? 'All' : `${minutes}'`}
                        </HudPill>
                      ))}
                    </div>
                  </div>
                </>
              )}

              <MetricControls
                state={state}
                xMetric={xMetric}
                yMetric={yMetric}
                barMetric={barMetric}
                radarMetrics={radarMetrics}
                playerMetricGroups={playerMetricGroups}
                teamMetricGroups={teamMetricGroups}
                compareIds={compareIds}
                pinnedIds={effectivePinnedIds}
                onChange={update}
                onOpenCompare={() => setPickerKind('compare')}
                onOpenPins={() => setPickerKind('pins')}
              />
            </div>
          </HudFrame>

          <HudFrame header={<span>Readout // Cohort</span>}>
            <div className="grid grid-cols-3 gap-2 p-3 sm:gap-3 sm:p-4">
              <ReadoutCard label="Rows" value={String(state.tab === 'players' ? playerRows.length : teamQuery.data?.count ?? 0)} />
              <ReadoutCard
                label={state.chart === 'radar' ? 'Axes' : 'Pinned'}
                value={String(state.chart === 'radar' ? radarMetrics.length : effectivePinnedIds.length)}
              />
              <ReadoutCard label="Radar set" value={String(compareIds.length)} />
            </div>
          </HudFrame>
        </div>

        <HudFrame
          header={<span>Preview // Live chart</span>}
          footer={
            state.chart === 'radar'
              ? 'Radar normalises each axis to make shapes comparable across stats.'
              : state.chart === 'scatter'
                ? 'Hover to inspect. Click marks to jump to the underlying profile.'
                : 'Click bars to jump to the underlying profile.'
          }
        >
          <div className="flex flex-col gap-5 p-4">
            <div className="flex flex-col gap-4 border border-electric/15 bg-electric/[0.03] p-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <p className="text-[10px] uppercase tracking-[0.24em] text-electric/80">
                  {state.tab === 'players' ? 'Players tab' : 'Teams tab'}
                </p>
                <h2 className="mt-2 text-[24px] font-black leading-none text-ink">{chartTitle}</h2>
                <p className="mt-2 max-w-3xl text-[12px] leading-relaxed text-ink-dim">{chartSubtitle}</p>
              </div>
              <ChartShareCard
                title={chartTitle}
                subtitle={chartSubtitle}
                contextLabel={`${state.tab === 'players' ? 'Players' : 'Teams'} · Create Charts`}
                fileName={chartTitle}
                aspect={state.chart === 'radar' ? 'square' : 'landscape'}
                copyUrl={pageShareUrl}
                compact={false}
                renderContent={({ exportMode }) => renderChart(exportMode)}
              />
            </div>

            {activeLoading && (
              <div className="flex items-center justify-center gap-2 py-20 text-electric">
                <Loader2 className="size-5 animate-spin" />
                <span className="text-[11px] uppercase tracking-[0.22em]">Loading chart surface</span>
              </div>
            )}

            {activeIsError && !activeLoading && (
              <div className="border border-ember/35 bg-ember/5 p-4 text-[12px] text-ember">
                {activeError instanceof Error ? activeError.message : 'Could not load chart data.'}
              </div>
            )}

            {!activeLoading && !activeIsError && <div className="min-h-[360px] sm:min-h-[480px] xl:min-h-[560px]">{renderChart(false)}</div>}
          </div>
        </HudFrame>
      </div>

      <VisualiserEntityPicker
        open={pickerKind != null}
        title={
          pickerKind === 'compare'
            ? state.chart === 'radar'
              ? `Select ${state.tab === 'players' ? 'players' : 'teams'} for radar`
              : 'Select comparison set'
            : `Highlight ${state.tab === 'players' ? 'players' : 'teams'}`
        }
        description={
          pickerKind === 'compare'
            ? 'Radar works best with 1-3 entities. The comparison set also drives the exported shape view.'
            : 'Pinned entities stay visually distinct across scatter and bar charts. Labels will show only pinned entities on large scatter cohorts.'
        }
        options={pickerOptions}
        selectedIds={pickerKind === 'compare' ? compareIds : effectivePinnedIds}
        maxSelected={pickerKind === 'compare' ? 3 : undefined}
        onChange={ids =>
          update(
            pickerKind === 'compare'
              ? { compareIds: ids, compareMode: 'manual' }
              : { pinnedIds: ids, pinMode: 'manual' },
          )
        }
        onClose={() => setPickerKind(null)}
        closeLabel={pickerKind === 'pins' ? 'Done' : 'Close'}
        isLoading={activeLoading}
        isError={activeIsError}
      />
    </div>
  )
}

function MetricControls({
  state,
  xMetric,
  yMetric,
  barMetric,
  radarMetrics,
  playerMetricGroups,
  teamMetricGroups,
  compareIds,
  pinnedIds,
  onChange,
  onOpenCompare,
  onOpenPins,
}: {
  state: DataVisualiserUrlState
  xMetric?: string
  yMetric?: string
  barMetric?: string
  radarMetrics: string[]
  playerMetricGroups: MetricGroup[]
  teamMetricGroups: MetricGroup[]
  compareIds: number[]
  pinnedIds: number[]
  onChange: (next: Partial<DataVisualiserUrlState>) => void
  onOpenCompare: () => void
  onOpenPins: () => void
}) {
  const metricGroups = state.tab === 'players' ? playerMetricGroups : teamMetricGroups
  return (
    <>
      {state.chart === 'scatter' && (
        <div className="grid gap-3 sm:grid-cols-2">
          <MetricSelect
            label="X axis"
            value={xMetric}
            groups={metricGroups}
            onChange={value => onChange({ xMetric: value })}
          />
          <MetricSelect
            label="Y axis"
            value={yMetric}
            groups={metricGroups}
            onChange={value => onChange({ yMetric: value })}
          />
        </div>
      )}

      {state.chart === 'bar' && (
        <>
          <MetricSelect
            label="Rank metric"
            value={barMetric}
            groups={metricGroups}
            onChange={value => onChange({ metric: value })}
          />
          <div className="flex flex-wrap items-center gap-2">
            {BAR_WINDOWS.map(option => (
              <HudPill
                key={option.value}
                active={state.barWindow === option.value}
                onClick={() => onChange({ barWindow: option.value })}
              >
                {option.label}
              </HudPill>
            ))}
            <ControlSelect
              label="Rows shown"
              value={String(state.barCount)}
              onChange={value =>
                onChange({
                  barCount: Math.min(
                    Math.max(Number(value) || DEFAULT_BAR_COUNT, MIN_BAR_COUNT),
                    MAX_BAR_COUNT,
                  ),
                })
              }
              options={Array.from({ length: MAX_BAR_COUNT - MIN_BAR_COUNT + 1 }, (_, index) => {
                const count = MIN_BAR_COUNT + index
                return { value: String(count), label: `Show ${count}` }
              })}
            />
          </div>
          <p className="text-[11px] leading-relaxed text-ink-dim">
            Rows shown controls how many ranked players or teams appear in the selected top or bottom slice.
          </p>
        </>
      )}

      {state.chart === 'radar' && (
        <>
          <MetricMultiSelect
            label="Radar axes"
            groups={metricGroups}
            selected={radarMetrics}
            onChange={next => onChange({ radarMetrics: next })}
          />
          <div className="flex flex-wrap items-center gap-2">
            <HudActionButton onClick={onOpenCompare} className="px-3 py-2 text-[11px]">
              {compareIds.length ? `${compareIds.length} selected` : 'Select entities'}
            </HudActionButton>
          </div>
        </>
      )}

      {state.chart !== 'radar' && (
        <div>
          <p className="mb-2 text-[10px] uppercase tracking-[0.22em] text-electric/75">Highlights</p>
          <div className="flex flex-wrap items-center gap-2">
            <HudPill active={pinnedIds.length > 0} onClick={onOpenPins} className="px-3 py-2">
              {pinnedIds.length ? `${pinnedIds.length} pinned` : 'Pin entities'}
            </HudPill>
            {state.chart === 'scatter' && (
              <HudPill active={state.labels} onClick={() => onChange({ labels: !state.labels })} className="px-3 py-2">
                Labels
              </HudPill>
            )}
            {state.chart === 'scatter' && (
              <HudPill active={state.trendline} onClick={() => onChange({ trendline: !state.trendline })} className="px-3 py-2">
                Trendline
              </HudPill>
            )}
          </div>
        </div>
      )}

      <div className="rounded border border-electric/15 bg-panel/45 p-3 text-[11px] leading-relaxed text-ink-dim">
        {state.chart === 'scatter' && (
          <span>
            Hover reveals the exact readout. Label mode shows all names only on smaller cohorts, otherwise it focuses on pinned entities.
          </span>
        )}
        {state.chart === 'bar' && (
          <span>
            Default ranked slices keep the chart shareable. Choose any window from 5 to 20 rows, and pinned entities stay in view even if they fall outside the selected top or bottom cut.
          </span>
        )}
        {state.chart === 'radar' && (
          <span>
            Radar compares up to three entities. Player shapes use percentiles; team shapes use league-relative normalisation so different stat scales still compare cleanly.
          </span>
        )}
      </div>
    </>
  )
}

interface RankedScatterHighlight {
  point: VisualiserScatterDatum
  rank: number
  xRank: number | null
  yRank: number | null
}

function buildChartTitle(
  state: DataVisualiserUrlState,
  xMetric: string | undefined,
  yMetric: string | undefined,
  barMetric: string | undefined,
  radarMetrics: string[],
  playerMeta: { metrics: Record<string, { label: string }> } | undefined,
  teamMeta: TeamStatMeta | undefined,
): string {
  const prefix = state.tab === 'players' ? 'Players' : 'Teams'
  if (state.chart === 'scatter') {
    return `${prefix} · ${metricLabel(state.tab, xMetric, playerMeta, teamMeta)} vs ${metricLabel(
      state.tab,
      yMetric,
      playerMeta,
      teamMeta,
    )}`
  }
  if (state.chart === 'bar') {
    return `${prefix} · ${metricLabel(state.tab, barMetric, playerMeta, teamMeta)}`
  }
  return `${prefix} · Radar comparison (${radarMetrics.length} axes)`
}

function buildChartSubtitle(state: DataVisualiserUrlState): string {
  const modeLabel =
    state.mode === 'full'
      ? 'season values'
      : state.tab === 'players'
        ? 'per 90 values'
        : 'per match values'
  const filters =
    state.tab === 'players'
      ? [
          state.position === 'ALL' ? 'outfield cohort' : state.position,
          `${state.minMinutes}+ minutes`,
          state.playerTeams.length
            ? state.playerTeams.length === 1
              ? state.playerTeams[0]
              : `${state.playerTeams.length} clubs`
            : 'all clubs',
        ].join(' · ')
      : 'league cohort'
  return `${state.competition} ${state.season} · ${modeLabel} · ${filters}`
}

function resolvePlayerCompareRows(rows: PlayerRow[], compareIds: number[]): PlayerRow[] {
  const map = new Map(rows.map(row => [row.canonical_player_id, row]))
  return compareIds.flatMap(id => {
    const row = map.get(id)
    return row ? [row] : []
  })
}

function resolveTeamCompareRows(rows: TeamSeasonRow[], compareIds: number[]): TeamSeasonRow[] {
  const map = new Map(rows.map(row => [row.canonical_team_id, row]))
  return compareIds.flatMap(id => {
    const row = map.get(id)
    return row ? [row] : []
  })
}

function metricLabel(
  tab: DataVisualiserUrlState['tab'],
  metricKey: string | undefined,
  playerMeta: { metrics: Record<string, { label: string }> } | undefined,
  teamMeta: TeamStatMeta | undefined,
): string {
  if (!metricKey) return 'Metric'
  if (tab === 'players') return stripPer90Suffix(playerMeta?.metrics[metricKey]?.label ?? metricKey)
  return teamKeyStatLabel(metricKey, teamMeta)
}

function teamRankToPercent(rank: number | null, teamCount: number): number {
  if (rank == null) return 0
  if (teamCount <= 1) return 100
  return ((teamCount - rank) / (teamCount - 1)) * 100
}

function rankValuesDescending<T>(
  items: T[],
  valueFor: (item: T) => number | null | undefined,
): Map<T, number> {
  const ranked = items
    .flatMap(item => {
      const value = valueFor(item)
      return value == null || Number.isNaN(value) ? [] : [{ item, value }]
    })
    .toSorted((left, right) => right.value - left.value)
  return new Map(ranked.map((entry, index) => [entry.item, index + 1]))
}

function rankHighHighPoints(points: VisualiserScatterDatum[]): RankedScatterHighlight[] {
  const xRanks = rankValuesDescending(points, point => point.x)
  const yRanks = rankValuesDescending(points, point => point.y)
  return points
    .flatMap(point => {
      const xRank = xRanks.get(point)
      const yRank = yRanks.get(point)
      if (xRank == null || yRank == null) return []
      return [{
        point,
        rank: xRank + yRank,
        xRank,
        yRank,
      }]
    })
    .toSorted((left, right) =>
      left.rank - right.rank ||
      (right.point.tieBreak ?? 0) - (left.point.tieBreak ?? 0) ||
      right.point.y - left.point.y ||
      right.point.x - left.point.x,
    )
}

function rankPlayerRowsByRadar(
  rows: PlayerRow[],
  keys: string[],
  mode: DataVisualiserUrlState['mode'],
  meta: StatMeta,
): Array<{ id: number; rank: number }> {
  const rankMaps = keys.map(key =>
    rankValuesDescending(rows, row => {
      const resolved = resolveProfileMetric(row, mode, barKindForMetricKey(key), meta)
      return resolved.percentile ?? resolved.value
    }),
  )
  return rows
    .flatMap(row => {
      const ranks = rankMaps.map(map => map.get(row))
      if (ranks.some(rank => rank == null)) return []
      const rankValues = ranks as number[]
      return [{
        id: row.canonical_player_id,
        rank: rankValues.reduce((sum, rank) => sum + rank, 0),
        minutes: row.minutes,
      }]
    })
    .toSorted((left, right) => left.rank - right.rank || right.minutes - left.minutes)
}

function rankTeamRowsByRadar(
  rows: TeamSeasonRow[],
  keys: string[],
  mode: DataVisualiserUrlState['mode'],
): Array<{ id: number; rank: number }> {
  const teamCount = Math.max(rows.length, 1)
  const rankMaps = keys.map(key =>
    rankValuesDescending(rows, row => {
      const rankMap = mode === 'full' ? row.ranks : row.ranks_per_match
      const rank = rankMap[key] ?? null
      if (rank != null) return teamRankToPercent(rank, teamCount)
      return teamStatValueForMode(key, row.stats[key], row.stats.matches ?? null, mode)
    }),
  )
  return rows
    .flatMap(row => {
      const ranks = rankMaps.map(map => map.get(row))
      if (ranks.some(rank => rank == null)) return []
      const rankValues = ranks as number[]
      return [{
        id: row.canonical_team_id,
        rank: rankValues.reduce((sum, rank) => sum + rank, 0),
        matches: row.stats.matches ?? 0,
      }]
    })
    .toSorted((left, right) => left.rank - right.rank || right.matches - left.matches)
}

interface MetricGroup {
  key: string
  label: string
  items: Array<{ key: string; label: string }>
}

function buildTeamMetricGroups(meta: TeamStatMeta | undefined): MetricGroup[] {
  if (!meta) return []
  return Object.keys(meta.stat_groups).map(groupKey => ({
    key: groupKey,
    label: meta.stat_groups[groupKey] ?? groupKey,
    items: Object.entries(meta.stats)
      .flatMap(([key, def]) => (def.group === groupKey ? [{ key, label: def.label }] : []))
      .toSorted((left, right) => left.label.localeCompare(right.label)),
  }))
}

function canonicalMetricKey(metricKey: string): string {
  const bar = barKindForMetricKey(metricKey)
  if (bar.kind === 'invariant') return metricKey.replace(/_per_90$/i, '')
  return bar.per90
}

function dedupeMetricGroups(groups: MetricGroup[]): MetricGroup[] {
  return groups.map(group => {
    const seen = new Set<string>()
    const items = group.items.filter(item => {
      const dedupeKey = `${canonicalMetricKey(item.key)}::${item.label.trim().toLowerCase()}`
      if (seen.has(dedupeKey)) return false
      seen.add(dedupeKey)
      return true
    })
    return { ...group, items }
  })
}

function toHudDropdownGroups(groups: MetricGroup[]): HudDropdownGroup[] {
  return groups.map(group => ({
    key: group.key,
    label: group.label,
    options: group.items.map(item => ({ value: item.key, label: item.label })),
  }))
}

function playerMetricDefaults(position: VisualiserPlayerPosition) {
  if (position === 'GK') {
    return {
      x: 'saves_per_90',
      y: 'accurate_long_balls_per_90',
      bar: 'clean_sheet_rate',
      radar: defaultPizzaMetricKeys('GK'),
    }
  }
  if (position === 'DEF') {
    return {
      x: 'interceptions_per_90',
      y: 'xgbuildup_per_90',
      bar: 'tackles_per_90',
      radar: defaultPizzaMetricKeys('DEF'),
    }
  }
  if (position === 'MID') {
    return {
      x: 'xa_per_90',
      y: 'xgbuildup_per_90',
      bar: 'key_passes_per_90',
      radar: defaultPizzaMetricKeys('MID'),
    }
  }
  return {
    x: 'npxg_per_90',
    y: 'xa_per_90',
    bar: 'goals_per_90',
    radar: defaultPizzaMetricKeys(position === 'FWD' ? 'FWD' : 'MID'),
  }
}

function teamMetricDefaults() {
  return {
    x: 'expected_goals',
    y: 'average_ball_possession',
    bar: 'expected_goals',
    radar: [
      'expected_goals',
      'expected_assists',
      'average_ball_possession',
      'big_chances_created',
      'clean_sheets',
      'goals_against',
    ],
  }
}

function coerceMetricKey(
  current: string | undefined,
  available: string[],
  preferred: string,
): string | undefined {
  if (!available.length) return undefined
  if (current && available.includes(current)) return current
  if (current) {
    const currentCanonical = canonicalMetricKey(current)
    const canonicalCurrent = available.find(key => canonicalMetricKey(key) === currentCanonical)
    if (canonicalCurrent) return canonicalCurrent
  }
  if (available.includes(preferred)) return preferred
  const preferredCanonical = canonicalMetricKey(preferred)
  const canonicalPreferred = available.find(key => canonicalMetricKey(key) === preferredCanonical)
  if (canonicalPreferred) return canonicalPreferred
  return available[0]
}

function coerceMetricKeys(current: string[], available: string[], preferred: string[]): string[] {
  const set = new Set(available)
  const explicit = current.filter(key => set.has(key))
  if (explicit.length) return explicit
  const fallback = preferred.filter(key => set.has(key))
  return fallback.length ? fallback : available.slice(0, 6)
}

function finalizeBarRows(
  rows: VisualiserBarDatum[],
  window: VisualiserBarWindow,
  count: number,
  pinnedIds: number[],
): VisualiserBarDatum[] {
  const sorted = rows.toSorted((left, right) => right.value - left.value)
  let base = sorted
  if (window === 'top') base = sorted.slice(0, count)
  if (window === 'bottom') base = sorted.toReversed().slice(0, count)
  if (window === 'all') base = sorted
  const baseIds = new Set(base.map(row => row.id))
  const pinnedIdSet = new Set(pinnedIds)
  const extras = sorted.filter(row => pinnedIdSet.has(row.id) && !baseIds.has(row.id))
  return [...base, ...extras]
}

function writeState(
  state: DataVisualiserUrlState,
  setSearchParams: ReturnType<typeof useSearchParams>[1],
  next: Partial<DataVisualiserUrlState>,
) {
  setSearchParams(writeDataVisualiserParams({ ...state, ...next }), { replace: true })
}

function ControlSelect({
  label = 'Select value',
  value,
  onChange,
  options,
  disabled = false,
}: {
  label?: string
  value: string
  onChange: (value: string) => void
  options: Array<{ value: string; label: string }>
  disabled?: boolean
}) {
  return (
    <HudSelectDropdown
      label={label}
      value={value}
      onChange={onChange}
      disabled={disabled}
      groups={[{ key: 'options', label, options }]}
      className="w-fit"
    />
  )
}

function MetricSelect({
  label,
  value,
  groups,
  onChange,
}: {
  label: string
  value: string | undefined
  groups: MetricGroup[]
  onChange: (value: string) => void
}) {
  return (
    <label className="flex min-w-0 flex-col gap-2">
      <span className="text-[10px] uppercase tracking-[0.22em] text-electric/75">{label}</span>
      <HudSelectDropdown
        label={label}
        value={value}
        onChange={onChange}
        groups={toHudDropdownGroups(groups)}
      />
    </label>
  )
}

function MetricMultiSelect({
  label,
  groups,
  selected,
  onChange,
}: {
  label: string
  groups: MetricGroup[]
  selected: string[]
  onChange: (selected: string[]) => void
}) {
  const options = groups.flatMap(group => group.items.map(item => ({ value: item.key, label: item.label })))

  return (
    <div className="relative">
      <p className="mb-2 text-[10px] uppercase tracking-[0.22em] text-electric/75">{label}</p>

      <div className="mb-2 flex flex-wrap gap-1.5">
        {selected.map(key => {
          const item = options.find(entry => entry.value === key)
          if (!item) return null
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange(selected.filter(entry => entry !== key))}
              className="border border-electric/25 bg-electric/10 px-2 py-1 text-[10px] uppercase tracking-wide text-electric"
            >
              {item.label}
            </button>
          )
        })}
      </div>
      <HudMultiSelectDropdown
        label="Axes"
        options={options}
        selected={selected}
        onChange={onChange}
        emptyLabel="+"
        triggerLabel="+"
        searchPlaceholder="Search metric..."
        maxSelected={8}
        hideClearButton
        hideChevron
        compact
        className="inline-flex w-auto"
      />
    </div>
  )
}

function TeamFilterDropdown({
  teams,
  selected,
  onChange,
}: {
  teams: string[]
  selected: string[]
  onChange: (teams: string[]) => void
}) {
  return (
    <HudMultiSelectDropdown
      label="Clubs"
      options={teams.map(team => ({ value: team, label: team }))}
      selected={selected}
      onChange={onChange}
      emptyLabel="All Clubs"
      searchPlaceholder="Search club..."
    />
  )
}

function ReadoutCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-electric/15 bg-panel/50 px-3 py-3">
      <div className="text-[10px] uppercase tracking-[0.22em] text-electric/70">{label}</div>
      <div className="mt-2 text-[24px] font-black leading-none text-ink">{value}</div>
    </div>
  )
}
