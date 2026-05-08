import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { Html, Line, OrbitControls, Stars } from '@react-three/drei'
import { useMemo, useRef, useState, type ReactNode } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowUpRight, Loader2, X } from 'lucide-react'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { fetchGalaxy, fetchGalaxySimilar } from '../lib/api'
import type { GalaxyEdge, GalaxyPoint, PositionGroup } from '../types/api'
import { cn } from '../lib/utils'
import {
  HudActionButton,
  HudDivider,
  HudFrame,
} from '../components/hud/Hud'
import { useScope } from '../context/ScopeContext'

const DEFAULT_FILTERS = {
  position_group: '',
  team: '',
  min_minutes: 900,
}

// ─── Star sprite ──────────────────────────────────────────────────────────────
// A radial-gradient sprite with a bright white core and soft falloff. When it's
// tinted by vertexColors + AdditiveBlending, colors show as a halo around a
// near-white center — which is the "colored star" look in the reference.

function makeStarTexture(): THREE.Texture {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const grad = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  grad.addColorStop(0.0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.15, 'rgba(255,255,255,0.85)')
  grad.addColorStop(0.4, 'rgba(255,255,255,0.25)')
  grad.addColorStop(1.0, 'rgba(255,255,255,0)')
  ctx.fillStyle = grad
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.needsUpdate = true
  return tex
}

// Scales minutes into a subtle sprite-size multiplier (kept narrow per spec).
function sizeFromMinutes(minutes: number, range: { min: number; max: number }): number {
  if (range.max <= range.min) return 1
  const t = (minutes - range.min) / (range.max - range.min)
  return 0.9 + t * 0.35
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

const LAYOUT_SCALE = 4
const MIN_SEPARATION = 1
const RELAX_ITERATIONS = 30

function applyLayout(points: GalaxyPoint[]): GalaxyPoint[] {
  if (points.length === 0) return points
  const positions: [number, number, number][] = points.map(p => [
    p.x * LAYOUT_SCALE,
    p.y * LAYOUT_SCALE,
    p.z * LAYOUT_SCALE,
  ])
  const minSq = MIN_SEPARATION * MIN_SEPARATION
  const n = positions.length

  for (let iter = 0; iter < RELAX_ITERATIONS; iter++) {
    let anyOverlap = false
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const a = positions[i]
        const b = positions[j]
        const dx = b[0] - a[0]
        const dy = b[1] - a[1]
        const dz = b[2] - a[2]
        const d2 = dx * dx + dy * dy + dz * dz
        if (d2 >= minSq || d2 === 0) continue
        anyOverlap = true
        const d = Math.sqrt(d2)
        const push = (MIN_SEPARATION - d) / 2
        const ux = dx / d
        const uy = dy / d
        const uz = dz / d
        a[0] -= ux * push
        a[1] -= uy * push
        a[2] -= uz * push
        b[0] += ux * push
        b[1] += uy * push
        b[2] += uz * push
      }
    }
    if (!anyOverlap) break
  }

  // Recenter: UMAP returns coordinates with an arbitrary origin, so the
  // cluster's center of mass almost never lands at (0,0,0). If we don't fix
  // that, the default camera (which looks at the origin) frames empty space
  // on one side and the cluster on the other. Shifting every point by the
  // centroid snaps the galaxy to the middle of the view on first paint.
  let cx = 0
  let cy = 0
  let cz = 0
  for (const p of positions) {
    cx += p[0]
    cy += p[1]
    cz += p[2]
  }
  cx /= n
  cy /= n
  cz /= n
  for (const p of positions) {
    p[0] -= cx
    p[1] -= cy
    p[2] -= cz
  }

  return points.map((p, i) => ({
    ...p,
    x: positions[i][0],
    y: positions[i][1],
    z: positions[i][2],
  }))
}

// ─── Stars (single Points mesh, one draw call) ────────────────────────────────

