import { lazy, Suspense, useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowUpRight, Loader2, Search, X } from 'lucide-react'
import { fetchGalaxy, fetchGalaxySimilar } from '../lib/api'
import type { GalaxyEdge, GalaxyPoint, PositionGroup } from '../types/api'
import { cn } from '../lib/utils'
import {
  HudActionButton,
  HudDivider,
  HudFrame,
} from '../components/hud/Hud'
import { HudMultiSelectDropdown } from '../components/hud/HudDropdown'
import { useScope } from '../context/ScopeContext'

const GalaxyScene = lazy(() =>
  import('../components/galaxy/GalaxyScene').then(module => ({ default: module.GalaxyScene })),
)

const DEFAULT_FILTERS = {
  position_group: [] as string[],
  team: [] as string[],
  min_minutes: 900,
}

const POSITION_FILTER_OPTIONS = [
  { value: 'FWD', label: 'FWD' },
  { value: 'MID', label: 'MID' },
  { value: 'DEF', label: 'DEF' },
]

function readParamValues(params: URLSearchParams, key: string): string[] {
  return params
    .getAll(key)
    .flatMap(value => value.split(','))
    .map(value => value.trim())
    .filter(Boolean)
}

// ─── Layout pass ─────────────────────────────────────────────────────────────
// UMAP can land similar players *extremely* close together — often overlapping
// within a single sprite. We do two things to fix that without touching the
// backend:
//   1. Uniformly scale the layout so the whole cluster feels airier.
//   2. Run a short physics-style relaxation that pushes any two stars that
//      ended up within `MIN_SEPARATION` of each other apart. This preserves
//      the overall shape of the embedding but guarantees no overlap.
//
// N is small (~hundreds of players) so an O(N^2) pass per iteration is fine.

function MinutesInput({
  value,
  floor,
  onCommit,
}: {
  value: number
  floor: number
  onCommit: (minutes: number) => void
}) {
  const [draft, setDraft] = useState(String(Math.max(value, floor)))

  function commitDraft() {
    const parsed = Number(draft)
    const nextMinutes = Number.isFinite(parsed) ? Math.max(parsed, floor) : floor
    setDraft(String(nextMinutes))
    onCommit(nextMinutes)
  }

  return (
    <input
      type="number"
      aria-label="Minimum minutes"
      className="border border-electric/25 bg-mat/80 px-2 py-1.5 font-mono text-[16px] text-electric/90 focus:border-electric focus:outline-none lg:text-[11px]"
      value={draft}
      min={floor}
      onChange={event => setDraft(event.target.value)}
      onBlur={commitDraft}
      onKeyDown={event => {
        if (event.key === 'Enter') {
          event.currentTarget.blur()
        }
      }}
    />
  )
}

function PositionBadge({ position }: { position: PositionGroup }) {
  return (
    <span className="text-[10px] px-2 py-0.5 rounded border border-electric/40 text-electric/90 tracking-[0.15em] font-medium">
      {position}
    </span>
  )
}

// ─── Bottom-center player HUD ───────────────────────────────────────────────
// Appears when a star is selected. Three columns:
//   1. Identity: large player name + team/position/archetype/minutes readout
//   2. Top comps list (the same edges drawn in the scene)
//   3. Actions: big glowing "Open Profile" CTA + subtle Clear
// Hovering a row in the comps list also lights up that star in the 3D scene
// via the shared hover state, so this panel and the sidebar list behave the
// same way.

function StatReadout({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col">
      <span className="text-[9px] uppercase tracking-[0.2em] text-electric/60">
        {label}
      </span>
      <span className="text-[13px] text-ink font-medium tabular-nums">
        {value}
      </span>
    </div>
  )
}

