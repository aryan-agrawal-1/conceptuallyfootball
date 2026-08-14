import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Database, Loader2 } from 'lucide-react'
import {
  fetchGalaxySimilarForPlayer,
  fetchPlayerCohort,
  fetchPlayerDetail,
  fetchTeamDetail,
  fetchTeamStatMatrix,
} from '../../lib/api'
import { formatValue } from '../../lib/format'
import {
  barKindForMetricKey,
  profileMetricDataKeys,
  resolveProfileMetric,
  stripPer90Suffix,
} from '../../lib/profileMetrics'
import { formatTeamStatMode, teamKeyStatLabel, teamStatValueForMode } from '../../lib/teamProfileMetrics'
import type { VisualArticleBlock } from '../../lib/editorial'
import type {
  GalaxySimilarResponse,
  MatrixResponse,
  PlayerDetailResponse,
  PlayerRow,
  StatMeta,
  TeamDetailResponse,
  TeamMatrixResponse,
  TeamSeasonRow,
} from '../../types/api'
import { VisualiserBarChart, type VisualiserBarDatum } from '../visualizer/VisualiserBarChart'
import { VisualiserRadarChart } from '../visualizer/VisualiserRadarChart'
import { VisualiserScatterPlot, type VisualiserScatterDatum } from '../visualizer/VisualiserScatterPlot'
import { ProfilePizzaSvg } from '../profile/ProfilePizzaSection'
import { CompareAlignedChart } from '../comparisons/CompareAlignedChart'
import { CompareRadarChart } from '../comparisons/CompareRadarChart'
import { CompareStatTable } from '../comparisons/CompareStatTable'

const SERIES_COLOURS = [
  { stroke: '#4A9EF5', fill: 'rgba(74,158,245,0.18)' },
  { stroke: '#F0A832', fill: 'rgba(240,168,50,0.18)' },
  { stroke: '#1FD17C', fill: 'rgba(31,209,124,0.18)' },
]

type VisualPayload =
  | { kind: 'similar'; data: GalaxySimilarResponse }
  | { kind: 'players'; data: PlayerDetailResponse[] }
  | { kind: 'team'; data: TeamDetailResponse }
  | { kind: 'player_cohort'; data: MatrixResponse }
  | { kind: 'team_cohort'; data: TeamMatrixResponse }

export function VisualAnalysisBlock({ block, editor = false }: { block: VisualArticleBlock; editor?: boolean }) {
  const visualQuery = useQuery({
    queryKey: ['editorial-visual', block.visual_type, block.config],
    queryFn: () => fetchVisualPayload(block),
    enabled: visualBlockReady(block),
    staleTime: 10 * 60 * 1_000,
    retry: 1,
  })
  const stale = useMemo(() => isStaleDate(block.data_as_of), [block.data_as_of])
  const title = block.title || defaultVisualTitle(block)

  return (
    <figure
      className={`overflow-hidden border bg-mat/55 ${editor ? 'border-electric/25' : 'border-line-bright'}`}
      aria-label={block.alt || title}
      data-visual-block={block.visual_type}
      data-visual-block-id={block.id}
      data-export-format="svg-or-html"
    >
      <header className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-4 py-3 sm:px-5">
        <div>
          <p className="font-mono text-[7px] uppercase tracking-[0.2em] text-electric">{visualTypeLabel(block.visual_type)}</p>
          <h4 className="mt-1.5 text-sm font-bold tracking-[-0.015em] text-ink">{title}</h4>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-2 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">
          <span className="border border-line px-2 py-1">vs {block.config.context.scope_label || 'scope not set'}</span>
          <span className="border border-line px-2 py-1">{block.config.context.season_label || 'season not set'}</span>
          <span className="border border-line px-2 py-1">{block.config.rate_mode === 'per90' ? 'Per 90' : 'Totals'}</span>
        </div>
      </header>

      {stale ? <VisualWarning>Data context is over 32 days old. Re-check it before review or publication.</VisualWarning> : null}
      {!visualBlockReady(block) ? <VisualWarning>Finish the subject, scope, and metric choices to render this visual.</VisualWarning> : null}
      {visualQuery.isLoading ? (
        <div className="grid min-h-56 place-items-center text-center text-[10px] uppercase tracking-[0.15em] text-ink-muted"><span><Loader2 className="mx-auto mb-3 size-4 animate-spin text-electric" />Building live preview</span></div>
      ) : visualQuery.isError ? (
        <div className="grid min-h-48 place-items-center px-8 text-center"><div><AlertTriangle className="mx-auto size-5 text-gold" /><p className="mt-3 text-xs leading-5 text-ink-dim">This data is missing or no longer available for the saved scope. The configuration and accessible description are still preserved.</p></div></div>
      ) : visualQuery.data ? (
        <div className="p-4 sm:p-6"><VisualContent block={block} payload={visualQuery.data} /></div>
      ) : null}

      <figcaption className="border-t border-line px-4 py-3 sm:px-5">
        {block.caption ? <p className="text-[11px] leading-5 text-ink-dim">{block.caption}</p> : null}
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">
          <span className="flex items-center gap-1"><Database className="size-2.5" /> {block.source_note || 'Conceptually Football'}</span>
          <span>Data as of {formatDate(block.data_as_of)}</span>
        </div>
        {block.alt ? <p className="sr-only">{block.alt}</p> : null}
        <p className="mt-2 text-right font-mono text-[6px] uppercase tracking-[0.16em] text-electric/65">conceptuallyfootball.com</p>
      </figcaption>
    </figure>
  )
}

