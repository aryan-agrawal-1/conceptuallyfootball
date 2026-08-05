import { forwardRef, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ArrowLeft, ArrowRight, GripVertical, RotateCcw, X } from 'lucide-react'
import { HudCornerMarks, HudPill } from '../hud/Hud'
import { ProfilePizzaSvg } from './ProfilePizzaSection'
import { ProfileDistributionPanel } from './ProfileDistributionPanel'
import { ShareActions, type ShareActionBusy } from '../share/ShareActions'
import {
  createPngExport,
  handoffPngExport,
  pngFileName,
  type PngExportPolicy,
} from '../share/pngExport'
import { formatValue } from '../../lib/format'
import { getPercentileTextColor, metricSemanticColor } from '../../lib/heatmap'
import {
  buildDefaultProfileExportPreset,
  curatedProfileMetricKeys,
  hydrateProfileExportPreset,
  isUsableExportMetric,
  profileExportLabelForKey,
  PROFILE_EXPORT_STAT_LIMIT,
  saveProfileExportPreset,
  type ProfileExportOrientation,
  type ProfileExportPreset,
  type ProfileExportTheme,
  type ProfileExportTile,
} from '../../lib/profileExport'
import {
  PIZZA_SLICE_MIN,
  PIZZA_SLICE_SOFT_MAX,
  barKindForMetricKey,
  canonicalProfileMetricKey,
  dedupeCanonicalMetricKeys,
  moveMetricKey,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { getTeamLogoPath } from '../../lib/teamLogos'
import { BRAND_DOMAIN, BRAND_NAME_UPPER, BRAND_SLUG } from '../../lib/brand'
import { shortPlayerName } from '../../lib/entityLabels'
import { cn } from '../../lib/utils'
import type {
  GalaxyEdge,
  MetricSemanticColor,
  PlayerRow,
  ProfileDistributionPayload,
  StatMeta,
} from '../../types/api'

interface PlayerProfileExportModalProps {
  player: PlayerRow
  meta: StatMeta
  initialRateMode: ProfileRateMode
  percentileMap?: Record<string, number | null>
  percentileScopeLabel?: string
  distributions?: ProfileDistributionPayload
  similarEdges?: GalaxyEdge[]
  similarIsLoading?: boolean
  similarIsError?: boolean
  similarScopeLabel?: string
  onClose: () => void
}

interface ResolvedTile extends ProfileExportTile {
  available: boolean
  value: number | null
  percentile: number | null
  formatUnit: Parameters<typeof formatValue>[1]
}

const MIN_STATS = PROFILE_EXPORT_STAT_LIMIT
const MAX_STATS = PROFILE_EXPORT_STAT_LIMIT

const PROFILE_EXPORT_BASE_DIMENSIONS: Record<
  ProfileExportOrientation,
  { width: number; height: number }
> = {
  portrait: { width: 1080, height: 1350 },
  landscape: { width: 1600, height: 900 },
}

function profileExportDimensions(preset: ProfileExportPreset): { width: number; height: number } {
  const base = PROFILE_EXPORT_BASE_DIMENSIONS[preset.orientation]
  const lowerPanelCount = Number(preset.notesEnabled) + Number(preset.similarEnabled)
  const growth =
    lowerPanelCount === 2 || preset.similarEnabled
      ? 1.45
      : lowerPanelCount === 1
        ? 1.35
        : preset.orientation === 'landscape' && preset.chartEnabled
          ? 1.08
          : 1
  return {
    width: Math.round(base.width * growth),
    height: Math.round(base.height * growth),
  }
}

const PROFILE_EXPORT_POLICIES: Record<ProfileExportOrientation, PngExportPolicy> = {
  portrait: {
    name: 'portrait player profile',
    pixelRatios: [1, 0.9, 0.8, 0.75],
    minWidth: 810,
    minHeight: 1012,
    minTextPixels: 8,
  },
  landscape: {
    name: 'landscape player profile',
    pixelRatios: [1, 0.9],
    minWidth: 1440,
    minHeight: 810,
    minTextPixels: 8,
  },
}

const POSITION_COHORT_LABEL: Record<PlayerRow['position_group'], string> = {
  FWD: 'forwards',
  MID: 'midfielders',
  DEF: 'defenders',
  GK: 'goalkeepers',
  UNK: 'players',
}

const THEME_LABEL: Record<ProfileExportTheme, string> = {
  'conceptually-football': 'Conceptually Football',
  boring: 'Boring',
}

const ORIENTATION_LABEL: Record<ProfileExportOrientation, string> = {
  portrait: 'Portrait 4:5',
  landscape: 'Landscape 16:9',
}

function layoutStatCap(): number {
  return MAX_STATS
}

function notesLimit(chartEnabled: boolean): number {
  return chartEnabled ? 280 : 500
}

function reorderTile(list: ProfileExportTile[], from: number, to: number): ProfileExportTile[] {
  const next = [...list]
  if (from < 0 || to < 0 || from >= next.length || to >= next.length || from === to) return list
  const [item] = next.splice(from, 1)
  next.splice(to, 0, item)
  return next
}

export function PlayerProfileExportModal({
  player,
  meta,
  initialRateMode,
  percentileMap = player.percentiles,
  percentileScopeLabel = player.competition_code,
  distributions,
  similarEdges = [],
  similarIsLoading = false,
  similarIsError = false,
  similarScopeLabel = `${player.competition_code} ${player.season_label}`,
  onClose,
}: PlayerProfileExportModalProps) {
  const exportRef = useRef<HTMLDivElement>(null)
  const defaultTitle = shortPlayerName(player.canonical_player_name)
  const [preset, setPreset] = useState<ProfileExportPreset>(() =>
    hydrateProfileExportPreset(player, meta, initialRateMode),
  )
  const [title, setTitle] = useState(defaultTitle)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState<ShareActionBusy>(null)
  const [dragIndex, setDragIndex] = useState<number | null>(null)

  useEffect(() => {
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = previous
    }
  }, [])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  const resolvedTiles = useMemo<ResolvedTile[]>(
    () =>
      preset.stats.map(tile => {
        if (!isUsableExportMetric(player, meta, preset.rateMode, tile.key)) {
          return {
            ...tile,
            available: false,
            value: null,
            percentile: null,
            formatUnit: undefined,
          }
        }
        const resolved = resolveProfileMetric(
          player,
          preset.rateMode,
          barKindForMetricKey(tile.key),
          meta,
          percentileMap,
        )
        return {
          ...tile,
          available: true,
          value: resolved.value,
          percentile: resolved.percentile,
          formatUnit: resolved.formatUnit,
        }
      }),
    [meta, percentileMap, player, preset.rateMode, preset.stats],
  )

  const validTiles = useMemo(() => resolvedTiles.filter(tile => tile.available), [resolvedTiles])
  const selectedKeys = useMemo(() => new Set(preset.stats.map(tile => tile.key)), [preset.stats])
  const statCap = layoutStatCap()
  const availableMetricKeys = useMemo(
    () =>
      validTiles.length >= statCap
        ? []
        : curatedProfileMetricKeys(player.position_group).filter(
            key => !selectedKeys.has(key) && isUsableExportMetric(player, meta, preset.rateMode, key),
          ),
    [meta, player, preset.rateMode, selectedKeys, statCap, validTiles.length],
  )
  const chartMetricKeys = useMemo(
    () =>
      dedupeCanonicalMetricKeys(
        preset.chartMetricKeys.filter(key =>
          isUsableExportMetric(player, meta, preset.rateMode, key),
        ),
      ),
    [meta, player, preset.chartMetricKeys, preset.rateMode],
  )

  const noteMax = notesLimit(preset.chartEnabled)
  const overCap = validTiles.length > statCap
  const underMin = validTiles.length < MIN_STATS
  const chartInvalid = preset.chartEnabled && chartMetricKeys.length < PIZZA_SLICE_MIN
  const notesInvalid = preset.notesEnabled && notes.length > noteMax
  const distributionInvalid =
    preset.distributionEnabled && (!preset.chartEnabled || !distributions)
  const similarInvalid = preset.similarEnabled && (similarIsLoading || similarIsError)
  const invalidReason = overCap
    ? `This layout supports up to ${statCap} stat tiles. Remove ${validTiles.length - statCap} to export.`
    : underMin
      ? `Select at least ${MIN_STATS} available stat tiles to export.`
      : chartInvalid
        ? `Select at least ${PIZZA_SLICE_MIN} available profile chart axes.`
        : distributionInvalid
          ? 'Distribution export requires an available profile chart cohort.'
          : similarInvalid
            ? similarIsLoading
              ? 'Similar players are still loading for the selected comparison cohort.'
              : 'Similar players are unavailable for the selected comparison cohort.'
            : notesInvalid
              ? `Notes must be ${noteMax} characters or fewer for this layout.`
              : null
  const canExport = !invalidReason && !busy

  const fileName = pngFileName(
    BRAND_SLUG,
    'player-profile',
    player.canonical_player_name,
    player.season_label,
    preset.theme,
  )

  function updatePreset(next: Partial<ProfileExportPreset>) {
    setPreset(prev => {
      const merged = { ...prev, ...next }
      return merged.chartEnabled && merged.distributionEnabled
        ? { ...merged, orientation: 'landscape' }
        : merged
    })
  }

  function updateStatLabel(key: string, label: string) {
    setPreset(prev => ({
      ...prev,
      stats: prev.stats.map(tile => (tile.key === key ? { ...tile, label } : tile)),
    }))
  }

  function removeStat(key: string) {
    setPreset(prev => ({
      ...prev,
      stats: prev.stats.filter(tile => tile.key !== key),
    }))
  }

  function addStat(key: string) {
    if (validTiles.length >= statCap) return
    setPreset(prev => ({
      ...prev,
      stats: [...prev.stats, { key, label: profileExportLabelForKey(key, meta) }],
    }))
  }

  function reorderStat(from: number, to: number) {
    setPreset(prev => ({ ...prev, stats: reorderTile(prev.stats, from, to) }))
    setDragIndex(to)
  }

  function resetDefaults() {
    setPreset(buildDefaultProfileExportPreset(player, meta, initialRateMode))
    setTitle(defaultTitle)
    setNotes('')
  }

  function persistExportPreset() {
    saveProfileExportPreset(player.position_group, {
      ...preset,
      stats: validTiles.map(tile => ({ key: tile.key, label: tile.label })),
      chartMetricKeys,
      notesEnabled: preset.notesEnabled,
      similarEnabled: preset.similarEnabled,
      distributionEnabled:
        preset.chartEnabled && Boolean(distributions) && preset.distributionEnabled,
      showPercentiles: player.eligibility.percentiles_eligible && preset.showPercentiles,
    })
  }

  async function handleExport(mode: 'share' | 'download') {
    if (!canExport) return
    try {
      setBusy(mode)
      const artifact = await createPngExport({
        resolveNode: () => exportRef.current,
        fileName,
        policy: PROFILE_EXPORT_POLICIES[preset.orientation],
        backgroundColor: preset.theme === 'boring' ? '#eef1f6' : '#070810',
      })
      await handoffPngExport(artifact, {
        mode,
        title,
        text: `${player.season_label} · ${player.canonical_team_name ?? 'No club'} profile`,
      })
      persistExportPreset()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="fixed inset-0 z-[120] flex items-center justify-center bg-mat/85 px-3 py-3 backdrop-blur-xl sm:px-6 sm:py-6">
      <div className="relative flex h-[calc(100svh-24px)] w-full max-w-[1680px] flex-col overflow-hidden border border-electric/25 bg-panel shadow-[0_24px_90px_-24px_rgba(0,0,0,0.9)] sm:h-[calc(100svh-48px)]">
        <HudCornerMarks size="size-3" />
        <div className="flex shrink-0 items-center justify-between gap-4 border-b border-electric/20 bg-electric/5 px-4 py-3">
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.28em] text-electric/80">Player profile export</p>
            <h2 className="truncate text-[18px] font-black text-ink" title={player.canonical_player_name}>
              {shortPlayerName(player.canonical_player_name)}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center border border-control-border text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10"
            aria-label="Close export modal"
          >
            <X size={17} />
          </button>
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden xl:grid-cols-[440px_minmax(0,1fr)]">
          <aside className="min-h-0 overflow-y-auto border-b border-electric/15 bg-mat/55 xl:border-b-0 xl:border-r">
            <div className="flex flex-col gap-5 p-4">
              <EditorSection title="Identity">
                <label className="flex flex-col gap-1.5">
                  <span className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">Title</span>
                  <input
                    value={title}
                    onChange={e => setTitle(e.target.value)}
                    className="border border-electric/20 bg-panel px-3 py-2 text-[13px] text-ink outline-none transition-colors focus:border-electric/60"
                  />
                </label>
                <SegmentedControl
                  label="Mode"
                  value={preset.theme}
                  options={(['conceptually-football', 'boring'] as const).map(value => ({
                    value,
                    label: THEME_LABEL[value],
                  }))}
                  onChange={theme => updatePreset({ theme })}
                />
                <SegmentedControl
                  label="Orientation"
                  value={preset.orientation}
                  options={(['portrait', 'landscape'] as const).map(value => ({
                    value,
                    label: ORIENTATION_LABEL[value],
                    disabled:
                      value === 'portrait' &&
                      preset.chartEnabled &&
                      preset.distributionEnabled,
                  }))}
                  onChange={orientation => updatePreset({ orientation })}
                />
                {preset.chartEnabled && preset.distributionEnabled && (
                  <p className="border border-electric/15 bg-electric/[0.04] px-3 py-2 text-[10px] leading-relaxed text-ink-muted">
                    Landscape keeps the profile chart and distributions readable side by side.
                  </p>
                )}
                <SegmentedControl
                  label="Rate"
                  value={preset.rateMode}
                  options={[
                    { value: 'per90', label: 'Per 90' },
                    { value: 'full', label: 'Season' },
                  ]}
                  onChange={rateMode => updatePreset({ rateMode })}
                />
              </EditorSection>

              <EditorSection
                title="Stats"
                meta={`${validTiles.length}/${statCap} selected · min ${MIN_STATS}`}
              >
                <label className="flex items-center justify-between gap-3 border border-electric/10 bg-electric/[0.03] px-3 py-2 text-[11px] text-ink-dim">
                  <span>Show percentile badges</span>
                  <input
                    type="checkbox"
                    checked={preset.showPercentiles}
                    disabled={!player.eligibility.percentiles_eligible}
                    onChange={e => updatePreset({ showPercentiles: e.target.checked })}
                  />
                </label>
                <div className="flex flex-col gap-2">
                  {resolvedTiles.map((tile, index) => (
                    <div
                      key={tile.key}
                      data-stat-row
                      draggable
                      onDragStart={e => {
                        setDragIndex(index)
                        e.dataTransfer.effectAllowed = 'move'
                        const row = e.currentTarget
                        e.dataTransfer.setDragImage(row, 24, 24)
                      }}
                      onDragEnd={() => setDragIndex(null)}
                      onDragOver={e => {
                        e.preventDefault()
                        if (dragIndex == null || dragIndex === index) return
                        reorderStat(dragIndex, index)
                      }}
                      onDrop={() => {
                        setDragIndex(null)
                      }}
                      className={cn(
                        'grid cursor-grab grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-2 border px-2 py-2 transition-[border-color,background-color,box-shadow,transform,opacity]',
                        tile.available
                          ? 'border-electric/15 bg-panel/70'
                          : 'border-ember/30 bg-ember/10',
                        dragIndex === index && 'scale-[1.015] border-electric/60 bg-electric/10 opacity-80 shadow-[0_10px_26px_-14px_rgba(74,158,245,0.85)]',
                      )}
                    >
                      <button
                        type="button"
                        className="grid size-8 cursor-grab place-items-center border border-control-border text-control-fg active:cursor-grabbing active:bg-electric/10"
                        aria-label="Drag to reorder stat"
                      >
                        <GripVertical size={14} />
                      </button>
                      <div className="min-w-0">
                        <input
                          value={tile.label}
                          onChange={e => updateStatLabel(tile.key, e.target.value)}
                          className="w-full border border-transparent bg-transparent px-1 py-1 text-[12px] font-medium text-ink outline-none focus:border-electric/30"
                        />
                        <p className={cn('truncate px-1 text-[10px]', tile.available ? 'text-ink-muted' : 'text-ember')}>
                          {tile.available
                            ? `${formatValue(tile.value, tile.formatUnit)} · ${stripPer90Suffix(meta.metrics[tile.key]?.label ?? tile.key)}`
                            : 'Unavailable for this player'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={() => removeStat(tile.key)}
                        className="grid size-7 place-items-center border border-control-border text-control-fg transition-colors hover:border-ember hover:text-ember active:bg-ember/10"
                        aria-label="Remove stat"
                      >
                        <X size={13} />
                      </button>
                    </div>
                  ))}
                </div>
                <select
                  value=""
                  onChange={e => {
                    if (e.target.value) addStat(e.target.value)
                  }}
                  className="w-full border border-electric/20 bg-panel px-3 py-2 text-[12px] text-ink outline-none focus:border-electric/60"
                >
                  <option value="">{validTiles.length >= statCap ? 'Maximum stats selected' : 'Add available stat...'}</option>
                  {availableMetricKeys.map(key => (
                    <option key={key} value={key}>
                      {profileExportLabelForKey(key, meta)}
                    </option>
                  ))}
                </select>
              </EditorSection>

              <EditorSection title="Profile chart">
                <label className="flex items-center justify-between gap-3 border border-electric/10 bg-electric/[0.03] px-3 py-2 text-[11px] text-ink-dim">
                  <span>Include profile chart</span>
                  <input
                    type="checkbox"
                    checked={preset.chartEnabled}
                    onChange={e => updatePreset({
                      chartEnabled: e.target.checked,
                      distributionEnabled: e.target.checked ? preset.distributionEnabled : false,
                    })}
                  />
                </label>
                <label className="flex items-center justify-between gap-3 border border-electric/10 bg-electric/[0.03] px-3 py-2 text-[11px] text-ink-dim">
                  <span>
                    Include matching distributions
                    <span className="mt-0.5 block text-[9px] text-ink-muted">
                      Uses the wide profile panel
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={preset.distributionEnabled}
                    disabled={!preset.chartEnabled || !distributions}
                    onChange={e => updatePreset({
                      distributionEnabled: e.target.checked,
                      orientation: e.target.checked ? 'landscape' : preset.orientation,
                    })}
                  />
                </label>
                {!player.eligibility.percentiles_eligible && preset.chartEnabled && (
                  <p className="border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-[11px] leading-relaxed text-amber-200">
                    Percentile ranks are unavailable for this player. The chart will render as a raw metric profile.
                  </p>
                )}
                <ChartAxisEditor
                  player={player}
                  meta={meta}
                  rateMode={preset.rateMode}
                  selectedKeys={preset.chartMetricKeys}
                  onChange={chartMetricKeys => updatePreset({
                    chartMetricKeys: dedupeCanonicalMetricKeys(chartMetricKeys),
                  })}
                />
              </EditorSection>

              <EditorSection title="Notes" meta={preset.notesEnabled ? `${notes.length}/${noteMax}` : undefined}>
                <label className="flex items-center justify-between gap-3 border border-electric/10 bg-electric/[0.03] px-3 py-2 text-[11px] text-ink-dim">
                  <span>Include notes</span>
                  <input
                    type="checkbox"
                    checked={preset.notesEnabled}
                    onChange={e => updatePreset({ notesEnabled: e.target.checked })}
                  />
                </label>
                {preset.notesEnabled && (
                  <textarea
                    value={notes}
                    maxLength={noteMax}
                    onChange={e => setNotes(e.target.value)}
                    rows={5}
                    className="w-full resize-none border border-electric/20 bg-panel px-3 py-2 text-[12px] leading-relaxed text-ink outline-none focus:border-electric/60"
                    placeholder="Add a short public-facing note..."
                  />
                )}
              </EditorSection>

              <EditorSection title="Similar players" meta={preset.similarEnabled ? 'Top 3' : undefined}>
                <label className="flex items-center justify-between gap-3 border border-electric/10 bg-electric/[0.03] px-3 py-2 text-[11px] text-ink-dim">
                  <span>Include similar players</span>
                  <input
                    type="checkbox"
                    checked={preset.similarEnabled}
                    onChange={e => updatePreset({ similarEnabled: e.target.checked })}
                  />
                </label>
                {preset.similarEnabled && (
                  <p className="border border-electric/10 bg-panel/45 px-3 py-2 text-[11px] leading-relaxed text-ink-muted">
                    Uses the same similarity model as the player profile page.
                  </p>
                )}
              </EditorSection>
            </div>
          </aside>

          <main className="flex min-h-0 flex-col bg-[#05060c]">
            <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
              <ExportSurfacePreview preset={preset}>
                <PlayerProfileExportSurface
                  player={player}
                  meta={meta}
                  title={title}
                  preset={preset}
                  tiles={validTiles}
                  chartMetricKeys={chartMetricKeys}
                  notes={notes}
                  similarEdges={similarEdges}
                  similarIsLoading={similarIsLoading}
                  similarIsError={similarIsError}
                  similarScopeLabel={similarScopeLabel}
                  previewInvalid={invalidReason}
                  percentileMap={percentileMap}
                  percentileScopeLabel={percentileScopeLabel}
                  distributions={distributions}
                />
              </ExportSurfacePreview>
            </div>

            <div className="flex shrink-0 flex-col gap-3 border-t border-electric/20 bg-panel/95 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-h-5 text-[11px] text-ink-muted">
                {invalidReason ? <span className="text-amber-300">{invalidReason}</span> : <span>{fileName}</span>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={resetDefaults}
                  className="flex items-center gap-1.5 border border-control-border px-3 py-2 text-[11px] uppercase tracking-[0.15em] text-control-fg transition-colors hover:border-electric hover:text-control-fg-hover active:bg-electric/10"
                >
                  <RotateCcw size={14} />
                  Reset defaults
                </button>
                <ShareActions
                  busy={busy}
                  disabled={!canExport}
                  disabledReason={invalidReason}
                  onShare={() => handleExport('share')}
                  onDownload={() => handleExport('download')}
                />
              </div>
            </div>
          </main>
        </div>
      </div>

      <div className="fixed left-[-20000px] top-0 pointer-events-none opacity-0" aria-hidden="true">
        <PlayerProfileExportSurface
          ref={exportRef}
          player={player}
          meta={meta}
          title={title}
          preset={preset}
          tiles={validTiles}
          chartMetricKeys={chartMetricKeys}
          notes={notes}
          similarEdges={similarEdges}
          similarIsLoading={similarIsLoading}
          similarIsError={similarIsError}
          similarScopeLabel={similarScopeLabel}
          percentileMap={percentileMap}
          percentileScopeLabel={percentileScopeLabel}
          distributions={distributions}
        />
      </div>
    </div>
  )
}

function ExportSurfacePreview({
  preset,
  children,
}: {
  preset: ProfileExportPreset
  children: ReactNode
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(0.4)
  const dimensions = profileExportDimensions(preset)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observedContainer = container

    function fitSurface() {
      const width = observedContainer.clientWidth
      const height = observedContainer.clientHeight
      if (!width || !height) return
      setScale(Math.min(1, width / dimensions.width, height / dimensions.height))
    }

    fitSurface()
    const observer = new ResizeObserver(fitSurface)
    observer.observe(observedContainer)
    return () => observer.disconnect()
  }, [dimensions.height, dimensions.width])

  return (
    <div ref={containerRef} className="flex min-h-full w-full items-start justify-center">
      <div
        className="relative shrink-0"
        style={{
          width: dimensions.width * scale,
          height: dimensions.height * scale,
        }}
      >
        <div
          className="absolute left-0 top-0"
          style={{
            width: dimensions.width,
            height: dimensions.height,
            transform: `scale(${scale})`,
            transformOrigin: 'top left',
          }}
        >
          {children}
        </div>
      </div>
    </div>
  )
}

function EditorSection({
  title,
  meta,
  children,
}: {
  title: string
  meta?: string
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[10px] font-bold uppercase tracking-[0.22em] text-electric">{title}</h3>
        {meta && <span className="text-[10px] uppercase tracking-[0.16em] text-ink-muted">{meta}</span>}
      </div>
      {children}
    </section>
  )
}

function SegmentedControl<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string
  value: T
  options: Array<{ value: T; label: string; disabled?: boolean }>
  onChange: (value: T) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">{label}</span>
      <div className="flex flex-wrap gap-2">
        {options.map(option =>
          option.disabled ? (
            <button
              key={option.value}
              type="button"
              disabled
              className="border border-control-border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.15em] text-control-disabled opacity-55"
            >
              {option.label}
            </button>
          ) : (
            <HudPill
              key={option.value}
              active={value === option.value}
              onClick={() => onChange(option.value)}
            >
              {option.label}
            </HudPill>
          ),
        )}
      </div>
    </div>
  )
}

