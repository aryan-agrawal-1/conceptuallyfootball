import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  GitCompareArrows,
  Loader2,
  Radar,
  Search,
  Sparkles,
  Target,
  X,
} from 'lucide-react'
import {
  fetchGkStatMatrix,
  fetchSearchEntities,
  fetchStatMatrix,
  fetchTeamStatMatrix,
  fetchCompetitionSeasonsCatalog,
  fetchPlayerDetail,
} from '../../lib/api'
import { foldForSearch } from '../../lib/foldAccents'
import { canonicalProfileMetricKey, defaultPizzaMetricKeys, stripPer90Suffix } from '../../lib/profileMetrics'
import { comparisonAxisPacksForPosition } from '../../lib/comparisonAxisPacks'
import { rankBarCandidates, rankScatterPointsByTopRight } from '../../lib/visualiserRanking'
import {
  AUTO_HIGHLIGHT_LIMIT,
  effectivePinIds,
  playerBarCandidates as buildPlayerBarCandidates,
  playerScatterPoints as buildPlayerScatterPoints,
  relevanceSortedOptions,
  teamBarCandidates as buildTeamBarCandidates,
  teamScatterPoints as buildTeamScatterPoints,
} from '../../lib/visualiserCharts'
import { VisualiserEntityPicker } from '../visualizer/VisualiserEntityPicker'
import {
  newVisualBlock,
  fetchCustomChartCohort,
  type VisualArticleBlock,
  type VisualBlockType,
  type VisualEntityKind,
  type VisualEntityReference,
  type VisualScopeKind,
} from '../../lib/editorial'
import type {
  CompetitionCatalogEntry,
  SearchPlayerEntity,
  SearchPlayerMembership,
  SearchTeamEntity,
  SearchTeamMembership,
  PlayerDetailResponse,
  PositionGroup,
  StatMeta,
  TeamStatMeta,
} from '../../types/api'
import { VisualAnalysisBlock } from './VisualAnalysisBlock'

const VISUAL_TYPES: Array<{
  type: VisualBlockType
  label: string
  description: string
  icon: typeof Radar
  hint: string
}> = [
  { type: 'similar_players', label: 'Similar players', description: 'A ranked set of stylistic matches for one player.', icon: Sparkles, hint: '1 player · scope' },
  { type: 'player_radar', label: 'Player profile', description: 'A focused percentile pizza with your chosen metrics.', icon: Radar, hint: '1 player · 3–12 metrics' },
  { type: 'stat_card', label: 'Key-stat cards', description: 'A fast row of player or team numbers and ranks.', icon: Target, hint: 'Player or team · 1–4 metrics' },
  { type: 'player_comparison', label: 'Player comparison', description: 'Compare two or three players on the same axes.', icon: GitCompareArrows, hint: '2–3 players · shared scope' },
  { type: 'custom_chart', label: 'Custom chart', description: 'Build a scatter or ranked bar chart for players or teams.', icon: BarChart3, hint: 'Cohort · x/y or metric' },
]

const inputClass = 'h-10 w-full border border-line-bright bg-mat px-3 text-xs text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none'
const BIG_FIVE_CODES = new Set(['ENG1', 'GER1', 'SPA1', 'FRA1', 'ITA1'])