function GalaxyStars({
  points,
  onSelect,
  onHover,
}: {
  points: GalaxyPoint[]
  onSelect: (id: number) => void
  onHover: (id: number | null) => void
}) {
  const texture = useMemo(() => makeStarTexture(), [])

  const { positions, colors, sizes, indexToPlayerId } = useMemo(() => {
    const positions = new Float32Array(points.length * 3)
    const colors = new Float32Array(points.length * 3)
    const sizes = new Float32Array(points.length)
    const indexToPlayerId: number[] = []

    const minutesList = points.map(p => p.minutes)
    const range = {
      min: Math.min(...minutesList, 0),
      max: Math.max(...minutesList, 1),
    }

    const colorObj = new THREE.Color()
    points.forEach((point, i) => {
      positions[i * 3 + 0] = point.x
      positions[i * 3 + 1] = point.y
      positions[i * 3 + 2] = point.z
      colorObj.set(point.cluster_color)
      colors[i * 3 + 0] = colorObj.r
      colors[i * 3 + 1] = colorObj.g
      colors[i * 3 + 2] = colorObj.b
      sizes[i] = sizeFromMinutes(point.minutes, range)
      indexToPlayerId.push(point.canonical_player_id)
    })

    return { positions, colors, sizes, indexToPlayerId }
  }, [points])

  const coloredHalo = useMemo(
    () =>
      new THREE.PointsMaterial({
        size: 0.65,
        map: texture,
        vertexColors: true,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true,
      }),
    [texture],
  )

  const whiteCore = useMemo(
    () =>
      new THREE.PointsMaterial({
        size: 0.22,
        map: texture,
        color: 0xffffff,
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
        sizeAttenuation: true,
      }),
    [texture],
  )

  function handleClick(event: ThreeEvent<MouseEvent>) {
    event.stopPropagation()
    const index = event.index
    if (typeof index !== 'number') return
    const playerId = indexToPlayerId[index]
    if (playerId != null) onSelect(playerId)
  }

  // `onPointerMove` on a Points object fires with `event.index` set to the
  // nearest point the raycaster hit. We translate that back to a player id
  // and surface it upward. `onPointerOut` fires when the pointer leaves the
  // entire Points object so we clear hover state there.
  function handlePointerMove(event: ThreeEvent<PointerEvent>) {
    event.stopPropagation()
    const index = event.index
    if (typeof index !== 'number') return
    const playerId = indexToPlayerId[index]
    if (playerId != null) onHover(playerId)
  }

  function handlePointerOut() {
    onHover(null)
  }

  return (
    <group>
      {/* Halo layer: colored, larger, picks up click events */}
      <points
        material={coloredHalo}
        onClick={handleClick}
        onPointerMove={handlePointerMove}
        onPointerOut={handlePointerOut}
      >
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
          />
          <bufferAttribute
            attach="attributes-color"
            args={[colors, 3]}
          />
          <bufferAttribute
            attach="attributes-size"
            args={[sizes, 1]}
          />
        </bufferGeometry>
      </points>

      {/* Core layer: bright white center, non-interactive */}
      <points material={whiteCore} raycast={() => null}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
          />
        </bufferGeometry>
      </points>
    </group>
  )
}

// ─── Selected-player highlight ────────────────────────────────────────────────