function ChartAxisEditor({
  player,
  meta,
  rateMode,
  selectedKeys,
  onChange,
}: {
  player: PlayerRow
  meta: StatMeta
  rateMode: ProfileRateMode
  selectedKeys: string[]
  onChange: (keys: string[]) => void
}) {
  const selectedSet = useMemo(
    () => new Set(selectedKeys.map(canonicalProfileMetricKey)),
    [selectedKeys],
  )
  const addable = useMemo(
    () =>
      selectedKeys.length >= PIZZA_SLICE_SOFT_MAX
        ? []
        : curatedProfileMetricKeys(player.position_group).filter(
        key =>
          !selectedSet.has(canonicalProfileMetricKey(key)) &&
          isUsableExportMetric(player, meta, rateMode, key),
      ),
    [meta, player, rateMode, selectedKeys.length, selectedSet],
  )

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {selectedKeys.map((key, index) => {
          const available = isUsableExportMetric(player, meta, rateMode, key)
          return (
            <div
              key={key}
              className={cn(
                'flex items-center gap-1 border px-2 py-1 text-[10px] uppercase tracking-wide',
                available
                  ? 'border-electric/25 bg-electric/5 text-ink-dim hover:text-ink'
                  : 'border-ember/35 bg-ember/10 text-ember',
              )}
            >
              <span className="max-w-[150px] truncate">{profileExportLabelForKey(key, meta)}</span>
              <button
                type="button"
                disabled={index === 0}
                onClick={() => onChange(moveMetricKey(selectedKeys, key, -1))}
                className="grid size-5 place-items-center hover:text-ink disabled:opacity-30"
                aria-label={`Move ${profileExportLabelForKey(key, meta)} earlier`}
              >
                <ArrowLeft size={10} />
              </button>
              <button
                type="button"
                disabled={index === selectedKeys.length - 1}
                onClick={() => onChange(moveMetricKey(selectedKeys, key, 1))}
                className="grid size-5 place-items-center hover:text-ink disabled:opacity-30"
                aria-label={`Move ${profileExportLabelForKey(key, meta)} later`}
              >
                <ArrowRight size={10} />
              </button>
              <button
                type="button"
                onClick={() => onChange(selectedKeys.filter(k => k !== key))}
                className="grid size-5 place-items-center hover:text-ember"
                aria-label={`Remove ${profileExportLabelForKey(key, meta)}`}
              >
                <X size={10} />
              </button>
            </div>
          )
        })}
      </div>
      <select
        value=""
        onChange={e => {
          if (e.target.value) onChange(dedupeCanonicalMetricKeys([...selectedKeys, e.target.value]))
        }}
        className="w-full border border-electric/20 bg-panel px-3 py-2 text-[12px] text-ink outline-none focus:border-electric/60"
      >
        <option value="">Add profile chart axis...</option>
        {addable.map(key => (
          <option key={key} value={key}>
            {profileExportLabelForKey(key, meta)}
          </option>
        ))}
      </select>
    </div>
  )
}