export function VisualBlockPicker({
  initialBlock,
  initialType,
  onClose,
  onInsert,
}: {
  initialBlock?: VisualArticleBlock
  initialType?: VisualBlockType
  onClose: () => void
  onInsert: (block: VisualArticleBlock) => void
}) {
  const [step, setStep] = useState<1 | 2 | 3>(initialBlock || initialType ? 2 : 1)
  const [block, setBlock] = useState<VisualArticleBlock>(() => initialBlock ?? newVisualBlock(initialType ?? 'custom_chart'))
  const [entityQuery, setEntityQuery] = useState('')
  const [metricQuery, setMetricQuery] = useState('')
  const [pinPickerOpen, setPinPickerOpen] = useState(false)
  const dialogRef = useRef<HTMLDivElement>(null)
  const searchQuery = useQuery({ queryKey: ['search-entities'], queryFn: fetchSearchEntities, staleTime: 10 * 60 * 1_000 })
  const catalogQuery = useQuery({ queryKey: ['competition-seasons'], queryFn: fetchCompetitionSeasonsCatalog, staleTime: 10 * 60 * 1_000 })
  const comparisonDetailsQuery = useQuery({
    queryKey: ['editorial-comparison-details', block.config.entities, block.config.context.scope_code],
    queryFn: () => Promise.all(block.config.entities.map(entity => fetchPlayerDetail(entity.id, {
      competition: entity.source_competition,
      season: entity.season_label,
      include: 'meta',
      comparison_scope: block.config.context.scope_code,
    }))),
    enabled: block.visual_type === 'player_comparison' && block.config.entities.length > 0 && Boolean(block.config.context.scope_code),
    staleTime: 10 * 60 * 1_000,
  })
  const metricQueryResult = useQuery({
    queryKey: ['editorial-visual-metrics', block.config.entity_kind, block.config.context.scope_code, block.config.context.season_label, block.config.filters.position_group],
    queryFn: async () => {
      const { context, entity_kind: entityKind, filters } = block.config
      if (entityKind === 'team') {
        const response = await fetchTeamStatMatrix({ competition: context.scope_code, season: context.season_label, include: 'meta' })
        return { kind: 'team' as const, meta: response.meta }
      }
      const response = filters.position_group === 'GK'
        ? await fetchGkStatMatrix({ competition: context.scope_code, season: context.season_label, min_minutes: 0, position_group: 'GK', page_size: 1 }, 'meta')
        : await fetchStatMatrix({ competition: context.scope_code, season: context.season_label, min_minutes: 0, position_group: filters.position_group === 'ALL' ? undefined : filters.position_group, page_size: 1 }, 'meta')
      return { kind: 'player' as const, meta: response.meta }
    },
    enabled: Boolean(block.config.context.scope_code && block.config.context.season_label),
    staleTime: 10 * 60 * 1_000,
  })

  const metricOptions = useMemo(() => {
    const base = buildMetricOptions(metricQueryResult.data)
    if (block.visual_type !== 'player_comparison' || !comparisonDetailsQuery.data?.length) return base
    return base.filter(metric => comparisonDetailsQuery.data?.every(row => comparisonMetricAvailable(row, metric.key)))
  }, [block.visual_type, comparisonDetailsQuery.data, metricQueryResult.data])
  const defaultMetricKeys = useMemo(() => visualDefaultMetricKeys(block, metricOptions, comparisonDetailsQuery.data), [block, comparisonDetailsQuery.data, metricOptions])
  const effectiveMetricKeys = useMemo(() => {
    const available = new Set(metricOptions.map(metric => metric.key))
    const selected = block.config.metric_keys.filter(key => available.has(key))
    const minimum = metricMinimum(block)
    return selected.length >= minimum ? selected : defaultMetricKeys
  }, [block, defaultMetricKeys, metricOptions])
  const effectiveBlock = useMemo(() => ({ ...block, config: { ...block.config, metric_keys: effectiveMetricKeys } }), [block, effectiveMetricKeys])
  const filteredMetrics = useMemo(() => {
    const needle = foldForSearch(metricQuery.trim())
    return needle ? metricOptions.filter(metric => foldForSearch(`${metric.label} ${metric.group}`).includes(needle)) : metricOptions
  }, [metricOptions, metricQuery])
  const customCohortQuery = useQuery({
    queryKey: ['editorial-custom-chart-cohort', block.config.entity_kind, block.config.context.scope_code, block.config.context.season_label, block.config.filters.position_group, block.config.filters.minimum_minutes, block.config.rate_mode, effectiveMetricKeys],
    queryFn: () => fetchCustomChartCohort({ ...block.config, metric_keys: effectiveMetricKeys }),
    enabled: block.visual_type === 'custom_chart' && Boolean(block.config.context.scope_code && block.config.context.season_label),
    staleTime: 10 * 60 * 1_000,
  })
  const customPinModel = useMemo(() => {
    if (block.visual_type !== 'custom_chart' || block.config.chart_type === 'radar') return null
    const payload = customCohortQuery.data
    if (!payload) return null
    const chartType = block.config.chart_type
    const keys = effectiveMetricKeys
    const barWindow = block.config.filters.bar_window
    let rows: Array<{ id: number; label: string; sublabel?: string; meta?: string; reference: VisualEntityReference }>
    let relevanceIds: number[] = []
    if (payload.kind === 'player_cohort') {
      const meta = payload.data.meta
      if (!meta) return null
      const results = payload.data.results
      if (chartType === 'scatter' && keys.length >= 2) {
        relevanceIds = rankScatterPointsByTopRight(buildPlayerScatterPoints(results, meta, block.config.rate_mode, keys[0], keys[1])).map(item => item.point.id)
      } else if (chartType === 'bar' && keys.length >= 1) {
        relevanceIds = rankBarCandidates(buildPlayerBarCandidates(results, meta, block.config.rate_mode, keys[0]), barWindow).map(item => item.id)
      }
      rows = results.map(row => ({
        id: row.canonical_player_id,
        label: row.canonical_player_name,
        sublabel: row.canonical_team_name ?? undefined,
        meta: `${row.minutes.toLocaleString()}′`,
        reference: {
          kind: 'player',
          id: row.canonical_player_id,
          name: row.canonical_player_name,
          source_competition: row.competition_code,
          season_label: row.season_label,
          competition_season_id: row.competition_season,
          position_group: row.position_group,
          team_name: row.canonical_team_name ?? '',
        },
      }))
    } else {
      const results = payload.data.results
      if (chartType === 'scatter' && keys.length >= 2) {
        relevanceIds = rankScatterPointsByTopRight(buildTeamScatterPoints(results, block.config.rate_mode, keys[0], keys[1])).map(item => item.point.id)
      } else if (chartType === 'bar' && keys.length >= 1) {
        relevanceIds = rankBarCandidates(buildTeamBarCandidates(results, block.config.rate_mode, keys[0]), barWindow).map(item => item.id)
      }
      rows = results.map(row => ({
        id: row.canonical_team_id,
        label: row.canonical_team_name,
        meta: `Rank ${row.ranks.rank ?? '-'}`,
        reference: {
          kind: 'team',
          id: row.canonical_team_id,
          name: row.canonical_team_name,
          source_competition: row.competition_code,
          season_label: row.season_label,
          competition_season_id: row.competition_season,
        },
      }))
    }
    const autoIds = relevanceIds.slice(0, AUTO_HIGHLIGHT_LIMIT)
    const manualIds = block.config.entities.map(entity => entity.id)
    const pinnedIds = effectivePinIds(
      block.config.filters.pin_mode === 'manual' ? 'manual' : 'auto',
      manualIds,
      autoIds,
      rows.map(row => row.id),
    )
    return {
      options: relevanceSortedOptions(
        rows.map(row => ({ id: row.id, label: row.label, sublabel: row.sublabel, meta: row.meta })),
        relevanceIds,
      ),
      pinnedIds,
      entitiesById: new Map(rows.map(row => [row.id, row.reference])),
    }
  }, [customCohortQuery.data, effectiveMetricKeys, block.visual_type, block.config.chart_type, block.config.rate_mode, block.config.filters.bar_window, block.config.filters.pin_mode, block.config.entities])

  function setPinnedEntities(ids: number[]) {
    if (!customPinModel) return
    setBlock(current => ({
      ...current,
      config: {
        ...current.config,
        entities: ids.flatMap(id => {
          const entity = customPinModel.entitiesById.get(id)
          return entity ? [entity] : []
        }),
        filters: { ...current.config.filters, pin_mode: 'manual' },
      },
    }))
  }

  const entityOptions = useMemo(() => {
    const source = block.config.entity_kind === 'player' ? searchQuery.data?.players ?? [] : searchQuery.data?.teams ?? []
    const needle = foldForSearch(entityQuery.trim())
    return source.filter(entity => {
      const name = 'canonical_player_name' in entity ? entity.canonical_player_name : entity.canonical_team_name
      if (needle && !foldForSearch(name).includes(needle)) return false
      if (block.visual_type === 'player_comparison' && block.config.entities[0] && 'memberships' in entity) {
        const first = block.config.entities[0]
        const firstPosition = first.position_group
        return (entity as SearchPlayerEntity).memberships.some(membership =>
          (membership.aggregate_season === block.config.context.season_label || membership.season === first.season_label)
          && membership.position_group === firstPosition,
        )
      }
      return true
    }).slice(0, 60)
  }, [block.config.context.season_label, block.config.entities, block.config.entity_kind, block.visual_type, entityQuery, searchQuery.data])

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      if (pinPickerOpen) setPinPickerOpen(false)
      else onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose, pinPickerOpen])

  function chooseType(type: VisualBlockType) {
    const next = newVisualBlock(type)
    if (type === 'custom_chart') {
      const entry = defaultCustomScope(catalogQuery.data?.competitions ?? [])
      if (entry) next.config.context = contextForCatalogEntry(entry)
    }
    setBlock(next)
    setStep(2)
    setEntityQuery('')
    setMetricQuery('')
  }

  function changeEntityKind(kind: VisualEntityKind) {
    setBlock(current => ({
      ...current,
      config: {
        ...current.config,
        entity_kind: kind,
        entities: [],
        metric_keys: [],
        filters: { ...current.config.filters, position_group: 'ALL' },
      },
    }))
  }

  function toggleEntity(entity: SearchPlayerEntity | SearchTeamEntity) {
    const id = 'canonical_player_id' in entity ? entity.canonical_player_id : entity.canonical_team_id
    const selected = block.config.entities.some(item => item.id === id)
    if (selected) {
      setBlock(current => ({ ...current, config: { ...current.config, entities: current.config.entities.filter(item => item.id !== id) } }))
      return
    }
    const multiple = block.visual_type === 'player_comparison'
    const max = entityMaximum(block)
    if (multiple && block.config.entities.length >= max) return
    const reference = referenceForEntity(entity, block.config.entities[0])
    if (!reference) return
    setBlock(current => {
      const entities = multiple ? [...current.config.entities, reference] : [reference]
      const context = multiple && current.config.entities.length ? current.config.context : contextForReference(reference, entity, catalogQuery.data?.competitions ?? [])
      const position = reference.kind === 'player' && reference.position_group ? reference.position_group : current.config.filters.position_group
      return { ...current, config: { ...current.config, entities, context, metric_keys: [], filters: { ...current.config.filters, position_group: position === 'UNK' ? 'ALL' : position } } }
    })
    if (!multiple) setEntityQuery('canonical_player_name' in entity ? entity.canonical_player_name : entity.canonical_team_name)
  }

  function removeEntity(id: number) {
    setBlock(current => ({ ...current, config: { ...current.config, entities: current.config.entities.filter(entity => entity.id !== id) } }))
  }

  function changeScope(scopeKind: VisualScopeKind) {
    const first = block.config.entities[0]
    if (!first) return
    const entity = findSourceEntity(first, searchQuery.data)
    setBlock(current => ({ ...current, config: { ...current.config, context: contextForScope(first, entity, scopeKind, catalogQuery.data?.competitions ?? []), metric_keys: [] } }))
  }

  function changeCustomScope(code: string) {
    const entry = catalogQuery.data?.competitions.find(item => item.code === code)
    if (!entry) return
    setBlock(current => ({ ...current, config: { ...current.config, context: contextForCatalogEntry(entry), metric_keys: [] } }))
  }

  function changeSeason(seasonLabel: string) {
    if (block.visual_type === 'custom_chart') {
      setBlock(current => ({ ...current, config: { ...current.config, context: { ...current.config.context, season_label: seasonLabel }, metric_keys: [] } }))
      return
    }
    setBlock(current => ({
      ...current,
      config: {
        ...current.config,
        entities: current.config.entities.flatMap(reference => {
          const source = findSourceEntity(reference, searchQuery.data)
          const membership = membershipForSeasonAndScope(
            source?.memberships ?? [],
            seasonLabel,
            current.config.context.scope_kind,
            current.config.context.scope_code,
            reference.position_group,
          )
          const next = source && membership ? referenceFromMembership(source, membership) : null
          return next ? [next] : []
        }),
        context: { ...current.config.context, season_label: seasonLabel },
        metric_keys: [],
      },
    }))
  }

  function toggleMetric(key: string) {
    const selected = effectiveMetricKeys.includes(key)
    const max = metricMaximum(block)
    setBlock(current => ({ ...current, config: { ...current.config, metric_keys: selected ? effectiveMetricKeys.filter(item => item !== key) : [...effectiveMetricKeys, key].slice(0, max) } }))
  }

  function changeScatterMetric(axis: 0 | 1, key: string) {
    const next = effectiveMetricKeys.slice(0, 2)
    const otherAxis = axis === 0 ? 1 : 0
    if (next[otherAxis] === key) {
      next[otherAxis] = next[axis]
    }
    next[axis] = key
    setBlock(current => ({ ...current, config: { ...current.config, metric_keys: next.filter(Boolean) } }))
  }

  function changeBarMetric(key: string) {
    setBlock(current => ({ ...current, config: { ...current.config, metric_keys: [key] } }))
  }

  function continueToDetails() {
    if (!configurationComplete(effectiveBlock)) return
    setBlock({
      ...effectiveBlock,
      title: effectiveBlock.title || suggestedTitle(effectiveBlock),
      alt: effectiveBlock.alt || suggestedAlt(effectiveBlock, metricOptions),
    })
    setStep(3)
  }

  function finish() {
    if (!detailsComplete(effectiveBlock)) return
    onInsert(effectiveBlock)
  }

  const customScopeEntry = catalogQuery.data?.competitions.find(entry => entry.code === block.config.context.scope_code)
  const seasonOptions = block.visual_type === 'custom_chart'
    ? customScopeEntry?.seasons.map(season => season.label) ?? []
    : seasonsForSelectedEntity(block, searchQuery.data)
  const bigFiveUnavailable = block.config.entities[0]?.kind === 'player' && !BIG_FIVE_CODES.has(block.config.entities[0].source_competition)

  return (
    <div className="fixed inset-0 z-[80] bg-mat/90 backdrop-blur-sm" role="presentation">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="visual-picker-title" className="flex h-full flex-col bg-panel lg:m-4 lg:h-[calc(100%-2rem)] lg:border lg:border-line-bright lg:shadow-2xl">
        <header className="flex min-h-16 items-center justify-between gap-4 border-b border-line px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-4">
            {step > 1 ? <button type="button" onClick={() => setStep(step === 3 ? 2 : 1)} className="grid size-9 place-items-center border border-line text-ink-muted hover:border-electric hover:text-electric" aria-label="Previous step"><ArrowLeft className="size-4" /></button> : null}
            <div><p className="font-mono text-[7px] uppercase tracking-[0.2em] text-electric">Visual studio · {step} of 3</p><h2 id="visual-picker-title" className="mt-1 text-sm font-bold text-ink">{step === 1 ? 'What should this visual explain?' : step === 2 ? 'Shape the analysis' : 'Make it publication-ready'}</h2></div>
          </div>
          <div className="flex items-center gap-3">
            <StepDots step={step} />
            <button type="button" onClick={onClose} className="grid size-9 place-items-center text-ink-muted hover:text-ink" aria-label="Close visual picker"><X className="size-4" /></button>
          </div>
        </header>

        {step === 1 ? (
          <div className="mx-auto grid w-full max-w-6xl flex-1 content-center gap-3 overflow-y-auto p-6 sm:grid-cols-2 lg:grid-cols-3 lg:p-10">
            {VISUAL_TYPES.map(option => <VisualTypeCard key={option.type} option={option} onClick={() => chooseType(option.type)} />)}
          </div>
        ) : (
          <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(360px,520px)_minmax(0,1fr)]">
            <div className="overflow-y-auto border-b border-line p-5 sm:p-7 lg:border-b-0 lg:border-r">
              {step === 2 ? (
                <div className="space-y-7">
                  {block.visual_type !== 'custom_chart' ? <Section title="1 · Subject" description={subjectDescription(block)}>
                    {block.visual_type === 'stat_card' ? <Segmented value={block.config.entity_kind} options={[['player', 'Player'], ['team', 'Team']]} onChange={value => changeEntityKind(value as VisualEntityKind)} /> : null}
                    <div className="relative mt-3"><Search className="pointer-events-none absolute left-3 top-3 size-3.5 text-ink-muted" /><input autoFocus value={entityQuery} onChange={event => setEntityQuery(event.target.value)} className={`${inputClass} pl-9`} placeholder={`Search ${block.config.entity_kind}s…`} /></div>
                    {entityQuery.trim() && (!block.config.entities.length || entityQuery !== block.config.entities[0]?.name) ? <div className="mt-2 flex max-h-48 flex-wrap content-start gap-2 overflow-y-auto border border-line bg-mat/40 p-2">
                      {searchQuery.isLoading ? <LoadingLine label="Loading canonical entities" /> : entityOptions.map(entity => <EntityOption key={'canonical_player_id' in entity ? entity.canonical_player_id : entity.canonical_team_id} entity={entity} selected={block.config.entities.some(item => item.id === ('canonical_player_id' in entity ? entity.canonical_player_id : entity.canonical_team_id))} disabled={!block.config.entities.some(item => item.id === ('canonical_player_id' in entity ? entity.canonical_player_id : entity.canonical_team_id)) && block.config.entities.length >= entityMaximum(block)} multiple={block.visual_type === 'player_comparison'} onClick={() => toggleEntity(entity)} />)}
                    </div> : null}
                    {block.visual_type === 'player_comparison' && block.config.entities.length ? <div className="mt-3 flex flex-wrap gap-2">{block.config.entities.map((entity, index) => <span key={`${entity.kind}-${entity.id}`} className="flex items-center gap-2 border border-electric/30 bg-electric-dim/35 px-2.5 py-1.5 text-[9px] text-ink"><span className="font-mono text-electric">{index + 1}</span>{entity.name}<button type="button" onClick={() => removeEntity(entity.id)} aria-label={`Remove ${entity.name}`} className="text-ink-muted hover:text-ember"><X className="size-3" /></button></span>)}</div> : null}
                    {block.visual_type === 'player_comparison' && block.config.entities[0]?.position_group ? <p className="mt-3 border-l-2 border-mint pl-3 text-[9px] leading-4 text-ink-dim">Now showing only {positionName(block.config.entities[0].position_group)} from this season, so every comparison stays meaningful.</p> : null}
                  </Section> : <Section title="1 · Chart scope" description="Choose the cohort first. Every player or team in this scope can become a plotted point.">
                    <Segmented value={block.config.entity_kind} options={[['player', 'Players'], ['team', 'Teams']]} onChange={value => changeEntityKind(value as VisualEntityKind)} />
                    <label className="mt-3 block"><FieldLabel>Competition or aggregate</FieldLabel><select value={block.config.context.scope_code} onChange={event => changeCustomScope(event.target.value)} className={inputClass}><option value="">Choose scope…</option>{customScopeOptions(catalogQuery.data?.competitions ?? []).map(entry => <option key={entry.code} value={entry.code}>{entry.name}</option>)}</select></label>
                  </Section>}

                  <Section title="2 · Comparison context" description={block.visual_type === 'custom_chart' ? 'Set the season and population filters for the chart.' : 'Choose the season and population that gives ranks and percentiles their meaning.'}>
                    {block.visual_type !== 'custom_chart' ? <Segmented value={block.config.context.scope_kind} options={[['league', 'Within league'], ['big5', 'Big 5'], ['all', 'All leagues']]} onChange={value => changeScope(value as VisualScopeKind)} disabled={!block.config.entities.length} disabledOptions={bigFiveUnavailable ? ['big5'] : []} /> : null}
                    <div className="mt-4 grid gap-3 sm:grid-cols-2"><label><FieldLabel>Season</FieldLabel><select value={block.config.context.season_label} disabled={!seasonOptions.length} onChange={event => changeSeason(event.target.value)} className={inputClass}>{seasonOptions.map(season => <option key={season} value={season}>{season}</option>)}</select></label><label><FieldLabel>Rate</FieldLabel><select value={block.config.rate_mode} onChange={event => setBlock(current => ({ ...current, config: { ...current.config, rate_mode: event.target.value as 'per90' | 'full' } }))} className={inputClass}><option value="per90">Per 90 / per match</option><option value="full">Season totals</option></select></label></div>
                    {bigFiveUnavailable ? <p className="mt-2 text-[9px] leading-4 text-ink-muted">Big 5 is unavailable because this player’s selected league is outside the Big 5.</p> : null}
                    {block.visual_type === 'custom_chart' && block.config.entity_kind === 'player' ? <div className="mt-3 grid gap-3 sm:grid-cols-2"><label><FieldLabel>Position</FieldLabel><select value={block.config.filters.position_group} onChange={event => setBlock(current => ({ ...current, config: { ...current.config, metric_keys: [], filters: { ...current.config.filters, position_group: event.target.value as 'ALL' | 'FWD' | 'MID' | 'DEF' | 'GK' } } }))} className={inputClass}><option value="ALL">All outfield</option><option value="FWD">Forwards</option><option value="MID">Midfielders</option><option value="DEF">Defenders</option><option value="GK">Goalkeepers</option></select></label><label><FieldLabel>Minimum minutes</FieldLabel><input type="number" min="0" step="90" value={block.config.filters.minimum_minutes} onChange={event => setBlock(current => ({ ...current, config: { ...current.config, filters: { ...current.config.filters, minimum_minutes: Number(event.target.value) } } }))} className={inputClass} /></label></div> : null}
                  </Section>

                  {block.visual_type !== 'similar_players' ? <Section title="3 · Display" description={metricDescription(block)}>
                    {block.visual_type === 'custom_chart' ? <Segmented value={block.config.chart_type} options={[['scatter', 'Scatter'], ['bar', 'Bar']]} onChange={value => setBlock(current => ({ ...current, config: { ...current.config, chart_type: value as 'scatter' | 'bar', metric_keys: [] } }))} /> : null}
                    {block.visual_type === 'player_comparison' ? <Segmented value={block.config.chart_type} options={[['dumbbell', 'Dumbbell'], ['radar', 'Radar'], ['table', 'Stat table']]} onChange={value => setBlock(current => ({ ...current, config: { ...current.config, chart_type: value as 'dumbbell' | 'radar' | 'table' } }))} /> : null}
                    {block.visual_type === 'custom_chart' && block.config.chart_type === 'scatter' ? <div className="mt-3 grid gap-2 sm:grid-cols-2"><Toggle checked={block.config.filters.labels} label="Plot labels" onChange={checked => setBlock(current => ({ ...current, config: { ...current.config, filters: { ...current.config.filters, labels: checked } } }))} /><Toggle checked={block.config.filters.trendline} label="Trend line" onChange={checked => setBlock(current => ({ ...current, config: { ...current.config, filters: { ...current.config.filters, trendline: checked } } }))} /></div> : null}
                    {block.visual_type === 'custom_chart' && block.config.chart_type === 'bar' ? <div className="mt-3 grid gap-3 sm:grid-cols-2"><label><FieldLabel>Ranking</FieldLabel><select value={block.config.filters.bar_window} onChange={event => setBlock(current => ({ ...current, config: { ...current.config, filters: { ...current.config.filters, bar_window: event.target.value as 'top' | 'bottom' | 'all' } } }))} className={inputClass}><option value="top">Top</option><option value="bottom">Bottom</option><option value="all">All</option></select></label><label><FieldLabel>Number of bars</FieldLabel><input type="number" min="5" max="20" value={block.config.filters.bar_count} onChange={event => setBlock(current => ({ ...current, config: { ...current.config, filters: { ...current.config.filters, bar_count: Number(event.target.value) } } }))} className={inputClass} /></label></div> : null}
                    {block.visual_type === 'custom_chart' && block.config.chart_type === 'scatter' ? (
                      <div className="mt-3 grid gap-3 sm:grid-cols-2">
                        <MetricSelect label="X axis" value={effectiveMetricKeys[0] ?? ''} metrics={metricOptions} disabled={metricQueryResult.isLoading} onChange={value => changeScatterMetric(0, value)} />
                        <MetricSelect label="Y axis" value={effectiveMetricKeys[1] ?? ''} metrics={metricOptions} disabled={metricQueryResult.isLoading} onChange={value => changeScatterMetric(1, value)} />
                      </div>
                    ) : block.visual_type === 'custom_chart' && block.config.chart_type === 'bar' ? (
                      <div className="mt-3">
                        <MetricSelect label="Metric" value={effectiveMetricKeys[0] ?? ''} metrics={metricOptions} disabled={metricQueryResult.isLoading} onChange={changeBarMetric} />
                      </div>
                    ) : (
                      <>
                        <div className="relative mt-3"><Search className="pointer-events-none absolute left-3 top-3 size-3.5 text-ink-muted" /><input value={metricQuery} onChange={event => setMetricQuery(event.target.value)} className={`${inputClass} pl-9`} placeholder="Find a metric…" /></div>
                        <div className="mt-2 max-h-56 overflow-y-auto border border-line bg-mat/40">
                          {metricQueryResult.isLoading || comparisonDetailsQuery.isLoading ? <LoadingLine label="Loading compatible metrics" /> : filteredMetrics.map(metric => <MetricOption key={metric.key} metric={metric} selectedIndex={effectiveMetricKeys.indexOf(metric.key)} disabled={!effectiveMetricKeys.includes(metric.key) && effectiveMetricKeys.length >= metricMaximum(block)} onClick={() => toggleMetric(metric.key)} />)}
                        </div>
                        {effectiveMetricKeys.length ? <p className="mt-2 text-[9px] leading-4 text-ink-muted">{effectiveMetricKeys.length} selected · click a selected metric to remove it.</p> : null}
                      </>
                    )}
                    {block.visual_type === 'custom_chart' && block.config.chart_type !== 'radar' ? (
                      <div className="mt-4">
                        <FieldLabel>Highlights</FieldLabel>
                        <button
                          type="button"
                          onClick={() => setPinPickerOpen(true)}
                          disabled={!customPinModel}
                          className={`border px-3 py-2 text-[10px] font-bold uppercase tracking-[0.12em] transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${(customPinModel?.pinnedIds.length ?? 0) > 0 ? 'border-electric bg-electric-dim/40 text-electric' : 'border-line-bright bg-panel text-ink hover:border-electric'}`}
                        >
                          {customPinModel?.pinnedIds.length ? `${customPinModel.pinnedIds.length} pinned` : 'Pin entities'}
                        </button>
                        <p className="mt-2 text-[9px] leading-4 text-ink-muted">Pinned entities stay visually distinct across scatter and bar charts, and keep their bar in view even outside the ranked slice.</p>
                      </div>
                    ) : null}
                  </Section> : null}
                </div>
              ) : (
                <div className="space-y-6">
                  <label><FieldLabel>Visual title</FieldLabel><input value={block.title} maxLength={240} onChange={event => setBlock(current => ({ ...current, title: event.target.value }))} className={inputClass} placeholder="A claim, not just a chart name" /></label>
                  <label><FieldLabel>Caption</FieldLabel><textarea value={block.caption} maxLength={2000} onChange={event => setBlock(current => ({ ...current, caption: event.target.value }))} className="min-h-24 w-full resize-y border border-line-bright bg-mat p-3 text-xs leading-5 text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none" placeholder="What should the reader notice?" /></label>
                  <label><FieldLabel>Alt text</FieldLabel><textarea value={block.alt} maxLength={1000} onChange={event => setBlock(current => ({ ...current, alt: event.target.value }))} className="min-h-24 w-full resize-y border border-line-bright bg-mat p-3 text-xs leading-5 text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none" placeholder="Describe the conclusion and important values for someone who cannot see the visual." /><span className="mt-1.5 block text-[9px] leading-4 text-ink-muted">Required. Describe the insight, not the colours or shape.</span></label>
                  <div className="grid gap-4 sm:grid-cols-2"><label><FieldLabel>Source note</FieldLabel><input value={block.source_note} maxLength={1000} onChange={event => setBlock(current => ({ ...current, source_note: event.target.value }))} className={inputClass} /></label><label><FieldLabel>Data as of</FieldLabel><input type="date" value={block.data_as_of} onChange={event => setBlock(current => ({ ...current, data_as_of: event.target.value }))} className={inputClass} /></label></div>
                </div>
              )}
            </div>

            <div className="min-h-0 overflow-y-auto bg-mat/45 p-5 sm:p-8">
              <div className="mx-auto max-w-4xl"><p className="mb-4 font-mono text-[7px] uppercase tracking-[0.2em] text-ink-muted">Article preview</p><VisualAnalysisBlock block={effectiveBlock} editor /></div>
            </div>
          </div>
        )}

        {step > 1 ? <footer className="flex min-h-16 items-center justify-between gap-4 border-t border-line bg-panel px-4 sm:px-6">
          <button type="button" onClick={() => setStep(step === 3 ? 2 : 1)} className="text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted hover:text-ink">Back</button>
          {step === 2 ? <button type="button" disabled={!configurationComplete(effectiveBlock)} onClick={continueToDetails} className="inline-flex h-10 items-center gap-2 bg-electric px-5 text-[8px] font-black uppercase tracking-[0.15em] text-mat hover:bg-ink disabled:cursor-not-allowed disabled:opacity-35">Add context <ArrowRight className="size-3.5" /></button> : <button type="button" disabled={!detailsComplete(effectiveBlock)} onClick={finish} className="inline-flex h-10 items-center gap-2 bg-electric px-5 text-[8px] font-black uppercase tracking-[0.15em] text-mat hover:bg-ink disabled:cursor-not-allowed disabled:opacity-35"><Check className="size-3.5" /> Insert visual</button>}
        </footer> : null}
      </div>

      <VisualiserEntityPicker
        open={pinPickerOpen}
        title={`Highlight ${block.config.entity_kind === 'player' ? 'players' : 'teams'}`}
        description="Pinned entities stay visually distinct across scatter and bar charts. Labels will show only pinned entities on large scatter cohorts."
        options={customPinModel?.options ?? []}
        selectedIds={customPinModel?.pinnedIds ?? []}
        groupSelected
        selectedSectionLabel="Pinned"
        clearAllLabel="Unpin all"
        closeLabel="Done"
        isLoading={customCohortQuery.isLoading}
        isError={customCohortQuery.isError}
        onChange={setPinnedEntities}
        onClose={() => setPinPickerOpen(false)}
      />
    </div>
  )
}