function PlayerHud({
  point,
  edges,
  isLoading,
  onSelectEdge,
  onHoverEdge,
  onClear,
  onOpenProfile,
}: {
  point: GalaxyPoint
  edges: GalaxyEdge[]
  isLoading: boolean
  onSelectEdge: (id: string) => void
  onHoverEdge: (id: string | null) => void
  onClear: () => void
  onOpenProfile: () => void
}) {
  const { buildScopedPath } = useScope()
  const header = (
    <div className="flex min-w-0 flex-1 items-center justify-between gap-2">
      <span className="truncate">Target Acquired // {point.galaxy_player_id}</span>
      <button
        type="button"
        onClick={onOpenProfile}
        className="inline-flex shrink-0 items-center gap-1 border border-electric/35 px-2 py-1 text-[9px] uppercase tracking-[0.16em] text-electric/90 lg:hidden"
      >
        Open
        <ArrowUpRight size={11} />
      </button>
    </div>
  )
  return (
    <HudFrame
      className="absolute inset-x-3 bottom-3 z-20 max-h-[30svh] overflow-hidden lg:inset-x-auto lg:bottom-4 lg:left-1/2 lg:max-h-[46svh] lg:w-[min(760px,calc(100%-2rem))] lg:-translate-x-1/2"
      header={header}
      footer={
        <div className="hidden justify-between items-center lg:flex">
          <span>{point.competition_code} // {point.primary_archetype_label}</span>
          <span className="font-mono">
            X {point.x.toFixed(2)}  Y {point.y.toFixed(2)}  Z {point.z.toFixed(2)}
          </span>
        </div>
      }
    >
      <div className="grid max-h-[calc(30svh-34px)] grid-cols-1 items-stretch gap-2 overflow-y-auto p-2.5 sm:grid-cols-[1fr_auto] lg:max-h-none lg:grid-cols-[1.3fr_1fr_auto] lg:gap-4 lg:overflow-visible lg:p-4">
        {/* Identity column */}
        <div className="flex min-w-0 flex-col gap-2 lg:gap-3">
          <div>
            <p className="mb-1 text-[9px] uppercase tracking-[0.22em] text-electric/70 lg:text-[10px] lg:tracking-[0.25em]">
              Player
            </p>
            <p className="break-words text-[15px] font-bold leading-tight text-ink sm:text-[18px] lg:truncate lg:text-[22px]">
              {point.canonical_player_name}
            </p>
            <p className="text-[11px] truncate">
              {point.canonical_team_id != null && point.canonical_team_name ? (
                <Link
                  to={buildScopedPath(`/team/${point.canonical_team_id}`)}
                  className="text-ink-dim hover:text-electric hover:underline"
                >
                  {point.canonical_team_name}
                </Link>
              ) : (
                <span className="text-ink-dim">{point.canonical_team_name ?? 'No team'}</span>
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 lg:gap-3">
            <PositionBadge position={point.position_group} />
            <span className="text-[9px] uppercase tracking-[0.16em] text-electric/70 lg:text-[10px] lg:tracking-[0.2em]">
              {point.cluster_label}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 pt-1 lg:gap-3">
            <StatReadout label="Minutes" value={point.minutes.toLocaleString()} />
            <StatReadout
              label="Archetype"
              value={<span className="text-[12px]">{point.primary_archetype_label}</span>}
            />
            <StatReadout
              label="Secondary"
              value={<span className="text-[12px]">{point.secondary_archetype_label || 'None'}</span>}
            />
            <StatReadout
              label="Confidence"
              value={
                point.primary_archetype_confidence == null
                  ? 'n/a'
                  : `${Math.round(point.primary_archetype_confidence * 100)}`
              }
            />
          </div>
        </div>

        {/* Top comps column */}
        <div className="hidden min-w-0 flex-col lg:flex">
          <p className="text-[10px] uppercase tracking-[0.25em] text-electric/70 mb-2">
            Top Comps
          </p>
          <div className="flex-1 border border-electric/15 bg-mat/40">
            {isLoading ? (
              <div className="flex items-center gap-2 px-2 py-3 text-[11px] text-ink-dim">
                <Loader2 size={12} className="animate-spin text-electric" />
                Scanning similarity matrix...
              </div>
            ) : edges.length === 0 ? (
              <p className="px-2 py-3 text-[11px] text-ink-muted">
                No comps available.
              </p>
            ) : (
              edges.map(edge => (
                <button
                  key={edge.to_galaxy_player_id}
                  onClick={() => onSelectEdge(edge.to_galaxy_player_id)}
                  onMouseEnter={() => onHoverEdge(edge.to_galaxy_player_id)}
                  onMouseLeave={() => onHoverEdge(null)}
                  className="w-full flex items-center justify-between px-2 py-1 text-[11px] border-b last:border-b-0 border-electric/10 hover:bg-electric/10 hover:text-electric transition-colors"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="text-electric/50 font-mono">
                      #{edge.rank}
                    </span>
                    <span className="truncate">{edge.to_player_name}</span>
                  </span>
                  <span className="font-mono text-electric">
                    {Math.round(edge.profile_match_score ?? edge.similarity * 100)}
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Actions column */}
        <div className="flex flex-row-reverse items-center justify-between gap-2 sm:col-span-1 lg:col-span-1 lg:min-w-[140px] lg:flex-col lg:items-end">
          <button
            onClick={onClear}
            className="flex items-center gap-1 text-[10px] uppercase tracking-[0.2em] text-ink-dim hover:text-ink"
          >
            <X size={12} />
            Clear
          </button>
          <HudActionButton onClick={onOpenProfile} className="hidden w-auto px-3 py-2 text-[10px] lg:flex lg:w-full lg:px-4 lg:py-3 lg:text-[12px]">
            <span>Open Profile</span>
            <ArrowUpRight size={14} className="transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </HudActionButton>
        </div>
      </div>
    </HudFrame>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function Galaxy() {
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const { scope, scopeLabel, buildScopedPath } = useScope()
  const [selectedPlayerId, setSelectedPlayerId] = useState<string | null>(null)
  const [hoveredPlayerId, setHoveredPlayerId] = useState<string | null>(null)
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [knownTeams, setKnownTeams] = useState<string[]>([])

  const rawFilterSearch = params.toString()
  const filters = useMemo(() => {
    const nextParams = new URLSearchParams(rawFilterSearch)
    return {
      competition: scope.competition,
      season: scope.season,
      min_minutes: Number(nextParams.get('min_minutes') ?? DEFAULT_FILTERS.min_minutes),
      position_group: readParamValues(nextParams, 'position_group'),
      team: readParamValues(nextParams, 'team'),
    }
  }, [rawFilterSearch, scope.competition, scope.season])

  const galaxyQuery = useQuery({
    queryKey: [
      'galaxy',
      filters.competition,
      filters.season,
      filters.min_minutes,
      filters.position_group.join(','),
      filters.team.join(','),
    ],
    queryFn: () => fetchGalaxy(filters),
    // Changing filters produces a new query key. Without this, React Query
    // would report `isPending = true` and my loader would take over the
    // screen while the new payload arrives. `keepPreviousData` keeps the
    // last good data visible during the refetch so filtering feels live.
    placeholderData: keepPreviousData,
  })

  // Edges/selected are fetched independently — selecting a player does NOT
  // touch the heavy galaxy payload, so the scene doesn't flash.
  const similarQuery = useQuery({
    queryKey: ['galaxy-similar', filters.competition, filters.season, selectedPlayerId],
    queryFn: () =>
      fetchGalaxySimilar(selectedPlayerId as string, filters.competition, filters.season),
    enabled: selectedPlayerId != null,
  })

  const data = galaxyQuery.data

  // Apply the scale + repulsion pass *once* per galaxy payload. Everything
  // downstream (sprites, highlight ring, similarity lines) reads from these
  // relaxed positions so they all stay in sync.
  const [laidOutPoints, setLaidOutPoints] = useState<GalaxyPoint[]>([])

  useEffect(() => {
    const points = data?.points ?? []
    const worker = new Worker(new URL('../workers/galaxyLayoutWorker.ts', import.meta.url), {
      type: 'module',
    })
    worker.onmessage = (event: MessageEvent<GalaxyPoint[]>) => {
      setLaidOutPoints(event.data)
    }
    worker.postMessage(points)
    return () => worker.terminate()
  }, [data?.points])

  const pointsById = useMemo(() => {
    const m = new Map<string, GalaxyPoint>()
    for (const point of laidOutPoints) m.set(point.galaxy_player_id, point)
    return m
  }, [laidOutPoints])

  const teams = useMemo(() => {
    const names = (data?.points ?? [])
      .map(point => point.canonical_team_name)
      .filter((team): team is string => Boolean(team))
    return [...new Set(names)].sort((a, b) => a.localeCompare(b))
  }, [data?.points])

  useEffect(() => {
    if (teams.length === 0) return
    setKnownTeams(current => {
      const next = [...new Set([...current, ...teams])].sort((a, b) => a.localeCompare(b))
      return next.length === current.length && next.every((team, index) => team === current[index]) ? current : next
    })
  }, [teams])

  function setFilter(next: Partial<typeof filters>) {
    const nextParams = new URLSearchParams(params)
    if ('position_group' in next) {
      nextParams.delete('position_group')
      for (const value of next.position_group ?? []) {
        if (value) nextParams.append('position_group', value)
      }
    }
    if ('team' in next) {
      nextParams.delete('team')
      for (const value of next.team ?? []) {
        if (value) nextParams.append('team', value)
      }
    }
    if ('min_minutes' in next) {
      const floor = data?.model_meta?.min_minutes ?? 450
      nextParams.set('min_minutes', String(Math.max(next.min_minutes ?? DEFAULT_FILTERS.min_minutes, floor)))
    }
    setParams(nextParams)
  }

  function selectGalaxyPlayer(id: string) {
    setSelectedPlayerId(id)
    setMobileSearchOpen(false)
  }

  function clearMobileSelectionOnMiss() {
    if (typeof window !== 'undefined' && window.matchMedia('(max-width: 1023px)').matches) {
      setSelectedPlayerId(null)
      setHoveredPlayerId(null)
    }
  }

  const mobileSearchResults = useMemo(() => {
    if (!mobileSearchOpen) return []
    const needle = search.trim().toLowerCase()
    if (!needle) return []
    return (data?.players ?? [])
      .filter(player => player.canonical_player_name.toLowerCase().includes(needle))
      .sort((a, b) => a.canonical_player_name.localeCompare(b.canonical_player_name))
      .slice(0, 6)
  }, [data?.players, mobileSearchOpen, search])

  if (galaxyQuery.isLoading) {
    return (
      <div className="flex h-[calc(100svh-132px)] items-center justify-center lg:h-[calc(100svh-52px)]">
        <Loader2 size={28} className="text-electric animate-spin" />
      </div>
    )
  }
  if (galaxyQuery.isError || !data) {
    return (
      <div className="flex h-[calc(100svh-132px)] flex-col items-center justify-center gap-3 px-4 lg:h-[calc(100svh-52px)]">
        <AlertCircle size={24} className="text-ember" />
        <p className="text-[12px] text-ink-muted">
          {galaxyQuery.error?.message ?? 'Failed to load galaxy.'}
        </p>
      </div>
    )
  }

  const selectedPoint =
    selectedPlayerId != null ? pointsById.get(selectedPlayerId) ?? null : null
  const hoveredPoint =
    hoveredPlayerId != null && hoveredPlayerId !== selectedPlayerId
      ? pointsById.get(hoveredPlayerId) ?? null
      : null
  const edges = similarQuery.data?.edges ?? []
  // Floating labels are rendered for:
  //   - every star in the selected player's "network" (the selected player +
  //     the top-5 similars they're connected to by a line), so the user sees
  //     the names of everyone involved in the comparison at a glance.
  //   - the currently hovered star, which floats independently.
  // De-duplicated by player id; if the hovered star is already in the network
  // we only render it once (and prefer the network styling).
  const labeledPoints: Array<{
    point: GalaxyPoint
    variant: 'hover' | 'selected' | 'linked'
  }> = []
  const seenLabelIds = new Set<string>()
  if (selectedPoint) {
    labeledPoints.push({ point: selectedPoint, variant: 'selected' })
    seenLabelIds.add(selectedPoint.galaxy_player_id)
  }
  for (const edge of edges) {
    if (seenLabelIds.has(edge.to_galaxy_player_id)) continue
    const p = pointsById.get(edge.to_galaxy_player_id)
    if (!p) continue
    labeledPoints.push({ point: p, variant: 'linked' })
    seenLabelIds.add(p.galaxy_player_id)
  }
  if (hoveredPoint && !seenLabelIds.has(hoveredPoint.galaxy_player_id)) {
    labeledPoints.push({ point: hoveredPoint, variant: 'hover' })
  }

  return (
    <div className="relative h-[calc(100svh-132px)] overflow-hidden bg-mat lg:h-[calc(100svh-52px)]">
      <div className="absolute inset-0 opacity-60 pointer-events-none bg-[radial-gradient(circle_at_20%_20%,#31243d_0%,#0b0f1f_40%,#05070f_100%)]" />

      <HudFrame
        className="absolute left-3 right-3 top-3 z-20 hidden max-h-[34svh] overflow-hidden sm:left-4 sm:right-auto sm:w-80 lg:block lg:max-h-none lg:w-72"
        header={`Target // ${scopeLabel}`}
      >
        <div className="max-h-[calc(34svh-36px)] space-y-2 overflow-y-auto p-3 lg:max-h-none lg:overflow-visible">
          <input
            type="search"
            placeholder="SEARCH PLAYER"
            value={search}
            onChange={event => setSearch(event.target.value)}
            className="w-full border border-electric/30 bg-mat/80 px-2 py-1.5 text-[16px] uppercase tracking-widest placeholder:text-electric/40 focus:border-electric focus:outline-none lg:text-[11px]"
          />
          <div className="grid grid-cols-2 gap-2">
            <HudMultiSelectDropdown
              label="Positions"
              options={POSITION_FILTER_OPTIONS}
              selected={filters.position_group}
              onChange={position_group => setFilter({ position_group })}
              emptyLabel="All Pos"
              className="min-w-0"
            />
            <MinutesInput
              key={`${filters.min_minutes}:${data.model_meta.min_minutes}`}
              value={filters.min_minutes}
              floor={data.model_meta.min_minutes}
              onCommit={min_minutes => setFilter({ min_minutes })}
            />
          </div>
          <p className="text-[10px] uppercase tracking-[0.16em] text-electric/50">
            Model floor: {data.model_meta.min_minutes} minutes
          </p>
          <HudMultiSelectDropdown
            label="Clubs"
            options={knownTeams.map(team => ({ value: team, label: team }))}
            selected={filters.team}
            onChange={team => setFilter({ team })}
            emptyLabel="All Teams"
            searchPlaceholder="Search club..."
          />
          <HudDivider />
          <div className="max-h-72 overflow-auto border border-electric/15 bg-mat/40">
            {(data.players ?? [])
              .filter(player => {
                if (!search) return true
                return player.canonical_player_name
                  .toLowerCase()
                  .includes(search.toLowerCase())
              })
              .sort((a, b) =>
                a.canonical_player_name.localeCompare(b.canonical_player_name),
              )
              .map(player => {
                const isSelected = player.galaxy_player_id === selectedPlayerId
                const isHovered = player.galaxy_player_id === hoveredPlayerId
                return (
                  <button
                    key={player.galaxy_player_id}
                    title={player.canonical_player_name}
                    className={cn(
                      'w-full flex items-center gap-2 px-2 py-1 text-[11px] border-b last:border-b-0 border-electric/10 transition-colors text-left',
                      'hover:bg-electric/10 hover:text-electric',
                      isSelected && 'bg-electric/15 text-electric',
                      isHovered && !isSelected && 'text-ink',
                    )}
                    onClick={() => selectGalaxyPlayer(player.galaxy_player_id)}
                    onMouseEnter={() =>
                      setHoveredPlayerId(player.galaxy_player_id)
                    }
                    onMouseLeave={() =>
                      setHoveredPlayerId(prev =>
                        prev === player.galaxy_player_id ? null : prev,
                      )
                    }
                  >
                    <span className="text-electric/40 font-mono shrink-0">
                      {isSelected ? '▸' : '·'}
                    </span>
                    <span className="truncate">
                      {player.canonical_player_name}
                      {player.competition_code ? ` · ${player.competition_code}` : ''}
                    </span>
                  </button>
                )
              })}
          </div>
        </div>
      </HudFrame>

      <button
        type="button"
        onClick={() => {
          setMobileSearchOpen(open => !open)
          setHoveredPlayerId(null)
        }}
        className={cn(
          'absolute left-3 top-3 z-30 flex items-center gap-2 border px-3 py-2 text-[11px] font-medium uppercase tracking-[0.18em] shadow-[0_12px_32px_-14px_rgba(74,158,245,0.75)] lg:hidden',
          mobileSearchOpen
            ? 'border-electric bg-electric/15 text-electric'
            : 'border-electric/30 bg-panel/85 text-electric/90 backdrop-blur-md',
        )}
      >
        <Search size={14} />
        Search
      </button>

      {mobileSearchOpen && (
        <HudFrame
          className="absolute left-3 right-3 top-14 z-30 max-h-[42svh] overflow-hidden lg:hidden"
          header={`Search // ${scopeLabel}`}
        >
          <div className="max-h-[calc(42svh-34px)] space-y-2 overflow-y-auto p-3">
            <input
              type="search"
              autoFocus
              placeholder="SEARCH PLAYER"
              value={search}
              onChange={event => setSearch(event.target.value)}
              className="w-full border border-electric/30 bg-mat/80 px-2 py-2 text-[16px] uppercase tracking-widest text-ink placeholder:text-electric/40 focus:border-electric focus:outline-none lg:text-[12px]"
            />
            <div className="grid grid-cols-2 gap-2">
              <HudMultiSelectDropdown
                label="Positions"
                options={POSITION_FILTER_OPTIONS}
                selected={filters.position_group}
                onChange={position_group => setFilter({ position_group })}
                emptyLabel="All Pos"
                className="min-w-0"
              />
              <MinutesInput
                key={`mobile:${filters.min_minutes}:${data.model_meta.min_minutes}`}
                value={filters.min_minutes}
                floor={data.model_meta.min_minutes}
                onCommit={min_minutes => setFilter({ min_minutes })}
              />
            </div>
            <p className="text-[10px] uppercase tracking-[0.16em] text-electric/50">
              Model floor: {data.model_meta.min_minutes} minutes
            </p>
            {search.trim() && (
              <div className="border border-electric/15 bg-mat/50">
                {mobileSearchResults.length ? (
                  mobileSearchResults.map(player => (
                    <button
                      key={player.galaxy_player_id}
                      type="button"
                      onClick={() => selectGalaxyPlayer(player.galaxy_player_id)}
                      className="flex w-full items-center gap-2 border-b border-electric/10 px-2 py-2 text-left text-[12px] text-ink-dim transition-colors last:border-b-0 hover:bg-electric/10 hover:text-electric"
                    >
                      <span className="text-electric/45 font-mono">·</span>
                      <span className="min-w-0 flex-1 truncate">{player.canonical_player_name}</span>
                      <span className="shrink-0 text-[10px] font-mono text-electric/60">
                        {player.competition_code}
                      </span>
                    </button>
                  ))
                ) : (
                  <p className="px-3 py-3 text-center text-[11px] uppercase tracking-[0.18em] text-ink-muted">
                    No players found
                  </p>
                )}
              </div>
            )}
          </div>
        </HudFrame>
      )}

      <HudFrame
        className="absolute right-4 top-4 z-20 hidden w-64 lg:block"
        header="Archetypes"
      >
        <div className="p-3 grid grid-cols-1 gap-1.5">
          {data.archetypes.map(item => (
            <div
              key={item.archetype_key}
              className="flex items-center gap-2 text-[11px] text-ink-dim"
            >
              <span
                className="size-2 rounded-full shadow-[0_0_6px_currentColor]"
                style={{ backgroundColor: item.color, color: item.color }}
              />
              <span className="tracking-wide">{item.label}</span>
            </div>
          ))}
        </div>
      </HudFrame>

      {selectedPoint && (
        <div className={cn(mobileSearchOpen && 'hidden lg:block')}>
          <PlayerHud
            point={selectedPoint}
            edges={edges}
            isLoading={similarQuery.isLoading}
            onSelectEdge={id => setSelectedPlayerId(id)}
            onHoverEdge={id => setHoveredPlayerId(id)}
            onClear={() => setSelectedPlayerId(null)}
            onOpenProfile={() =>
              navigate(buildScopedPath(`/player/${selectedPoint.canonical_player_id}`))
            }
          />
        </div>
      )}

      <Suspense
        fallback={
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 size={28} className="text-electric animate-spin" />
          </div>
        }
      >
        <GalaxyScene
          points={laidOutPoints}
          selectedPoint={selectedPoint}
          hoveredPoint={hoveredPoint}
          labeledPoints={labeledPoints}
          edges={edges}
          pointsById={pointsById}
          onSelect={setSelectedPlayerId}
          onHover={setHoveredPlayerId}
          onPointerMissed={clearMobileSelectionOnMiss}
        />
      </Suspense>
    </div>
  )
}