interface PlayerProfileExportSurfaceProps {
  player: PlayerRow
  meta: StatMeta
  title: string
  preset: ProfileExportPreset
  tiles: ResolvedTile[]
  chartMetricKeys: string[]
  notes: string
  similarEdges: GalaxyEdge[]
  similarIsLoading: boolean
  similarIsError: boolean
  similarScopeLabel: string
  percentileMap: Record<string, number | null>
  percentileScopeLabel: string
  distributions?: ProfileDistributionPayload
  previewInvalid?: string | null
}

const PlayerProfileExportSurface = forwardRef<HTMLDivElement, PlayerProfileExportSurfaceProps>(function PlayerProfileExportSurface(
  {
    player,
    meta,
    title,
    preset,
    tiles,
    chartMetricKeys,
    notes,
    similarEdges,
    similarIsLoading,
    similarIsError,
    similarScopeLabel,
    percentileMap,
    percentileScopeLabel,
    distributions,
    previewInvalid,
  },
  ref,
) {
  const logo = getTeamLogoPath(player.canonical_team_id, player.canonical_team_name)
  const subtitleParts = [
    player.canonical_team_name,
    player.native_position || player.position_group,
    player.season_label,
    `${player.minutes.toLocaleString()} min`,
  ].filter(Boolean)
  const rawOnly = !player.eligibility.percentiles_eligible
  const contextLine = rawOnly
    ? `Stats: ${player.competition_code} ${player.season_label} · Raw values · Percentiles unavailable`
    : `Stats: ${player.competition_code} ${player.season_label} · ${preset.rateMode === 'per90' ? 'Per 90' : 'Season'} · Percentiles vs ${percentileScopeLabel} ${POSITION_COHORT_LABEL[player.position_group]}`
  const theme = surfaceTheme(preset.theme)
  const orientation = preset.orientation
  const isLandscape = orientation === 'landscape'
  const dimensions = profileExportDimensions(preset)
  const hasLowerPanel = preset.notesEnabled || preset.similarEnabled
  const hasDistribution = Boolean(
    preset.chartEnabled && preset.distributionEnabled && distributions,
  )
  const hasSupplement = preset.chartEnabled || hasLowerPanel
  const chartScale = isLandscape
    ? hasDistribution ? 0.7 : 0.72
    : 1.06
  const chartViewportSize = 760 * chartScale
  const chartPanelHeight = chartViewportSize + (isLandscape ? 72 : 80)
  const supplementRows =
    preset.chartEnabled && hasLowerPanel
      ? `${chartPanelHeight}px minmax(0, 1fr)`
      : 'auto'

  return (
    <div
      ref={ref}
      className="relative overflow-hidden font-sans"
      style={{
        width: dimensions.width,
        height: dimensions.height,
        background: theme.background,
        color: theme.text,
      }}
    >
      <SurfaceBackground theme={preset.theme} />
      <div
        className={cn(
          'relative z-10 flex h-full flex-col',
          isLandscape ? 'p-[44px]' : 'p-[54px]',
        )}
      >
        <header className={cn('flex shrink-0 items-start justify-between', isLandscape ? 'gap-7' : 'gap-9')}>
          <div className={cn('flex min-w-0 items-center', isLandscape ? 'gap-5' : 'gap-7')}>
            <div
              className={cn(
                'grid shrink-0 place-items-center border',
                isLandscape ? 'size-[86px]' : 'size-[124px]',
              )}
              style={{
                borderColor: theme.border,
                background: theme.logoBackground,
              }}
            >
              {logo ? (
                <img
                  src={logo}
                  alt=""
                  className={cn(
                    'object-contain',
                    isLandscape ? 'max-h-[64px] max-w-[64px]' : 'max-h-[94px] max-w-[94px]',
                  )}
                />
              ) : (
                <span
                  style={{ color: theme.accent }}
                  className={cn('font-black', isLandscape ? 'text-[26px]' : 'text-[34px]')}
                >
                  CF
                </span>
              )}
            </div>
            <div className="min-w-0">
              <p
                style={{ color: theme.accent }}
                className={cn(
                  'font-bold uppercase tracking-[0.3em]',
                  isLandscape ? 'mb-2 text-[12px]' : 'mb-4 text-[16px]',
                )}
              >
                Player profile
              </p>
              <h1
                className={cn(
                  'line-clamp-2 break-words font-black tracking-normal',
                  isLandscape
                    ? 'max-w-[940px] text-[50px] leading-[0.92]'
                    : 'max-w-[710px] text-[66px] leading-[0.92]',
                )}
              >
                {title || player.canonical_player_name}
              </h1>
              <p
                style={{ color: theme.muted }}
                className={cn(
                  'truncate font-medium',
                  isLandscape ? 'mt-3 max-w-[980px] text-[16px]' : 'mt-5 max-w-[760px] text-[21px]',
                )}
              >
                {subtitleParts.join(' · ')}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-start justify-end gap-4 text-right">
            <div>
              <p
                style={{ color: theme.accent }}
                className={cn(
                  'font-black uppercase leading-tight tracking-[0.14em]',
                  isLandscape ? 'max-w-[260px] text-[20px]' : 'max-w-[300px] text-[26px]',
                )}
              >
                {BRAND_NAME_UPPER}
              </p>
              <p
                style={{ color: theme.muted }}
                className={cn(
                  'uppercase tracking-[0.24em]',
                  isLandscape ? 'mt-1 text-[10px]' : 'mt-2 text-[12px]',
                )}
              >
                {BRAND_DOMAIN}
              </p>
            </div>
          </div>
        </header>

        <div
          className={cn(
            'flex min-h-0 flex-1 flex-col',
            isLandscape ? 'mt-5 gap-[18px]' : 'mt-8 gap-6',
          )}
        >
          <section
            className={cn(
              'grid gap-4',
              hasSupplement
                ? 'shrink-0 grid-cols-4'
                : isLandscape
                  ? 'min-h-0 flex-1 grid-cols-4 auto-rows-fr'
                  : 'min-h-0 flex-1 grid-cols-2 auto-rows-fr',
            )}
          >
            {tiles.map(tile => (
              <ExportStatTile
                key={tile.key}
                tile={tile}
                theme={preset.theme}
                showPercentile={preset.showPercentiles && !rawOnly}
                semanticColor={metricSemanticColor(meta.metrics[tile.key])}
                compact={hasSupplement}
                landscape={isLandscape}
              />
            ))}
          </section>

          {hasSupplement && (
            <div
              className={cn(
                'grid min-h-0 flex-1',
                isLandscape ? 'gap-[18px]' : 'gap-6',
              )}
              style={{ gridTemplateRows: supplementRows }}
            >
              {preset.chartEnabled && (
                <div
                  className={cn(
                    'grid min-h-0',
                    isLandscape ? 'gap-[18px]' : 'gap-6',
                    hasDistribution ? 'grid-cols-2' : 'grid-cols-1',
                  )}
                >
                  <section
                    data-export-section="profile-chart"
                    className={cn(
                      'relative grid min-h-0 place-items-center overflow-hidden border',
                      isLandscape ? 'px-3 py-3' : 'px-4 py-5',
                    )}
                    style={{ borderColor: theme.border, background: theme.panel }}
                  >
                    {preset.theme === 'conceptually-football' && <HudCornerMarks size="size-4" />}
                    <div className="flex min-h-0 flex-col items-center">
                      <p
                        style={{ color: theme.accent }}
                        className={cn(
                          'mb-1 font-bold uppercase tracking-[0.26em]',
                          isLandscape ? 'text-[11px]' : 'text-[14px]',
                        )}
                      >
                        Profile chart
                      </p>
                      <div
                        className={cn(
                          'grid place-items-center overflow-visible',
                          preset.theme === 'boring' && 'brightness-75 contrast-125',
                        )}
                        style={{
                          width: chartViewportSize,
                          height: chartViewportSize,
                        }}
                      >
                        <div
                          style={{
                            width: 760,
                            height: 760,
                            transform: `scale(${chartScale})`,
                            transformOrigin: 'top left',
                          }}
                        >
                          <ProfilePizzaSvg
                            player={player}
                            rateMode={preset.rateMode}
                            meta={meta}
                            metricKeys={chartMetricKeys}
                            percentileMap={percentileMap}
                            exportMode
                          />
                        </div>
                      </div>
                      {rawOnly && (
                        <p
                          style={{ color: theme.muted }}
                          className={cn(
                            'mt-1 uppercase tracking-[0.18em]',
                            isLandscape ? 'text-[9px]' : 'text-[12px]',
                          )}
                        >
                          Raw metric profile
                        </p>
                      )}
                    </div>
                  </section>

                  {hasDistribution && distributions && (
                    <section
                      data-export-section="cohort-distance"
                      className="relative flex min-h-0 flex-col overflow-hidden border p-3 [&_figcaption]:min-w-0 [&_figcaption>span]:truncate"
                      style={{ borderColor: theme.border, background: theme.panel }}
                    >
                      {preset.theme === 'conceptually-football' && <HudCornerMarks size="size-4" />}
                      <div className="mb-1 flex items-end justify-between gap-3">
                        <p style={{ color: theme.accent }} className="text-[11px] font-bold uppercase tracking-[0.24em]">
                          Cohort distance
                        </p>
                        <p style={{ color: theme.muted }} className="font-mono text-[9px] uppercase tracking-[0.12em]">
                          {distributions.context.competition_code} · {distributions.cohort_count} eligible
                        </p>
                      </div>
                      <div className="min-h-0 flex-1">
                        <ProfileDistributionPanel
                          player={player}
                          rateMode={preset.rateMode}
                          meta={meta}
                          metricKeys={chartMetricKeys}
                          distributions={distributions}
                          percentileMap={percentileMap}
                          compact
                          dense
                          light={preset.theme === 'boring'}
                        />
                      </div>
                    </section>
                  )}
                </div>
              )}

              {hasLowerPanel && (
                <div
                  className={cn(
                    'grid min-h-0',
                    isLandscape ? 'gap-[18px]' : 'gap-6',
                    preset.notesEnabled && preset.similarEnabled ? 'grid-cols-2' : 'grid-cols-1',
                  )}
                >
                  {preset.notesEnabled && (
                    <section
                      className={cn(
                        'relative min-h-0 overflow-hidden border',
                        isLandscape ? 'p-[18px]' : 'p-6',
                      )}
                      style={{ borderColor: theme.border, background: theme.panel }}
                    >
                      {preset.theme === 'conceptually-football' && <HudCornerMarks size="size-4" />}
                      <p
                        style={{ color: theme.accent }}
                        className={cn(
                          'font-bold uppercase tracking-[0.26em]',
                          isLandscape ? 'mb-2 text-[11px]' : 'mb-4 text-[14px]',
                        )}
                      >
                        Notes
                      </p>
                      <p
                        style={{ color: theme.text }}
                        className={cn(
                          'whitespace-pre-line break-words font-medium',
                          isLandscape ? 'text-[16px] leading-[1.32]' : 'text-[20px] leading-[1.4]',
                        )}
                      >
                        {notes.trim() || ' '}
                      </p>
                    </section>
                  )}

                  {preset.similarEnabled && (
                    <SimilarPlayersExportPanel
                      edges={similarEdges}
                      isLoading={similarIsLoading}
                      isError={similarIsError}
                      scopeLabel={similarScopeLabel}
                      theme={preset.theme}
                      compact={false}
                    />
                  )}
                </div>
              )}
            </div>
          )}

          <footer className="mt-auto flex shrink-0 items-end justify-between gap-8">
            <div className="min-w-0">
              <p
                style={{ color: theme.muted }}
                className={cn(
                  'truncate font-medium',
                  isLandscape ? 'max-w-[1280px] text-[11px]' : 'max-w-[820px] text-[14px]',
                )}
              >
                {contextLine}
              </p>
              {previewInvalid && (
                <p className={cn(
                  'font-bold uppercase tracking-[0.14em] text-amber-300',
                  isLandscape ? 'mt-1 text-[9px]' : 'mt-2 text-[12px]',
                )}>
                  Preview only · {previewInvalid}
                </p>
              )}
            </div>
            <div className="text-right">
              <p
                style={{ color: theme.muted }}
                className={cn(
                  'uppercase tracking-[0.24em]',
                  isLandscape ? 'text-[10px]' : 'text-[12px]',
                )}
              >
                {BRAND_DOMAIN}
              </p>
            </div>
          </footer>
        </div>
      </div>
    </div>
  )
})