function VisualTypeCard({ option, onClick }: { option: typeof VISUAL_TYPES[number]; onClick: () => void }) {
  const Icon = option.icon
  return <button type="button" onClick={onClick} className="group min-h-48 border border-line bg-mat/45 p-5 text-left transition-[border-color,background-color,transform] hover:-translate-y-0.5 hover:border-electric hover:bg-electric-dim/20 focus-visible:-translate-y-0.5"><div className="grid size-10 place-items-center border border-electric/25 bg-electric-dim/40 text-electric"><Icon className="size-4" /></div><h3 className="mt-6 text-base font-bold text-ink">{option.label}</h3><p className="mt-2 text-[11px] leading-5 text-ink-dim">{option.description}</p><p className="mt-5 font-mono text-[7px] uppercase tracking-[0.15em] text-ink-muted group-hover:text-electric">{option.hint}</p></button>
}

function EntityOption({ entity, selected, disabled, multiple, onClick }: { entity: SearchPlayerEntity | SearchTeamEntity; selected: boolean; disabled: boolean; multiple: boolean; onClick: () => void }) {
  const player = 'canonical_player_id' in entity
  const name = player ? entity.canonical_player_name : entity.canonical_team_name
  const membership = entity.memberships[0]
  const meta = player ? `${(membership as SearchPlayerMembership)?.canonical_team_name || membership?.competition || 'No current club'} · ${(membership as SearchPlayerMembership)?.position_group || ''}` : `${membership?.competition || ''} · ${(membership as SearchTeamMembership)?.rank ? `#${(membership as SearchTeamMembership).rank}` : 'Team'}`
  return <button type="button" disabled={disabled} onClick={onClick} className={`flex max-w-full items-center gap-2 border px-3 py-2 text-left disabled:opacity-30 ${selected ? 'border-electric bg-electric text-mat' : 'border-line-bright bg-panel text-ink hover:border-electric'}`}><span className="min-w-0"><strong className="block truncate text-[10px]">{name}</strong><span className={`mt-0.5 block truncate font-mono text-[7px] uppercase tracking-[0.08em] ${selected ? 'text-mat/70' : 'text-ink-muted'}`}>{meta}</span></span>{multiple && selected ? <Check className="size-3 shrink-0" /> : null}</button>
}