async function fetchVisualPayload(block: VisualArticleBlock): Promise<VisualPayload> {
  const { config } = block
  const first = config.entities[0]
  if (block.visual_type === 'similar_players' && first) {
    return {
      kind: 'similar',
      data: await fetchGalaxySimilarForPlayer(
        first.id,
        first.source_competition,
        first.season_label,
        config.context.scope_code,
      ),
    }
  }
  if (block.visual_type === 'custom_chart') {
    if (config.entity_kind === 'team') {
      return {
        kind: 'team_cohort',
        data: await fetchTeamStatMatrix({
          competition: config.context.scope_code,
          season: config.context.season_label,
          include: 'meta',
        }),
      }
    }
    return {
      kind: 'player_cohort',
      data: await fetchPlayerCohort(
        {
          competition: config.context.scope_code,
          season: config.context.season_label,
          position_group: config.filters.position_group === 'ALL' ? undefined : config.filters.position_group,
          teams: config.filters.team_names,
          min_minutes: config.filters.minimum_minutes,
        },
        profileMetricDataKeys(config.metric_keys, config.rate_mode),
      ),
    }
  }
  if (config.entity_kind === 'team' && first) {
    return {
      kind: 'team',
      data: await fetchTeamDetail(first.id, {
        competition: first.source_competition,
        season: first.season_label,
        include: 'meta',
      }),
    }
  }
  return {
    kind: 'players',
    data: await Promise.all(config.entities.map(entity => fetchPlayerDetail(entity.id, {
      competition: entity.source_competition,
      season: entity.season_label,
      include: 'meta',
      comparison_scope: config.context.scope_code,
    }))),
  }
}

function VisualContent({ block, payload }: { block: VisualArticleBlock; payload: VisualPayload }) {
  if (payload.kind === 'similar') return <SimilarPlayers data={payload.data} />
  if (payload.kind === 'team') return <TeamCards block={block} team={payload.data} />
  if (payload.kind === 'player_cohort') return <PlayerCohortChart block={block} data={payload.data} />
  if (payload.kind === 'team_cohort') return <TeamCohortChart block={block} data={payload.data} />
  if (block.visual_type === 'stat_card') {
    return <PlayerCards block={block} player={payload.data[0]} />
  }
  return <PlayerRadar block={block} players={payload.data} />
}

function SimilarPlayers({ data }: { data: GalaxySimilarResponse }) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {data.edges.slice(0, 6).map(edge => (
        <div key={`${edge.to_player_id}-${edge.rank}`} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-3 border border-line bg-panel/45 px-3 py-3">
          <span className="font-mono text-[9px] text-electric">#{edge.rank}</span>
          <span className="min-w-0"><strong className="block truncate text-xs text-ink">{edge.to_player_name}</strong><span className="mt-1 block truncate text-[9px] text-ink-muted">{edge.to_team_name || edge.to_competition_code}</span></span>
          <span className="border border-electric/30 bg-electric-dim/50 px-2 py-1 font-mono text-[10px] text-electric">{Math.round(edge.profile_match_score ?? edge.similarity * 100)}</span>
        </div>
      ))}
    </div>
  )
}

