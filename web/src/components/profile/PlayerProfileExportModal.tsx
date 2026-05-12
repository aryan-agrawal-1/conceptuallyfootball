import { forwardRef, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Download, GripVertical, RotateCcw, Share2, X } from 'lucide-react'
import { HudActionButton, HudCornerMarks, HudPill } from '../hud/Hud'
import { ProfilePizzaSvg } from './ProfilePizzaSection'
import { formatValue } from '../../lib/format'
import { getPercentileTextColor } from '../../lib/heatmap'
import {
  buildDefaultProfileExportPreset,
  curatedProfileMetricKeys,
  hydrateProfileExportPreset,
  isUsableExportMetric,
  profileExportLabelForKey,
  saveProfileExportPreset,
  type ProfileExportPreset,
  type ProfileExportTheme,
  type ProfileExportTile,
} from '../../lib/profileExport'
import {
  PIZZA_SLICE_MIN,
  barKindForMetricKey,
  resolveProfileMetric,
  stripPer90Suffix,
  type ProfileRateMode,
} from '../../lib/profileMetrics'
import { getTeamLogoPath } from '../../lib/teamLogos'
import { BRAND_DOMAIN, BRAND_NAME_UPPER, BRAND_SLUG } from '../../lib/brand'
import { cn } from '../../lib/utils'
import type { PlayerRow, StatMeta } from '../../types/api'

interface PlayerProfileExportModalProps {
  player: PlayerRow
  meta: StatMeta
  initialRateMode: ProfileRateMode
  percentileMap?: Record<string, number | null>
  percentileScopeLabel?: string
  onClose: () => void
}

interface ResolvedTile extends ProfileExportTile {
  available: boolean
  value: number | null
  percentile: number | null
  formatUnit: Parameters<typeof formatValue>[1]
}

const A4_WIDTH = 1240
const A4_HEIGHT = 1754
const MIN_STATS = 4

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

function layoutStatCap(chartEnabled: boolean, notesEnabled: boolean): number {
  if (chartEnabled && notesEnabled) return 8
  if (chartEnabled) return 10
  if (notesEnabled) return 18
  return 24
}

function notesLimit(chartEnabled: boolean): number {
  return chartEnabled ? 280 : 500
}

function dataUrlToFile(dataUrl: string, fileName: string): Promise<File> {
  return fetch(dataUrl)
    .then(res => res.blob())
    .then(blob => new File([blob], fileName, { type: blob.type || 'image/png' }))
}