function MetricOption({ metric, selectedIndex, disabled, onClick }: { metric: MetricOptionValue; selectedIndex: number; disabled: boolean; onClick: () => void }) {
  return <button type="button" disabled={disabled} onClick={onClick} className={`flex w-full items-center justify-between gap-3 border-b border-line px-3 py-2.5 text-left last:border-0 disabled:opacity-30 ${selectedIndex >= 0 ? 'bg-electric-dim/40' : 'hover:bg-panel'}`}><span className="min-w-0"><strong className="block truncate text-[11px] text-ink">{metric.label}</strong><span className="mt-1 block font-mono text-[7px] uppercase tracking-[0.1em] text-ink-muted">{metric.group}</span></span><span className={`grid size-5 shrink-0 place-items-center border font-mono text-[8px] ${selectedIndex >= 0 ? 'border-electric bg-electric text-mat' : 'border-line-bright text-transparent'}`}>{selectedIndex >= 0 ? selectedIndex + 1 : <Check className="size-3" />}</span></button>
}

function MetricSelect({ label, value, metrics, disabled, onChange }: { label: string; value: string; metrics: MetricOptionValue[]; disabled: boolean; onChange: (value: string) => void }) {
  const groups = new Map<string, MetricOptionValue[]>()
  for (const metric of metrics) {
    const group = groups.get(metric.group)
    if (group) group.push(metric)
    else groups.set(metric.group, [metric])
  }
  return <label><FieldLabel>{label}</FieldLabel><select value={value} disabled={disabled || metrics.length === 0} onChange={event => onChange(event.target.value)} className={inputClass}><option value="" disabled>{disabled ? 'Loading metrics…' : 'Choose metric…'}</option>{[...groups].map(([group, options]) => <optgroup key={group} label={group}>{options.map(metric => <option key={metric.key} value={metric.key}>{metric.label}</option>)}</optgroup>)}</select></label>
}

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return <section><h3 className="font-mono text-[8px] uppercase tracking-[0.18em] text-electric">{title}</h3><p className="mt-2 text-[11px] leading-5 text-ink-dim">{description}</p><div className="mt-4">{children}</div></section>
}