function PlayerCards({ block, player }: { block: VisualArticleBlock; player?: PlayerDetailResponse }) {
  if (!player?.meta) return <EmptyVisual label="Player metrics are unavailable." />
  const percentileMap = player.comparison_percentiles ?? player.percentiles
  const count = Math.max(1, Math.min(block.config.metric_keys.length, 4))
  return (
    <div className="mx-auto grid gap-px border border-line bg-line" style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`, maxWidth: `${count * 15}rem` }}>
      {block.config.metric_keys.map(key => {
        const resolved = resolveProfileMetric(player, block.config.rate_mode, barKindForMetricKey(key), player.meta as StatMeta, percentileMap)
        return <MetricCard key={key} label={stripPer90Suffix(player.meta?.metrics[key]?.label ?? key)} value={formatValue(resolved.value, resolved.formatUnit)} context={resolved.percentile == null ? 'No percentile' : `${Math.round(resolved.percentile)}th percentile`} />
      })}
    </div>
  )
}

function TeamCards({ block, team }: { block: VisualArticleBlock; team: TeamDetailResponse }) {
  const count = Math.max(1, Math.min(block.config.metric_keys.length, 4))
  return (
    <div className="mx-auto grid gap-px border border-line bg-line" style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`, maxWidth: `${count * 15}rem` }}>
      {block.config.metric_keys.map(key => <MetricCard key={key} label={teamKeyStatLabel(key, team.meta)} value={formatTeamStatMode(key, team.stats[key], team.stats.matches ?? null, block.config.rate_mode)} context={teamRankContext(team, key, block.config.rate_mode)} />)}
    </div>
  )
}

function MetricCard({ label, value, context }: { label: string; value: string; context: string }) {
  return <div className="min-h-28 bg-panel/80 p-4"><p className="text-[8px] font-bold uppercase tracking-[0.16em] text-ink-muted">{label}</p><p className="mt-3 text-2xl font-black tabular-nums text-ink">{value}</p><p className="mt-2 font-mono text-[8px] uppercase tracking-[0.1em] text-electric">{context}</p></div>
}

function PlayerRadar({ block, players }: { block: VisualArticleBlock; players: PlayerDetailResponse[] }) {
  const meta = players[0]?.meta
  if (!meta) return <EmptyVisual label="Player comparison data is unavailable." />
  if (block.visual_type === 'player_radar') {
    const player = players[0]
    return <div className="flex justify-center"><ProfilePizzaSvg player={player} rateMode={block.config.rate_mode} meta={meta} metricKeys={block.config.metric_keys} percentileMap={player.comparison_percentiles ?? player.percentiles} /></div>
  }
  const comparisonPlayers = players.map((row, slot) => ({ row, slot }))
  const percentileMapForRow = (row: PlayerRow) => (row as PlayerDetailResponse).comparison_percentiles ?? row.percentiles
  if (block.config.chart_type === 'table') {
    return <CompareStatTable metricKeys={block.config.metric_keys} players={comparisonPlayers} meta={meta} rateMode={block.config.rate_mode} hoveredStatIndex={null} lockedStatIndex={null} percentileMapForRow={percentileMapForRow} />
  }
  if (block.config.chart_type === 'dumbbell') {
    return <CompareAlignedChart metricKeys={block.config.metric_keys} players={comparisonPlayers} meta={meta} positionGroup={players[0].position_group} rateMode={block.config.rate_mode} percentileMapForRow={percentileMapForRow} />
  }
  return <CompareRadarChart metricKeys={block.config.metric_keys} players={comparisonPlayers} meta={meta} rateMode={block.config.rate_mode} hoveredStatIndex={null} lockedStatIndex={null} onHoverStat={() => undefined} onClickStat={() => undefined} percentileMapForRow={percentileMapForRow} />
}