function surfaceTheme(theme: ProfileExportTheme): {
  background: string
  panel: string
  text: string
  muted: string
  accent: string
  border: string
  logoBackground: string
} {
  if (theme === 'boring') {
    return {
      background: '#eef1f6',
      panel: 'rgba(248,250,253,0.82)',
      text: '#10131a',
      muted: '#596070',
      accent: '#2066c4',
      border: 'rgba(32,102,196,0.18)',
      logoBackground: 'rgba(248,250,253,0.88)',
    }
  }
  return {
    background: '#070810',
    panel: 'rgba(13,15,26,0.78)',
    text: '#e4eaf8',
    muted: '#8a95b8',
    accent: '#4a9ef5',
    border: 'rgba(74,158,245,0.25)',
    logoBackground: 'rgba(74,158,245,0.08)',
  }
}

function SurfaceBackground({ theme }: { theme: ProfileExportTheme }) {
  if (theme === 'boring') {
    return
  }
  return (
    <>
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(74,158,245,0.16),transparent_36%),linear-gradient(135deg,rgba(74,158,245,0.1),transparent_42%),linear-gradient(180deg,rgba(255,255,255,0.04),transparent_24%)]" />
      <div className="absolute inset-0 opacity-[0.12] [background-image:linear-gradient(rgba(74,158,245,0.22)_1px,transparent_1px),linear-gradient(90deg,rgba(74,158,245,0.22)_1px,transparent_1px)] [background-size:38px_38px]" />
    </>
  )
}

