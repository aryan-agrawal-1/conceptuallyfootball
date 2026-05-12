import { Canvas, useFrame, useThree, type ThreeEvent } from '@react-three/fiber'
import { Html, Line, OrbitControls, Stars } from '@react-three/drei'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib'
import { cn } from '../../lib/utils'
import type { GalaxyEdge, GalaxyPoint } from '../../types/api'

type GalaxyLabel = {
  point: GalaxyPoint
  variant: 'hover' | 'selected' | 'linked'
}

interface GalaxySceneProps {
  points: GalaxyPoint[]
  selectedPoint: GalaxyPoint | null
  hoveredPoint: GalaxyPoint | null
  labeledPoints: GalaxyLabel[]
  edges: GalaxyEdge[]
  pointsById: Map<string, GalaxyPoint>
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
  onPointerMissed: () => void
}

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

function sizeFromMinutes(minutes: number, range: { min: number; max: number }): number {
  if (range.max <= range.min) return 1
  const t = (minutes - range.min) / (range.max - range.min)
  return 0.9 + t * 0.35
}

function GalaxyStars({
  points,
  onSelect,
  onHover,
}: {
  points: GalaxyPoint[]
  onSelect: (id: string) => void
  onHover: (id: string | null) => void
}) {
  const texture = useMemo(() => makeStarTexture(), [])

  const { positions, colors, sizes, indexToPlayerId } = useMemo(() => {
    const positions = new Float32Array(points.length * 3)
    const colors = new Float32Array(points.length * 3)
    const sizes = new Float32Array(points.length)
    const indexToPlayerId: string[] = []
    const minutesList = points.map(point => point.minutes)
    const range = {
      min: Math.min(...minutesList, 0),
      max: Math.max(...minutesList, 1),
    }
    const colorObj = new THREE.Color()

    points.forEach((point, index) => {
      positions[index * 3 + 0] = point.x
      positions[index * 3 + 1] = point.y
      positions[index * 3 + 2] = point.z
      colorObj.set(point.cluster_color)
      colors[index * 3 + 0] = colorObj.r
      colors[index * 3 + 1] = colorObj.g
      colors[index * 3 + 2] = colorObj.b
      sizes[index] = sizeFromMinutes(point.minutes, range)
      indexToPlayerId.push(point.galaxy_player_id)
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

  function handlePointerMove(event: ThreeEvent<PointerEvent>) {
    event.stopPropagation()
    const index = event.index
    if (typeof index !== 'number') return
    const playerId = indexToPlayerId[index]
    if (playerId != null) onHover(playerId)
  }

  return (
    <group>
      <points
        material={coloredHalo}
        onClick={handleClick}
        onPointerMove={handlePointerMove}
        onPointerOut={() => onHover(null)}
      >
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[colors, 3]} />
          <bufferAttribute attach="attributes-size" args={[sizes, 1]} />
        </bufferGeometry>
      </points>
      <points material={whiteCore} raycast={() => null}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
      </points>
    </group>
  )
}

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

function HoverPulse({ point }: { point: GalaxyPoint }) {
  const ringRef = useRef<THREE.Mesh>(null)
  useFrame(state => {
    if (!ringRef.current) return
    const pulse = 1 + Math.sin(state.clock.elapsedTime * 3.2) * 0.18
    ringRef.current.scale.setScalar(pulse)
  })
  return (
    <group position={[point.x, point.y, point.z]}>
      <mesh ref={ringRef}>
        <ringGeometry args={[0.45, 0.52, 48]} />
        <meshBasicMaterial color={point.cluster_color} transparent opacity={0.75} side={THREE.DoubleSide} />
      </mesh>
    </group>
  )
}

function PlayerLabel({ point, variant = 'hover' }: GalaxyLabel) {
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
      zIndexRange={[10, 0]}
      style={{ pointerEvents: 'none' }}
    >
      <div
        className={cn(
          'relative px-1.5 py-0.5 text-[11px] whitespace-nowrap backdrop-blur border',
          variant === 'selected' && 'border-electric bg-electric/20 text-ink font-medium tracking-wide',
          variant === 'linked' && 'border-electric/60 bg-panel/80 text-ink',
          variant === 'hover' && 'border-electric/40 bg-panel/90 text-ink',
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

const FOCUS_DISTANCE = 5.5
const FOCUS_LERP = 0.1
const FOCUS_EPSILON = 0.02

function CameraFocus({ target }: { target: GalaxyPoint | null }) {
  const { camera } = useThree()
  const controls = useThree(state => state.controls as OrbitControlsImpl | null)
  const goalTarget = useRef(new THREE.Vector3())
  const goalCamera = useRef(new THREE.Vector3())
  const animating = useRef(false)
  const lastTargetId = useRef<string | null>(null)

  useFrame(() => {
    if (!controls) return
    const targetId = target?.galaxy_player_id ?? null
    if (targetId !== lastTargetId.current) {
      lastTargetId.current = targetId
      if (target) {
        goalTarget.current.set(target.x, target.y, target.z)
        const direction = new THREE.Vector3()
          .subVectors(camera.position, controls.target)
          .normalize()
        goalCamera.current.copy(goalTarget.current).add(direction.multiplyScalar(FOCUS_DISTANCE))
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

function SimilarityLines({
  edges,
  pointsById,
  from,
}: {
  edges: GalaxyEdge[]
  pointsById: Map<string, GalaxyPoint>
  from: GalaxyPoint
}) {
  if (!edges.length) return null
  return (
    <>
      {edges.map(edge => {
        const to = pointsById.get(edge.to_galaxy_player_id)
        if (!to) return null
        return (
          <Line
            key={`${edge.from_galaxy_player_id}-${edge.to_galaxy_player_id}`}
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

export function GalaxyScene({
  points,
  selectedPoint,
  hoveredPoint,
  labeledPoints,
  edges,
  pointsById,
  onSelect,
  onHover,
  onPointerMissed,
}: GalaxySceneProps) {
  return (
    <Canvas
      onPointerMissed={onPointerMissed}
      camera={{ position: [0, 0, 28], fov: 60 }}
      dpr={[1, 1.5]}
      gl={{ powerPreference: 'high-performance', antialias: true }}
      onCreated={state => {
        state.raycaster.params.Points = { threshold: 0.3 }
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
      <GalaxyStars points={points} onSelect={onSelect} onHover={onHover} />
      {selectedPoint && <SelectedHighlight point={selectedPoint} />}
      {hoveredPoint && <HoverPulse point={hoveredPoint} />}
      {labeledPoints.map(({ point, variant }) => (
        <PlayerLabel key={`label-${point.galaxy_player_id}`} point={point} variant={variant} />
      ))}
      {selectedPoint && <SimilarityLines edges={edges} pointsById={pointsById} from={selectedPoint} />}
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
  )
}