function Segmented({ value, options, onChange, disabled = false, disabledOptions = [] }: { value: string; options: Array<[string, string]>; onChange: (value: string) => void; disabled?: boolean; disabledOptions?: string[] }) {
  return <div className="grid border border-line bg-mat p-1" style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}>{options.map(([option, label]) => <button key={option} type="button" disabled={disabled || disabledOptions.includes(option)} onClick={() => onChange(option)} className={`min-h-8 px-2 text-[8px] font-bold uppercase tracking-[0.1em] disabled:cursor-not-allowed disabled:opacity-30 ${value === option ? 'bg-electric text-mat' : 'text-ink-muted hover:text-ink'}`}>{label}</button>)}</div>
}

function Toggle({ checked, label, onChange }: { checked: boolean; label: string; onChange: (checked: boolean) => void }) {
  return <label className="flex min-h-10 cursor-pointer items-center justify-between border border-line bg-mat px-3 text-[9px] text-ink"><span>{label}</span><input type="checkbox" checked={checked} onChange={event => onChange(event.target.checked)} className="accent-electric" /></label>
}

function StepDots({ step }: { step: number }) {
  return <div className="hidden items-center gap-1.5 sm:flex" aria-label={`Step ${step} of 3`}>{[1, 2, 3].map(value => <span key={value} className={`h-1.5 transition-[width,background-color] ${value === step ? 'w-5 bg-electric' : value < step ? 'w-1.5 bg-mint' : 'w-1.5 bg-line-bright'}`} />)}</div>
}