function slugify(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
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
  onClose,
}: PlayerProfileExportModalProps) {
  const exportRef = useRef<HTMLDivElement>(null)
  const [preset, setPreset] = useState<ProfileExportPreset>(() =>
    hydrateProfileExportPreset(player, meta, initialRateMode),
  )
  const [title, setTitle] = useState(player.canonical_player_name)
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState<'share' | 'download' | null>(null)
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
  const availableMetricKeys = useMemo(
    () =>
      curatedProfileMetricKeys(player.position_group).filter(
        key => !selectedKeys.has(key) && isUsableExportMetric(player, meta, preset.rateMode, key),
      ),
    [meta, player, preset.rateMode, selectedKeys],
  )
  const chartMetricKeys = useMemo(
    () =>
      preset.chartMetricKeys.filter(key =>
        isUsableExportMetric(player, meta, preset.rateMode, key),
      ),
    [meta, player, preset.chartMetricKeys, preset.rateMode],
  )

  const statCap = layoutStatCap(preset.chartEnabled, preset.notesEnabled)
  const noteMax = notesLimit(preset.chartEnabled)
  const overCap = validTiles.length > statCap
  const underMin = validTiles.length < MIN_STATS
  const chartInvalid = preset.chartEnabled && chartMetricKeys.length < PIZZA_SLICE_MIN
  const notesInvalid = preset.notesEnabled && notes.length > noteMax
  const invalidReason = overCap
    ? `This layout supports up to ${statCap} stat tiles. Remove ${validTiles.length - statCap} to export.`
    : underMin
      ? `Select at least ${MIN_STATS} available stat tiles to export.`
      : chartInvalid
        ? `Select at least ${PIZZA_SLICE_MIN} available profile chart axes.`
        : notesInvalid
          ? `Notes must be ${noteMax} characters or fewer for this layout.`
          : null
  const canExport = !invalidReason && !busy

  const fileName = useMemo(
    () =>
      `${BRAND_SLUG}-player-profile-${slugify(title || player.canonical_player_name)}-${slugify(player.season_label)}-${preset.theme}.png`,
    [player.canonical_player_name, player.season_label, preset.theme, title],
  )

  function updatePreset(next: Partial<ProfileExportPreset>) {
    setPreset(prev => ({ ...prev, ...next }))
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
    setTitle(player.canonical_player_name)
    setNotes('')
  }

  function persistExportPreset() {
    saveProfileExportPreset(player.position_group, {
      ...preset,
      stats: validTiles.map(tile => ({ key: tile.key, label: tile.label })),
      chartMetricKeys,
      notesEnabled: preset.notesEnabled,
      showPercentiles: player.eligibility.percentiles_eligible && preset.showPercentiles,
    })
  }

  async function buildImage(): Promise<string> {
    const node = exportRef.current
    if (!node) throw new Error('Export surface unavailable.')
    const { toPng } = await import('html-to-image')
    return toPng(node, {
      cacheBust: true,
      pixelRatio: 2,
      backgroundColor: preset.theme === 'boring' ? '#eef1f6' : '#070810',
    })
  }

  async function handleDownload() {
    if (!canExport) return
    try {
      setBusy('download')
      const dataUrl = await buildImage()
      const link = document.createElement('a')
      link.href = dataUrl
      link.download = fileName
      link.click()
      persistExportPreset()
    } finally {
      setBusy(null)
    }
  }

  async function handleShare() {
    if (!canExport) return
    try {
      setBusy('share')
      const dataUrl = await buildImage()
      const file = await dataUrlToFile(dataUrl, fileName)
      if (
        typeof navigator !== 'undefined' &&
        'share' in navigator &&
        'canShare' in navigator &&
        navigator.canShare?.({ files: [file] })
      ) {
        await navigator.share({
          title,
          text: `${player.season_label} · ${player.canonical_team_name ?? 'No club'} profile`,
          files: [file],
        })
        persistExportPreset()
        return
      }
      const link = document.createElement('a')
      link.href = dataUrl
      link.download = fileName
      link.click()
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
            <h2 className="truncate text-[18px] font-black text-ink">{player.canonical_player_name}</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="grid size-9 shrink-0 place-items-center border border-electric/20 text-ink-muted transition-colors hover:border-electric/50 hover:text-electric"
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
                        className="grid size-8 cursor-grab place-items-center border border-electric/15 text-ink-muted active:cursor-grabbing"
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
                        className="grid size-7 place-items-center border border-electric/15 text-ink-muted transition-colors hover:border-ember/50 hover:text-ember"
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
                  <option value="">Add available stat...</option>
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
                    onChange={e => updatePreset({ chartEnabled: e.target.checked })}
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
                  onChange={chartMetricKeys => updatePreset({ chartMetricKeys })}
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
            </div>
          </aside>

          <main className="flex min-h-0 flex-col bg-[#05060c]">
            <div className="min-h-0 flex-1 overflow-auto p-4 sm:p-6">
              <div className="flex min-h-full items-start justify-center">
                <div className="origin-top" style={{ width: A4_WIDTH * 0.42, height: A4_HEIGHT * 0.42 }}>
                  <div style={{ transform: 'scale(0.42)', transformOrigin: 'top left' }}>
                    <PlayerProfileExportSurface
                      player={player}
                      meta={meta}
                      title={title}
                      preset={preset}
                      tiles={validTiles}
                      chartMetricKeys={chartMetricKeys}
                      notes={notes}
                      previewInvalid={invalidReason}
                      percentileMap={percentileMap}
                      percentileScopeLabel={percentileScopeLabel}
                    />
                  </div>
                </div>
              </div>
            </div>

            <div className="flex shrink-0 flex-col gap-3 border-t border-electric/20 bg-panel/95 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-h-5 text-[11px] text-ink-muted">
                {invalidReason ? <span className="text-amber-300">{invalidReason}</span> : <span>{fileName}</span>}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={resetDefaults}
                  className="flex items-center gap-1.5 border border-electric/15 px-3 py-2 text-[11px] uppercase tracking-[0.15em] text-ink-muted transition-colors hover:border-electric/40 hover:text-electric"
                >
                  <RotateCcw size={14} />
                  Reset defaults
                </button>
                <button
                  type="button"
                  onClick={handleShare}
                  disabled={!canExport}
                  title={invalidReason ?? undefined}
                  className={cn(
                    'relative flex items-center gap-1.5 border border-electric/15 px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.15em] text-ink-muted transition-colors hover:border-electric/40 hover:text-electric/80',
                    !canExport && 'pointer-events-none opacity-40',
                  )}
                >
                  <Share2 className="size-3.5" />
                  {busy === 'share' ? 'Preparing...' : 'Share'}
                </button>
                <HudActionButton onClick={handleDownload} disabled={!canExport} className="px-4 py-2.5">
                  <Download size={15} />
                  {busy === 'download' ? 'Rendering...' : 'Download PNG'}
                </HudActionButton>
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
          percentileMap={percentileMap}
          percentileScopeLabel={percentileScopeLabel}
        />
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
  options: Array<{ value: T; label: string }>
  onChange: (value: T) => void
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-[10px] uppercase tracking-[0.18em] text-ink-muted">{label}</span>
      <div className="flex flex-wrap gap-2">
        {options.map(option => (
          <HudPill
            key={option.value}
            active={value === option.value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
          </HudPill>
        ))}
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
  const selectedSet = useMemo(() => new Set(selectedKeys), [selectedKeys])
  const addable = useMemo(
    () =>
      curatedProfileMetricKeys(player.position_group).filter(
        key => !selectedSet.has(key) && isUsableExportMetric(player, meta, rateMode, key),
      ),
    [meta, player, rateMode, selectedSet],
  )

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        {selectedKeys.map(key => {
          const available = isUsableExportMetric(player, meta, rateMode, key)
          return (
            <button
              key={key}
              type="button"
              onClick={() => onChange(selectedKeys.filter(k => k !== key))}
              className={cn(
                'flex items-center gap-1 border px-2 py-1 text-[10px] uppercase tracking-wide',
                available
                  ? 'border-electric/25 bg-electric/5 text-ink-dim hover:text-ink'
                  : 'border-ember/35 bg-ember/10 text-ember',
              )}
            >
              <span className="max-w-[150px] truncate">{profileExportLabelForKey(key, meta)}</span>
              <X size={11} />
            </button>
          )
        })}
      </div>
      <select
        value=""
        onChange={e => {
          if (e.target.value) onChange([...selectedKeys, e.target.value])
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
  percentileMap: Record<string, number | null>
  percentileScopeLabel: string
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
    percentileMap,
    percentileScopeLabel,
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
  const hasSupplement = preset.chartEnabled || preset.notesEnabled
  const chartScale = preset.notesEnabled ? 0.62 : 1.2

  return (
    <div
      ref={ref}
      className={cn(
        'relative overflow-hidden',
        preset.theme === 'conceptually-football' ? 'font-sans' : 'font-sans',
      )}
      style={{
        width: A4_WIDTH,
        height: A4_HEIGHT,
        background: theme.background,
        color: theme.text,
      }}
    >
      <SurfaceBackground theme={preset.theme} />
      <div className="relative z-10 flex h-full flex-col p-[72px]">
        <header className="flex items-start justify-between gap-10">
          <div className="flex min-w-0 items-start gap-7">
            <div
              className="grid size-[142px] shrink-0 place-items-center border"
              style={{
                borderColor: theme.border,
                background: theme.logoBackground,
              }}
            >
              {logo ? (
                <img src={logo} alt="" className="max-h-[106px] max-w-[106px] object-contain" />
              ) : (
                <span style={{ color: theme.accent }} className="text-[36px] font-black">
                  CF
                </span>
              )}
            </div>
            <div className="min-w-0">
              <p style={{ color: theme.accent }} className="mb-5 text-[18px] font-bold uppercase tracking-[0.32em]">
                Player profile
              </p>
              <h1 className="max-w-[760px] text-[76px] font-black leading-[0.92] tracking-normal">
                {title || player.canonical_player_name}
              </h1>
              <p style={{ color: theme.muted }} className="mt-6 text-[24px] font-medium">
                {subtitleParts.join(' · ')}
              </p>
            </div>
          </div>
          <div className="flex shrink-0 items-start justify-end gap-4 text-right">
            <div>
              <p style={{ color: theme.accent }} className="max-w-[340px] text-[30px] font-black uppercase leading-tight tracking-[0.14em]">
                {BRAND_NAME_UPPER}
              </p>
              <p style={{ color: theme.muted }} className="mt-2 text-[13px] uppercase tracking-[0.24em]">
                {BRAND_DOMAIN}
              </p>
            </div>
          </div>
        </header>

        <div className="mt-10 flex min-h-0 flex-1 flex-col gap-8">
          <section
            className={cn(
              'grid gap-4',
              hasSupplement ? 'grid-cols-4' : 'content-start grid-cols-4',
              hasSupplement && tiles.length > 8 && 'grid-cols-5',
              !hasSupplement && tiles.length > 16 && 'grid-cols-5',
            )}
          >
            {tiles.map(tile => (
              <ExportStatTile
                key={tile.key}
                tile={tile}
                theme={preset.theme}
                showPercentile={preset.showPercentiles && !rawOnly}
              />
            ))}
          </section>

          {hasSupplement && (
            <div
              className={cn(
                'grid min-h-0 flex-1 gap-8',
                preset.chartEnabled && preset.notesEnabled ? 'grid-cols-[0.95fr_1.05fr]' : 'grid-cols-1',
              )}
            >
              {preset.chartEnabled && (
              <section
                className="relative flex min-h-0 flex-col items-center justify-center overflow-hidden border px-4 py-6"
                style={{ borderColor: theme.border, background: theme.panel }}
              >
                {preset.theme === 'conceptually-football' && <HudCornerMarks size="size-4" />}
                <p style={{ color: theme.accent }} className="mb-2 text-[15px] font-bold uppercase tracking-[0.26em]">
                  Profile chart
                </p>
                <div
                  className={cn(preset.theme === 'boring' && 'brightness-75 contrast-125')}
                  style={{
                    width: 760 * chartScale,
                    height: 760 * chartScale,
                  }}
                >
                  <div style={{ transform: `scale(${chartScale})`, transformOrigin: 'top left' }}>
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
                  <p style={{ color: theme.muted }} className="mt-2 text-[13px] uppercase tracking-[0.18em]">
                    Raw metric profile
                  </p>
                )}
              </section>
              )}

              {preset.notesEnabled && (
              <section
                className="relative min-h-0 overflow-hidden border p-8"
                style={{ borderColor: theme.border, background: theme.panel }}
              >
                {preset.theme === 'conceptually-football' && <HudCornerMarks size="size-4" />}
                <p style={{ color: theme.accent }} className="mb-5 text-[15px] font-bold uppercase tracking-[0.26em]">
                  Notes
                </p>
                <p style={{ color: theme.text }} className="whitespace-pre-line text-[24px] font-medium leading-[1.45]">
                  {notes.trim() || ' '}
                </p>
              </section>
              )}
            </div>
          )}

          <footer className="mt-auto flex items-end justify-between gap-8">
            <div>
              <p style={{ color: theme.muted }} className="text-[16px] font-medium">
                {contextLine}
              </p>
              {previewInvalid && (
                <p className="mt-2 text-[14px] font-bold uppercase tracking-[0.14em] text-amber-300">
                  Preview only · {previewInvalid}
                </p>
              )}
            </div>
            <div className="text-right">
              <p style={{ color: theme.muted }} className="text-[14px] uppercase tracking-[0.24em]">
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
}: {
  tile: ResolvedTile
  theme: ProfileExportTheme
  showPercentile: boolean
}) {
  const style = surfaceTheme(theme)
  const pctColor = tile.percentile != null ? getPercentileTextColor(tile.percentile) : style.muted
  return (
    <article
      className="relative min-h-[138px] border p-5"
      style={{
        borderColor: style.border,
        background: style.panel,
      }}
    >
      {theme === 'conceptually-football' && <HudCornerMarks size="size-3" />}
      <p style={{ color: style.muted }} className="mb-4 line-clamp-2 text-[13px] font-bold uppercase tracking-[0.18em]">
        {tile.label}
      </p>
      <div className="flex items-end justify-between gap-3">
        <p style={{ color: style.text }} className="text-[38px] font-black leading-none tabular-nums">
          {formatValue(tile.value, tile.formatUnit)}
        </p>
        {showPercentile && (
          <div
            className="border px-2.5 py-1 text-[15px] font-black tabular-nums"
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