function ExportStatTile({
  tile,
  theme,
  showPercentile,
  semanticColor,
  compact,
  landscape,
}: {
  tile: ResolvedTile
  theme: ProfileExportTheme
  showPercentile: boolean
  semanticColor: MetricSemanticColor
  compact: boolean
  landscape: boolean
}) {
  const style = surfaceTheme(theme)
  const pctColor =
    tile.percentile != null
      ? getPercentileTextColor(tile.percentile, semanticColor)
      : style.muted
  return (
    <article
      className={cn(
        'relative min-h-0 border',
        compact
          ? landscape ? 'p-3' : 'p-4'
          : landscape ? 'flex flex-col justify-center p-7' : 'flex flex-col justify-center p-8',
      )}
      style={{
        borderColor: style.border,
        background: style.panel,
      }}
    >
      {theme === 'conceptually-football' && <HudCornerMarks size="size-3" />}
      <p
        style={{ color: style.muted }}
        className={cn(
          'line-clamp-2 font-bold uppercase tracking-[0.18em]',
          compact
            ? landscape ? 'mb-2 text-[10px]' : 'mb-3 text-[12px]'
            : landscape ? 'mb-5 text-[15px]' : 'mb-7 text-[18px]',
        )}
      >
        {tile.label}
      </p>
      <div className="flex items-end justify-between gap-3">
        <p
          style={{ color: style.text }}
          className={cn(
            'font-black leading-none tabular-nums',
            compact
              ? landscape ? 'text-[30px]' : 'text-[36px]'
              : landscape ? 'text-[54px]' : 'text-[68px]',
          )}
        >
          {formatValue(tile.value, tile.formatUnit)}
        </p>
        {showPercentile && (
          <div
            className={cn(
              'border font-black tabular-nums',
              compact
                ? landscape ? 'px-2 py-0.5 text-[12px]' : 'px-2.5 py-1 text-[14px]'
                : 'px-3 py-1.5 text-[18px]',
            )}
            style={{
              color: theme === 'boring' ? '#10131a' : pctColor,
              borderColor: `${pctColor}66`,
              background: theme === 'boring' ? `${pctColor}22` : `${pctColor}16`,
            }}
          >
            {tile.percentile != null ? Math.round(tile.percentile) : '—'}
          </div>
        )}
      </div>
    </article>
  )
}