function LoadingLine({ label }: { label: string }) {
  return <p className="flex items-center justify-center gap-2 px-3 py-8 text-[9px] uppercase tracking-[0.12em] text-ink-muted"><Loader2 className="size-3 animate-spin text-electric" />{label}</p>
}

function FieldLabel({ children }: { children: string }) {
  return <span className="mb-1.5 block font-mono text-[8px] uppercase tracking-[0.14em] text-ink-muted">{children}</span>
}

function referenceForEntity(entity: SearchPlayerEntity | SearchTeamEntity, first?: VisualEntityReference): VisualEntityReference | null {
  const memberships = entity.memberships
  const membership = first
    ? memberships.find(item => (item.aggregate_season === first.season_label || item.season === first.season_label) && item.competition_type === 'domestic_league' && (!first.position_group || !('position_group' in item) || item.position_group === first.position_group))
      ?? memberships.find(item => (item.aggregate_season === first.season_label || item.season === first.season_label) && (!first.position_group || !('position_group' in item) || item.position_group === first.position_group))
      ?? memberships[0]
    : memberships.find(item => item.competition_type === 'domestic_league' && item.include_in_domestic_aggregates)
      ?? memberships.find(item => item.competition_type === 'domestic_league')
      ?? memberships[0]
  if (!membership) return null
  if ('canonical_player_id' in entity) {
    const playerMembership = membership as SearchPlayerMembership
    return { kind: 'player', id: entity.canonical_player_id, name: entity.canonical_player_name, source_competition: membership.competition, season_label: membership.season, competition_season_id: membership.competition_season_id, position_group: playerMembership.position_group, team_name: playerMembership.canonical_team_name ?? '' }
  }
  return { kind: 'team', id: entity.canonical_team_id, name: entity.canonical_team_name, source_competition: membership.competition, season_label: membership.season, competition_season_id: membership.competition_season_id }
}

