import type { GalaxyPoint } from '../types/api'

const LAYOUT_SCALE = 4
const MIN_SEPARATION = 1
const RELAX_ITERATIONS = 30

function applyLayout(points: GalaxyPoint[]): GalaxyPoint[] {
  if (points.length === 0) return points
  const positions: [number, number, number][] = points.map(point => [
    point.x * LAYOUT_SCALE,
    point.y * LAYOUT_SCALE,
    point.z * LAYOUT_SCALE,
  ])
  const minSq = MIN_SEPARATION * MIN_SEPARATION
  const total = positions.length

  for (let iteration = 0; iteration < RELAX_ITERATIONS; iteration += 1) {
    let anyOverlap = false
    for (let leftIndex = 0; leftIndex < total; leftIndex += 1) {
      for (let rightIndex = leftIndex + 1; rightIndex < total; rightIndex += 1) {
        const left = positions[leftIndex]
        const right = positions[rightIndex]
        const dx = right[0] - left[0]
        const dy = right[1] - left[1]
        const dz = right[2] - left[2]
        const distanceSq = dx * dx + dy * dy + dz * dz
        if (distanceSq >= minSq || distanceSq === 0) continue
        anyOverlap = true
        const distance = Math.sqrt(distanceSq)
        const push = (MIN_SEPARATION - distance) / 2
        const ux = dx / distance
        const uy = dy / distance
        const uz = dz / distance
        left[0] -= ux * push
        left[1] -= uy * push
        left[2] -= uz * push
        right[0] += ux * push
        right[1] += uy * push
        right[2] += uz * push
      }
    }
    if (!anyOverlap) break
  }

  let centerX = 0
  let centerY = 0
  let centerZ = 0
  for (const point of positions) {
    centerX += point[0]
    centerY += point[1]
    centerZ += point[2]
  }
  centerX /= total
  centerY /= total
  centerZ /= total

  for (const point of positions) {
    point[0] -= centerX
    point[1] -= centerY
    point[2] -= centerZ
  }

  return points.map((point, index) => ({
    ...point,
    x: positions[index][0],
    y: positions[index][1],
    z: positions[index][2],
  }))
}

self.onmessage = (event: MessageEvent<GalaxyPoint[]>) => {
  self.postMessage(applyLayout(event.data))
}