function SelectedHighlight({ point }: { point: GalaxyPoint }) {
  return (
    <group position={[point.x, point.y, point.z]}>
      <mesh>
        <ringGeometry args={[0.55, 0.62, 48]} />
        <meshBasicMaterial color={point.cluster_color} transparent opacity={0.9} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

// ─── Hover pulse ─────────────────────────────────────────────────────────────
// A ring that sits on the hovered star and gently breathes in/out. We animate
// scale rather than geometry so the ring mesh is built once and we just push a
// scalar per frame. `useFrame` runs inside the R3F render loop — cheap.

function HoverPulse({ point }: { point: GalaxyPoint }) {
  const ringRef = useRef<THREE.Mesh>(null)
  useFrame(state => {
    if (!ringRef.current) return
    const t = state.clock.elapsedTime
    const pulse = 1 + Math.sin(t * 3.2) * 0.18
    ringRef.current.scale.setScalar(pulse)
  })
  return (
    <group position={[point.x, point.y, point.z]}>
      <mesh ref={ringRef}>
        <ringGeometry args={[0.45, 0.52, 48]} />
        <meshBasicMaterial
          color={point.cluster_color}
          transparent
          opacity={0.75}
          side={THREE.DoubleSide}
        />
      </mesh>
    </group>
  )
}

// ─── Floating player label ───────────────────────────────────────────────────
// Renders a DOM element via `<Html>` positioned in 3D space. Used both for the
// hovered star and for the selected player + its linked comps. `variant` lets
// us visually distinguish "network" labels (the selected player and its top-5
// similars) from a plain hover.

function PlayerLabel({
  point,
  variant = 'hover',
}: {
  point: GalaxyPoint
  variant?: 'hover' | 'selected' | 'linked'
}) {
  // Each variant's bracket tone matches its border — selected is the boldest,
  // linked is a softened electric, hover is the dimmest. This lets a user
  // scan a clicked player's network at a glance while still getting a light
  // readout on casual hover.
  const bracketClass = cn(
    'absolute size-1 pointer-events-none',
    variant === 'selected' && 'border-electric',
    variant === 'linked' && 'border-electric/70',
    variant === 'hover' && 'border-electric/50',
  )

  return (
    <Html
      position={[point.x, point.y + 0.55, point.z]}
      center
      distanceFactor={12}
      zIndexRange={[50, 0]}
      style={{ pointerEvents: 'none' }}
    >
      <div
        className={cn(
          'relative px-1.5 py-0.5 text-[11px] whitespace-nowrap backdrop-blur border',
          variant === 'selected' &&
            'border-electric bg-electric/20 text-ink font-medium tracking-wide',
          variant === 'linked' &&
            'border-electric/60 bg-panel/80 text-ink',
          variant === 'hover' &&
            'border-electric/40 bg-panel/90 text-ink',
        )}
      >
        <span className={cn(bracketClass, '-top-px -left-px border-t border-l')} />
        <span className={cn(bracketClass, '-top-px -right-px border-t border-r')} />
        <span className={cn(bracketClass, '-bottom-px -left-px border-b border-l')} />
        <span className={cn(bracketClass, '-bottom-px -right-px border-b border-r')} />
        {point.canonical_player_name}
      </div>
    </Html>
  )
}

// ─── Camera focus animation ──────────────────────────────────────────────────
// When `target` changes, smoothly slide the camera AND the OrbitControls
// pivot toward the selected star. We preserve the current view direction so
// the user's rotation isn't thrown out — we just translate the orbit origin
// and pull the camera closer. OrbitControls is registered with `makeDefault`
// below so `useThree(state => state.controls)` returns it.
//
// Note: we lerp every frame while `animating` is true; once the camera is
// within an epsilon of its goal we stop updating so idle frames do no work.

const FOCUS_DISTANCE = 5.5
const FOCUS_LERP = 0.1
const FOCUS_EPSILON = 0.02

function CameraFocus({ target }: { target: GalaxyPoint | null }) {
  const { camera } = useThree()
  const controls = useThree(state => state.controls as OrbitControlsImpl | null)

  const goalTarget = useRef(new THREE.Vector3())
  const goalCamera = useRef(new THREE.Vector3())
  const animating = useRef(false)
  const lastTargetId = useRef<number | null>(null)

  useFrame(() => {
    if (!controls) return
    const targetId = target?.canonical_player_id ?? null

    if (targetId !== lastTargetId.current) {
      lastTargetId.current = targetId
      if (target) {
        goalTarget.current.set(target.x, target.y, target.z)
        // Keep the current view direction; just shorten the distance.
        const direction = new THREE.Vector3()
          .subVectors(camera.position, controls.target)
          .normalize()
        goalCamera.current
          .copy(goalTarget.current)
          .add(direction.multiplyScalar(FOCUS_DISTANCE))
        animating.current = true
      } else {
        animating.current = false
      }
    }

    if (!animating.current) return
    controls.target.lerp(goalTarget.current, FOCUS_LERP)
    camera.position.lerp(goalCamera.current, FOCUS_LERP)
    controls.update()

    if (
      camera.position.distanceTo(goalCamera.current) < FOCUS_EPSILON &&
      controls.target.distanceTo(goalTarget.current) < FOCUS_EPSILON
    ) {
      animating.current = false
    }
  })

  return null
}

// ─── Similarity lines ─────────────────────────────────────────────────────────

function SimilarityLines({
  edges,
  pointsById,
  from,
}: {
  edges: GalaxyEdge[]
  pointsById: Map<number, GalaxyPoint>
  from: GalaxyPoint
}) {
  if (!edges.length) return null
  return (
    <>
      {edges.map(edge => {
        const to = pointsById.get(edge.to_player_id)
        if (!to) return null
        return (
          <Line
            key={`${edge.from_player_id}-${edge.to_player_id}`}
            points={[
              [from.x, from.y, from.z],
              [to.x, to.y, to.z],
            ]}
            color={to.cluster_color}
            lineWidth={1.25}
            transparent
            opacity={0.8}
          />
        )
      })}
    </>
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
  onSelectEdge: (id: number) => void
  onHoverEdge: (id: number | null) => void
  onClear: () => void
  onOpenProfile: () => void
}) {
  const { buildScopedPath } = useScope()
  return (
    <HudFrame
      className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 w-[min(760px,calc(100%-2rem))]"
      header={`Target Acquired // ID ${point.canonical_player_id.toString().padStart(6, '0')}`}
      footer={
        <div className="flex justify-between items-center">
          <span>Cluster {point.cluster_id + 1} // {point.cluster_label}</span>
          <span className="font-mono">
            X {point.x.toFixed(2)}  Y {point.y.toFixed(2)}  Z {point.z.toFixed(2)}
          </span>
        </div>
      }
    >
      <div className="grid grid-cols-[1.3fr_1fr_auto] gap-4 p-4 items-stretch">
        {/* Identity column */}
        <div className="flex flex-col gap-3 min-w-0">
          <div>
            <p className="text-[10px] uppercase tracking-[0.25em] text-electric/70 mb-1">
              Player
            </p>
            <p className="text-[22px] leading-tight font-bold text-ink truncate">
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
          <div className="flex items-center gap-3">
            <PositionBadge position={point.position_group} />
            <span className="text-[10px] uppercase tracking-[0.2em] text-electric/70">
              {point.cluster_label}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-3 pt-1">
            <StatReadout label="Minutes" value={point.minutes.toLocaleString()} />
            <StatReadout
              label="Archetype"
              value={<span className="text-[12px]">{point.cluster_label}</span>}
            />
          </div>
        </div>

        {/* Top comps column */}
        <div className="flex flex-col min-w-0">
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
                  key={edge.to_player_id}
                  onClick={() => onSelectEdge(edge.to_player_id)}
                  onMouseEnter={() => onHoverEdge(edge.to_player_id)}
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
                    {Math.round(edge.similarity * 100)}%
                  </span>
                </button>
              ))
            )}
          </div>
        </div>

        {/* Actions column */}
        <div className="flex flex-col justify-between items-end gap-2 min-w-[140px]">
          <button
            onClick={onClear}
            className="flex items-center gap-1 text-[10px] uppercase tracking-[0.2em] text-ink-dim hover:text-ink"
          >
            <X size={12} />
            Clear
          </button>
          <HudActionButton onClick={onOpenProfile} className="w-full">
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
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null)
  const [hoveredPlayerId, setHoveredPlayerId] = useState<number | null>(null)
  const [search, setSearch] = useState('')

  const filters = {
    competition: scope.competition,
    season: scope.season,
    min_minutes: Number(params.get('min_minutes') ?? DEFAULT_FILTERS.min_minutes),
    position_group: params.get('position_group') ?? DEFAULT_FILTERS.position_group,
    team: params.get('team') ?? DEFAULT_FILTERS.team,
  }

  const galaxyQuery = useQuery({
    queryKey: ['galaxy', filters],
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
      fetchGalaxySimilar(selectedPlayerId as number, filters.competition, filters.season),
    enabled: selectedPlayerId != null,
  })

  const data = galaxyQuery.data

  // Apply the scale + repulsion pass *once* per galaxy payload. Everything
  // downstream (sprites, highlight ring, similarity lines) reads from these
  // relaxed positions so they all stay in sync.
  const laidOutPoints = useMemo(() => applyLayout(data?.points ?? []), [data?.points])

  const pointsById = useMemo(() => {
    const m = new Map<number, GalaxyPoint>()
    for (const point of laidOutPoints) m.set(point.canonical_player_id, point)
    return m
  }, [laidOutPoints])

  const teams = useMemo(() => {
    const names = (data?.points ?? [])
      .map(point => point.canonical_team_name)
      .filter((team): team is string => Boolean(team))
    return [...new Set(names)].sort((a, b) => a.localeCompare(b))
  }, [data?.points])

  function setFilter(next: Partial<typeof filters>) {
    const nextParams = new URLSearchParams(params)
    if ('position_group' in next) {
      const value = next.position_group ?? ''
      if (value) nextParams.set('position_group', value)
      else nextParams.delete('position_group')
    }
    if ('team' in next) {
      const value = next.team ?? ''
      if (value) nextParams.set('team', value)
      else nextParams.delete('team')
    }
    if ('min_minutes' in next) {
      nextParams.set('min_minutes', String(next.min_minutes ?? DEFAULT_FILTERS.min_minutes))
    }
    setParams(nextParams)
  }

  if (galaxyQuery.isLoading) {
    return (
      <div className="flex items-center justify-center h-[calc(100svh-52px)]">
        <Loader2 size={28} className="text-electric animate-spin" />
      </div>
    )
  }
  if (galaxyQuery.isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100svh-52px)] gap-3">
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
  const seenLabelIds = new Set<number>()
  if (selectedPoint) {
    labeledPoints.push({ point: selectedPoint, variant: 'selected' })
    seenLabelIds.add(selectedPoint.canonical_player_id)
  }
  for (const edge of edges) {
    if (seenLabelIds.has(edge.to_player_id)) continue
    const p = pointsById.get(edge.to_player_id)
    if (!p) continue
    labeledPoints.push({ point: p, variant: 'linked' })
    seenLabelIds.add(p.canonical_player_id)
  }
  if (hoveredPoint && !seenLabelIds.has(hoveredPoint.canonical_player_id)) {
    labeledPoints.push({ point: hoveredPoint, variant: 'hover' })
  }

  return (
    <div className="h-[calc(100svh-52px)] relative bg-mat overflow-hidden">
      <div className="absolute inset-0 opacity-60 pointer-events-none bg-[radial-gradient(circle_at_20%_20%,#31243d_0%,#0b0f1f_40%,#05070f_100%)]" />

      <HudFrame
        className="absolute top-4 left-4 z-20 w-72"
        header={`Target // ${scopeLabel}`}
      >
        <div className="p-3 space-y-2">
          <input
            type="search"
            placeholder="SEARCH PLAYER"
            value={search}
            onChange={event => setSearch(event.target.value)}
            className="w-full bg-mat/80 border border-electric/30 px-2 py-1.5 text-[11px] tracking-widest uppercase placeholder:text-electric/40 focus:outline-none focus:border-electric"
          />
          <div className="grid grid-cols-2 gap-2">
            <select
              className="bg-mat/80 border border-electric/25 text-[11px] px-2 py-1.5 tracking-widest text-electric/90 focus:outline-none focus:border-electric"
              value={filters.position_group}
              onChange={event => setFilter({ position_group: event.target.value })}
            >
              <option value="">ALL POS</option>
              <option value="FWD">FWD</option>
              <option value="MID">MID</option>
              <option value="DEF">DEF</option>
              <option value="GK">GK</option>
            </select>
            <input
              type="number"
              className="bg-mat/80 border border-electric/25 text-[11px] px-2 py-1.5 font-mono text-electric/90 focus:outline-none focus:border-electric"
              value={filters.min_minutes}
              min={0}
              onChange={event => setFilter({ min_minutes: Number(event.target.value) || 0 })}
            />
          </div>
          <select
            className="w-full bg-mat/80 border border-electric/25 text-[11px] px-2 py-1.5 tracking-widest text-electric/90 focus:outline-none focus:border-electric"
            value={filters.team}
            onChange={event => setFilter({ team: event.target.value })}
          >
            <option value="">ALL TEAMS</option>
            {teams.map(team => (
              <option key={team} value={team}>
                {team}
              </option>
            ))}
          </select>
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
                const isSelected = player.canonical_player_id === selectedPlayerId
                const isHovered = player.canonical_player_id === hoveredPlayerId
                return (
                  <button
                    key={player.canonical_player_id}
                    title={player.canonical_player_name}
                    className={cn(
                      'w-full flex items-center gap-2 px-2 py-1 text-[11px] border-b last:border-b-0 border-electric/10 transition-colors text-left',
                      'hover:bg-electric/10 hover:text-electric',
                      isSelected && 'bg-electric/15 text-electric',
                      isHovered && !isSelected && 'text-ink',
                    )}
                    onClick={() => setSelectedPlayerId(player.canonical_player_id)}
                    onMouseEnter={() =>
                      setHoveredPlayerId(player.canonical_player_id)
                    }
                    onMouseLeave={() =>
                      setHoveredPlayerId(prev =>
                        prev === player.canonical_player_id ? null : prev,
                      )
                    }
                  >
                    <span className="text-electric/40 font-mono shrink-0">
                      {isSelected ? '▸' : '·'}
                    </span>
                    <span className="truncate">
                      {player.canonical_player_name}
                    </span>
                  </button>
                )
              })}
          </div>
        </div>
      </HudFrame>

      <HudFrame
        className="absolute top-4 right-4 z-20 w-64"
        header="Archetypes"
      >
        <div className="p-3 grid grid-cols-1 gap-1.5">
          {data.archetypes.map(item => (
            <div
              key={item.cluster_id}
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
      )}

      <Canvas
        camera={{ position: [0, 0, 28], fov: 60 }}
        // Cap DPR at 1.5 to keep the backing buffer small on Retina/hi-DPI
        // displays. At 1.75–2x, the combination of additively-blended star
        // sprites, SDF text atlases (archetype labels) and the Stars
        // background can blow past the GPU's per-context budget on some
        // machines, which manifests as an immediate "Context Lost".
        dpr={[1, 1.5]}
        // `powerPreference: 'high-performance'` asks the browser to use the
        // discrete GPU when available instead of integrated graphics — the
        // integrated path is where we saw context loss on macOS.
        gl={{ powerPreference: 'high-performance', antialias: true }}
        onCreated={state => {
          state.raycaster.params.Points = { threshold: 0.3 }
          // By default, when WebGL loses its context, three.js stops
          // rendering. Calling `preventDefault()` tells the browser "we'll
          // handle it" — and three.js has built-in logic to recreate its
          // resources (textures, buffers, programs) when the context is
          // restored, so the galaxy just picks back up.
          const canvas = state.gl.domElement
          canvas.addEventListener(
            'webglcontextlost',
            event => {
              event.preventDefault()
            },
            false,
          )
        }}
      >
        <color attach="background" args={['#060912']} />
        <Stars radius={120} depth={60} count={1600} factor={4} saturation={0} fade speed={0.3} />
        <GalaxyStars
          points={laidOutPoints}
          onSelect={setSelectedPlayerId}
          onHover={setHoveredPlayerId}
        />
        {selectedPoint && <SelectedHighlight point={selectedPoint} />}
        {hoveredPoint && <HoverPulse point={hoveredPoint} />}
        {labeledPoints.map(({ point, variant }) => (
          <PlayerLabel
            key={`label-${point.canonical_player_id}`}
            point={point}
            variant={variant}
          />
        ))}
        {selectedPoint && (
          <SimilarityLines edges={edges} pointsById={pointsById} from={selectedPoint} />
        )}
        <CameraFocus target={selectedPoint} />
        <OrbitControls
          makeDefault
          enablePan
          enableZoom
          enableRotate
          rotateSpeed={0.35}
          zoomSpeed={0.35}
          panSpeed={0.4}
          enableDamping
          dampingFactor={0.08}
          minDistance={4}
          maxDistance={55}
        />
      </Canvas>
    </div>
  )
}