function referenceFromMembership(entity: SearchPlayerEntity | SearchTeamEntity, membership: SearchPlayerMembership | SearchTeamMembership): VisualEntityReference | null {
  if ('canonical_player_id' in entity && 'position_group' in membership) {
    return { kind: 'player', id: entity.canonical_player_id, name: entity.canonical_player_name, source_competition: membership.competition, season_label: membership.season, competition_season_id: membership.competition_season_id, position_group: membership.position_group, team_name: membership.canonical_team_name ?? '' }
  }
  if ('canonical_team_id' in entity) {
    return { kind: 'team', id: entity.canonical_team_id, name: entity.canonical_team_name, source_competition: membership.competition, season_label: membership.season, competition_season_id: membership.competition_season_id }
  }
  return null
}

function contextForReference(reference: VisualEntityReference, entity: SearchPlayerEntity | SearchTeamEntity, catalog: CompetitionCatalogEntry[]) {
  return contextForScope(reference, entity, 'league', catalog)
}

function contextForScope(reference: VisualEntityReference, entity: SearchPlayerEntity | SearchTeamEntity | undefined, scopeKind: VisualScopeKind, catalog: CompetitionCatalogEntry[]) {
  const membership = entity?.memberships.find(item => item.competition_season_id === reference.competition_season_id)
  const code = scopeKind === 'league' ? reference.source_competition : scopeKind === 'big5' ? 'BIG5' : 'ALL'
  const catalogEntry = catalog.find(item => item.code === code)
  const seasonLabel = scopeKind === 'league' ? reference.season_label : membership?.aggregate_season ?? reference.season_label
  const scopeLabel = scopeKind === 'league' ? catalogEntry?.name ?? reference.source_competition : scopeKind === 'big5' ? 'Big 5 leagues' : 'All available leagues'
  return { scope_kind: scopeKind, scope_code: code, scope_label: scopeLabel, season_label: seasonLabel }
}

function contextForCatalogEntry(entry: CompetitionCatalogEntry) {
  const scopeKind: VisualScopeKind = entry.code === 'BIG5' ? 'big5' : entry.code === 'ALL' ? 'all' : entry.competition_type === 'aggregate' ? 'all' : 'competition'
  return { scope_kind: scopeKind, scope_code: entry.code, scope_label: entry.name, season_label: entry.seasons[0]?.label ?? '' }
}

function customScopeOptions(catalog: CompetitionCatalogEntry[]): CompetitionCatalogEntry[] {
  return catalog.filter(entry => entry.seasons.length > 0 && (entry.group === 'aggregate' || entry.group === 'domestic' || entry.group === 'european'))
}

function defaultCustomScope(catalog: CompetitionCatalogEntry[]): CompetitionCatalogEntry | undefined {
  return customScopeOptions(catalog).find(entry => entry.code === 'BIG5') ?? customScopeOptions(catalog)[0]
}

function seasonForScope(membership: SearchPlayerMembership | SearchTeamMembership, scopeKind: VisualScopeKind): string {
  return scopeKind === 'league' || scopeKind === 'competition' ? membership.season : membership.aggregate_season ?? membership.season
}

function membershipForSeasonAndScope(
  memberships: Array<SearchPlayerMembership | SearchTeamMembership>,
  seasonLabel: string,
  scopeKind: VisualScopeKind,
  scopeCode: string,
  positionGroup?: string,
) {
  const candidates = memberships.filter(membership =>
    seasonForScope(membership, scopeKind) === seasonLabel
    && (!positionGroup || !('position_group' in membership) || membership.position_group === positionGroup),
  )
  if (scopeKind === 'league' || scopeKind === 'competition') {
    return candidates.find(membership => membership.competition === scopeCode)
  }
  return candidates.find(membership => membership.competition_type === 'domestic_league' && membership.include_in_domestic_aggregates)
    ?? candidates.find(membership => membership.competition_type === 'domestic_league')
    ?? candidates[0]
}