function PlayerCohortChart({ block, data }: { block: VisualArticleBlock; data: MatrixResponse }) {
  const meta = data.meta
  if (!meta) return <EmptyVisual label="Player chart metadata is unavailable." />
  if (block.config.chart_type === 'scatter') {
    const [xKey, yKey] = block.config.metric_keys
    const points = data.results.flatMap<VisualiserScatterDatum>(row => {
      const x = resolveProfileMetric(row, block.config.rate_mode, barKindForMetricKey(xKey), meta)
      const y = resolveProfileMetric(row, block.config.rate_mode, barKindForMetricKey(yKey), meta)
      if (x.value == null || y.value == null) return []
      return [{ id: row.canonical_player_id, label: row.canonical_player_name, sublabel: row.canonical_team_name ?? undefined, x: x.value, y: y.value, xText: formatValue(x.value, x.formatUnit), yText: formatValue(y.value, y.formatUnit), highlighted: block.config.entities.some(entity => entity.id === row.canonical_player_id) }]
    })
    return <VisualiserScatterPlot points={points} xLabel={metricLabel(meta, xKey)} yLabel={metricLabel(meta, yKey)} showLabels={block.config.filters.labels} labelIds={block.config.entities.map(entity => entity.id)} showTrendline={block.config.filters.trendline} />
  }
  if (block.config.chart_type === 'bar') {
    const key = block.config.metric_keys[0]
    const rows = data.results.flatMap<VisualiserBarDatum>(row => {
      const resolved = resolveProfileMetric(row, block.config.rate_mode, barKindForMetricKey(key), meta)
      return resolved.value == null ? [] : [{ id: row.canonical_player_id, label: row.canonical_player_name, sublabel: row.canonical_team_name ?? undefined, value: resolved.value, valueText: formatValue(resolved.value, resolved.formatUnit), highlighted: block.config.entities.some(entity => entity.id === row.canonical_player_id) }]
    }).toSorted((left, right) => block.config.filters.bar_window === 'bottom' ? left.value - right.value : right.value - left.value).slice(0, block.config.filters.bar_count)
    return <VisualiserBarChart rows={rows} metricLabel={metricLabel(meta, key)} />
  }
  return <CohortPlayerRadar block={block} rows={data.results} meta={meta} />
}

function CohortPlayerRadar({ block, rows, meta }: { block: VisualArticleBlock; rows: PlayerRow[]; meta: StatMeta }) {
  const selected = block.config.entities.length ? rows.filter(row => block.config.entities.some(entity => entity.id === row.canonical_player_id)) : rows.slice(0, 3)
  const series = selected.slice(0, 3).map((row, index) => ({ id: row.canonical_player_id, label: row.canonical_player_name, sublabel: row.canonical_team_name ?? undefined, ...SERIES_COLOURS[index], values: block.config.metric_keys.map(key => { const resolved = resolveProfileMetric(row, block.config.rate_mode, barKindForMetricKey(key), meta); return { pct: resolved.percentile ?? 0, text: `${metricLabel(meta, key)} · ${formatValue(resolved.value, resolved.formatUnit)}` } }) }))
  return <VisualiserRadarChart axisLabels={block.config.metric_keys.map(key => metricLabel(meta, key))} series={series} />
}

function TeamCohortChart({ block, data }: { block: VisualArticleBlock; data: TeamMatrixResponse }) {
  const meta = data.meta
  if (!meta) return <EmptyVisual label="Team chart metadata is unavailable." />
  if (block.config.chart_type === 'scatter') {
    const [xKey, yKey] = block.config.metric_keys
    const points = data.results.flatMap<VisualiserScatterDatum>(row => {
      const x = teamStatValueForMode(xKey, row.stats[xKey], row.stats.matches ?? null, block.config.rate_mode)
      const y = teamStatValueForMode(yKey, row.stats[yKey], row.stats.matches ?? null, block.config.rate_mode)
      if (x == null || y == null) return []
      return [{ id: row.canonical_team_id, label: row.canonical_team_name, x, y, xText: formatTeamStatMode(xKey, row.stats[xKey], row.stats.matches ?? null, block.config.rate_mode), yText: formatTeamStatMode(yKey, row.stats[yKey], row.stats.matches ?? null, block.config.rate_mode), highlighted: block.config.entities.some(entity => entity.id === row.canonical_team_id) }]
    })
    return <VisualiserScatterPlot points={points} xLabel={teamKeyStatLabel(xKey, meta)} yLabel={teamKeyStatLabel(yKey, meta)} showLabels={block.config.filters.labels} labelIds={block.config.entities.map(entity => entity.id)} showTrendline={block.config.filters.trendline} />
  }
  if (block.config.chart_type === 'bar') {
    const key = block.config.metric_keys[0]
    const rows = data.results.flatMap<VisualiserBarDatum>(row => { const value = teamStatValueForMode(key, row.stats[key], row.stats.matches ?? null, block.config.rate_mode); return value == null ? [] : [{ id: row.canonical_team_id, label: row.canonical_team_name, value, valueText: formatTeamStatMode(key, row.stats[key], row.stats.matches ?? null, block.config.rate_mode), highlighted: block.config.entities.some(entity => entity.id === row.canonical_team_id) }] }).toSorted((left, right) => block.config.filters.bar_window === 'bottom' ? left.value - right.value : right.value - left.value).slice(0, block.config.filters.bar_count)
    return <VisualiserBarChart rows={rows} metricLabel={teamKeyStatLabel(key, meta)} />
  }
  const chosen = block.config.entities.length ? data.results.filter(row => block.config.entities.some(entity => entity.id === row.canonical_team_id)) : data.results.slice(0, 3)
  const series = chosen.slice(0, 3).map((row, index) => ({ id: row.canonical_team_id, label: row.canonical_team_name, ...SERIES_COLOURS[index], values: block.config.metric_keys.map(key => ({ pct: teamPercentile(row, key, data.results.length, block.config.rate_mode), text: `${teamKeyStatLabel(key, meta)} · ${formatTeamStatMode(key, row.stats[key], row.stats.matches ?? null, block.config.rate_mode)}` })) }))
  return <VisualiserRadarChart axisLabels={block.config.metric_keys.map(key => teamKeyStatLabel(key, meta))} series={series} />
}