function SimilarPlayersExportPanel({
  edges,
  isLoading,
  isError,
  scopeLabel,
  theme,
  compact,
}: {
  edges: GalaxyEdge[]
  isLoading: boolean
  isError: boolean
  scopeLabel: string
  theme: ProfileExportTheme
  compact: boolean
}) {
  const style = surfaceTheme(theme)
  const topEdges = edges.slice(0, 3)

  return (
    <section
      className={cn(
        'relative min-h-0 overflow-hidden border',
        compact ? 'p-2.5' : 'p-6',
      )}
      style={{ borderColor: style.border, background: style.panel }}
    >
      {theme === 'conceptually-football' && <HudCornerMarks size="size-4" />}
      <div className={cn('flex items-start justify-between', compact ? 'mb-1 gap-3' : 'mb-4 gap-4')}>
        <p
          style={{ color: style.accent }}
          className={cn(
            'font-bold uppercase tracking-[0.26em]',
            compact ? 'text-[10px]' : 'text-[14px]',
          )}
        >
          Similar players
        </p>
        <p
          style={{ color: style.muted }}
          className={cn(
            'max-w-[55%] truncate text-right uppercase tracking-[0.2em]',
            compact ? 'text-[9px]' : 'text-[10px]',
          )}
        >
          {scopeLabel}
        </p>
      </div>

      {isLoading && (
        <p
          style={{ color: style.muted }}
          className={cn(
            'flex items-center justify-center text-center font-bold uppercase tracking-[0.18em]',
            compact ? 'min-h-[90px] text-[12px]' : 'min-h-[170px] text-[17px]',
          )}
        >
          Scanning similarity matrix
        </p>
      )}

      {isError && !isLoading && (
        <p
          style={{ color: style.muted }}
          className={cn(
            'flex items-center justify-center text-center font-medium leading-relaxed',
            compact ? 'min-h-[90px] text-[12px]' : 'min-h-[170px] text-[18px]',
          )}
        >
          Similar players are unavailable for this league-season.
        </p>
      )}

      {!isLoading && !isError && topEdges.length === 0 && (
        <p
          style={{ color: style.muted }}
          className={cn(
            'flex items-center justify-center text-center font-medium leading-relaxed',
            compact ? 'min-h-[90px] text-[12px]' : 'min-h-[170px] text-[18px]',
          )}
        >
          No similar players found for this profile.
        </p>
      )}

      {!isLoading && !isError && topEdges.length > 0 && (
        <div
          className={cn('flex flex-col', compact ? 'gap-1' : 'gap-2')}
          style={{
            background: 'transparent',
          }}
        >
          {topEdges.map(edge => {
            const score = Math.round(edge.profile_match_score ?? edge.similarity * 100)
            return (
              <div
                key={`${edge.to_galaxy_player_id}-${edge.rank}`}
                className={cn(
                  'grid items-center border text-left',
                  compact
                    ? 'grid-cols-[26px_minmax(0,1fr)_auto] gap-2 px-2 py-0.5'
                    : 'grid-cols-[34px_minmax(0,1fr)_auto] gap-3 px-3 py-3',
                )}
                style={{
                  borderColor: style.border,
                  background: theme === 'boring' ? 'rgba(255,255,255,0.34)' : 'rgba(7,8,16,0.26)',
                }}
              >
                <span
                  style={{ color: style.accent }}
                  className={cn('font-mono font-bold opacity-70', compact ? 'text-[10px]' : 'text-[14px]')}
                >
                  #{edge.rank}
                </span>
                <span className="min-w-0">
                  <span
                    style={{ color: style.text }}
                    className={cn('block truncate font-bold leading-tight', compact ? 'text-[13px]' : 'text-[20px]')}
                  >
                    {shortPlayerName(edge.to_player_name)}
                  </span>
                  <span
                    style={{ color: style.muted }}
                    className={cn('block truncate font-medium', compact ? 'text-[9px]' : 'mt-1 text-[13px]')}
                  >
                    {edge.to_team_name ?? edge.to_competition_code ?? '—'}
                  </span>
                </span>
                <span
                  className={cn(
                    'border text-center font-mono font-black tabular-nums',
                    compact ? 'px-2 py-0.5 text-[11px]' : 'px-2.5 py-1 text-[15px]',
                  )}
                  style={{
                    color: theme === 'boring' ? style.text : style.accent,
                    borderColor: `${style.accent}55`,
                    background: `${style.accent}18`,
                  }}
                >
                  {score}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