function seasonsForSelectedEntity(block: VisualArticleBlock, data?: { players: SearchPlayerEntity[]; teams: SearchTeamEntity[] }): string[] {
  const first = block.config.entities[0]
  if (!first) return []
  const source = findSourceEntity(first, data)
  return [...new Set((source?.memberships ?? [])
    .filter(membership => block.config.context.scope_kind !== 'league' || membership.competition === first.source_competition)
    .map(membership => seasonForScope(membership, block.config.context.scope_kind)))]
}

function findSourceEntity(reference: VisualEntityReference, data?: { players: SearchPlayerEntity[]; teams: SearchTeamEntity[] }): SearchPlayerEntity | SearchTeamEntity | undefined {
  return reference.kind === 'player' ? data?.players.find(entity => entity.canonical_player_id === reference.id) : data?.teams.find(entity => entity.canonical_team_id === reference.id)
}

interface MetricOptionValue { key: string; label: string; group: string }

function buildMetricOptions(payload?: { kind: 'player'; meta?: StatMeta } | { kind: 'team'; meta?: TeamStatMeta }): MetricOptionValue[] {
  if (!payload?.meta) return []
  if (payload.kind === 'player') {
    const seen = new Set<string>()
    return Object.entries(payload.meta.metrics).flatMap(([key, metric]) => {
      const canonical = canonicalProfileMetricKey(key)
      if (seen.has(canonical)) return []
      seen.add(canonical)
      return [{ key: canonical, label: stripPer90Suffix(metric.label), group: payload.meta?.metric_groups[metric.group] ?? metric.group }]
    })
  }
  return Object.entries(payload.meta.stats).map(([key, metric]) => ({ key, label: metric.label, group: payload.meta?.stat_groups[metric.group] ?? metric.group }))
}

function comparisonMetricAvailable(player: PlayerDetailResponse, key: string): boolean {
  return player.metrics[key] != null || player.comparison_percentiles?.[key] != null || player.scope_percentiles?.[key] != null || player.percentiles[key] != null
}

function visualDefaultMetricKeys(block: VisualArticleBlock, metrics: MetricOptionValue[], players?: PlayerDetailResponse[]): string[] {
  const available = new Set(metrics.map(metric => metric.key))
  if (!available.size) return []
  if (block.visual_type === 'player_radar') {
    const position = block.config.entities[0]?.position_group ?? 'MID'
    return defaultPizzaMetricKeys(position as PositionGroup).filter(key => available.has(key)).slice(0, metricMaximum(block))
  }
  if (block.visual_type === 'player_comparison' && players?.[0]?.meta) {
    const pack = comparisonAxisPacksForPosition(players[0].position_group, players[0].meta, key => players.every(player => comparisonMetricAvailable(player, key)))[0]
    if (pack) return pack.keys
  }
  const count = block.visual_type === 'stat_card' ? 4 : block.visual_type === 'custom_chart' && block.config.chart_type === 'scatter' ? 2 : block.visual_type === 'custom_chart' && block.config.chart_type === 'bar' ? 1 : Math.min(6, metrics.length)
  return metrics.slice(0, count).map(metric => metric.key)
}

function entityMaximum(block: VisualArticleBlock): number {
  return block.visual_type === 'player_comparison' ? 3 : 1
}

function metricMaximum(block: VisualArticleBlock): number {
  if (block.visual_type === 'stat_card') return 4
  if (block.visual_type === 'custom_chart' && block.config.chart_type === 'scatter') return 2
  if (block.visual_type === 'custom_chart' && block.config.chart_type === 'bar') return 1
  return 12
}

function metricMinimum(block: VisualArticleBlock): number {
  if (block.visual_type === 'similar_players') return 0
  if (block.visual_type === 'custom_chart' && block.config.chart_type === 'scatter') return 2
  if (block.visual_type === 'player_radar' || block.visual_type === 'player_comparison' || (block.visual_type === 'custom_chart' && block.config.chart_type === 'radar')) return 3
  return 1
}

function configurationComplete(block: VisualArticleBlock): boolean {
  const minimumEntities = block.visual_type === 'player_comparison' ? 2 : block.visual_type === 'custom_chart' ? 0 : 1
  const minimumMetrics = metricMinimum(block)
  return Boolean(block.config.context.scope_code && block.config.context.season_label && block.config.entities.length >= minimumEntities && block.config.metric_keys.length >= minimumMetrics)
}

function detailsComplete(block: VisualArticleBlock): boolean {
  return configurationComplete(block) && Boolean(block.alt.trim() && block.source_note.trim() && block.data_as_of)
}

function subjectDescription(block: VisualArticleBlock): string {
  if (block.visual_type === 'player_comparison') return 'Pick the anchor player first, then up to two peers. We keep position and season context aligned.'
  return `Pick the ${block.config.entity_kind} this block is about. Its current context becomes the sensible default.`
}

function metricDescription(block: VisualArticleBlock): string {
  if (block.visual_type === 'custom_chart' && block.config.chart_type === 'scatter') return 'Choose X first and Y second. The cohort provides every plotted point.'
  if (block.visual_type === 'custom_chart' && block.config.chart_type === 'bar') return 'Choose the metric to rank from highest to lowest.'
  if (block.visual_type === 'custom_chart' && block.config.chart_type === 'radar') return 'Choose at least three shared axes; highlighted entities become the shapes.'
  return `Choose the metrics that carry the argument. Up to ${metricMaximum(block)} can be shown.`
}

function suggestedTitle(block: VisualArticleBlock): string {
  const names = block.config.entities.map(entity => entity.name)
  if (block.visual_type === 'similar_players') return `Players most similar to ${names[0]}`
  if (block.visual_type === 'player_comparison') return names.join(' vs ')
  if (block.visual_type === 'player_radar') return `${names[0]} percentile profile`
  if (block.visual_type === 'stat_card') return `${names[0]} key numbers`
  return `${block.config.entity_kind === 'player' ? 'Player' : 'Team'} ${block.config.chart_type} · ${block.config.context.scope_label}`
}

function suggestedAlt(block: VisualArticleBlock, metrics: MetricOptionValue[]): string {
  const labels = block.config.metric_keys.map(key => metrics.find(metric => metric.key === key)?.label ?? key)
  const names = block.config.entities.map(entity => entity.name).join(', ')
  if (block.visual_type === 'similar_players') return `Ranked list of players with profiles most similar to ${names} in ${block.config.context.scope_label}, ${block.config.context.season_label}.`
  return `${suggestedTitle(block)} for ${block.config.context.scope_label}, ${block.config.context.season_label}, using ${labels.join(', ')}. Add the main conclusion before publishing.`
}

function positionName(position: string): string {
  return ({ FWD: 'forwards', MID: 'midfielders', DEF: 'defenders', GK: 'goalkeepers' } as Record<string, string>)[position] ?? 'players'
}