function VisualWarning({ children }: { children: string }) {
  return <div className="flex items-center gap-2 border-b border-gold/25 bg-gold-dim/30 px-4 py-2 text-[9px] leading-4 text-gold sm:px-5"><AlertTriangle className="size-3 shrink-0" />{children}</div>
}

function EmptyVisual({ label }: { label: string }) {
  return <p className="py-12 text-center text-xs text-ink-muted">{label}</p>
}

function visualBlockReady(block: VisualArticleBlock): boolean {
  const { config } = block
  const minimumEntities = block.visual_type === 'player_comparison' ? 2 : block.visual_type === 'custom_chart' ? 0 : 1
  const minimumMetrics = block.visual_type === 'similar_players' ? 0 : block.visual_type === 'custom_chart' && config.chart_type === 'scatter' ? 2 : block.visual_type === 'player_radar' || block.visual_type === 'player_comparison' || (block.visual_type === 'custom_chart' && config.chart_type === 'radar') ? 3 : 1
  return Boolean(config.context.scope_code && config.context.season_label && config.entities.length >= minimumEntities && config.metric_keys.length >= minimumMetrics)
}

function defaultVisualTitle(block: VisualArticleBlock): string {
  const names = block.config.entities.map(entity => entity.name)
  if (block.visual_type === 'similar_players') return names[0] ? `Players most similar to ${names[0]}` : 'Similar players'
  if (block.visual_type === 'player_comparison') return names.length ? names.join(' vs ') : 'Player comparison'
  if (block.visual_type === 'player_radar') return names[0] ? `${names[0]} percentile profile` : 'Player percentile profile'
  if (block.visual_type === 'stat_card') return names[0] ? `${names[0]} key numbers` : 'Key numbers'
  return `${block.config.entity_kind === 'player' ? 'Player' : 'Team'} ${block.config.chart_type} chart`
}

function visualTypeLabel(type: VisualArticleBlock['visual_type']): string {
  return ({ similar_players: 'Similar player view', player_radar: 'Player profile', stat_card: 'Stat cards', player_comparison: 'Player comparison', custom_chart: 'Custom chart' })[type]
}

function metricLabel(meta: StatMeta, key: string): string {
  return stripPer90Suffix(meta.metrics[key]?.label ?? key)
}

function teamRankContext(team: TeamDetailResponse, key: string, rateMode: 'per90' | 'full'): string {
  const rank = (rateMode === 'full' ? team.ranks : team.ranks_per_match)[key]
  return rank == null ? 'No rank' : `League rank ${rank}`
}

function teamPercentile(row: TeamSeasonRow, key: string, count: number, rateMode: 'per90' | 'full'): number {
  const rank = (rateMode === 'full' ? row.ranks : row.ranks_per_match)[key]
  if (rank == null || count <= 1) return 0
  return Math.max(0, Math.min(100, ((count - rank) / (count - 1)) * 100))
}

function isStaleDate(value: string): boolean {
  const timestamp = new Date(`${value}T00:00:00Z`).getTime()
  return Number.isFinite(timestamp) && Date.now() - timestamp > 32 * 86_400_000
}

function formatDate(value: string): string {
  const date = new Date(`${value}T00:00:00Z`)
  return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date)
}
