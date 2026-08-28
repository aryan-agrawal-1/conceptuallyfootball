import type { ActionGridCell, EventCarry, EventPass, TeamPassFlow } from '../../types/eventMaps'
import {
  actionGridCellBounds,
  createPitchTransform,
  type PitchTransform,
} from './pitchGeometry'

export type CanvasViewport = {
  width: number
  height: number
  devicePixelRatio: number
}

export type DenseLayerOptions = {
  selectedEventId?: string | null
  successfulColor?: string
  unsuccessfulColor?: string
  densityColor?: string
  densityDomainMax?: number
  flowColor?: string
  flowDensityColor?: string
  carryColor?: string
  densityStyle?: 'cells' | 'smooth'
  selectedFlowId?: string | null
}

export const EVENT_HEATMAP_COLOR = '#4A9EF5'

const defaultLayerOptions = {
  successfulColor: '#4A9EF5',
  unsuccessfulColor: '#EF5C66',
  densityColor: EVENT_HEATMAP_COLOR,
  flowColor: '#F0A832',
  flowDensityColor: EVENT_HEATMAP_COLOR,
}

export function configureHiDPICanvas(
  canvas: HTMLCanvasElement,
  viewport: CanvasViewport,
) {
  const width = Math.max(0, viewport.width)
  const height = Math.max(0, viewport.height)
  const devicePixelRatio = Math.max(1, viewport.devicePixelRatio)
  const backingWidth = Math.round(width * devicePixelRatio)
  const backingHeight = Math.round(height * devicePixelRatio)

  if (canvas.width !== backingWidth) canvas.width = backingWidth
  if (canvas.height !== backingHeight) canvas.height = backingHeight
  canvas.style.width = `${width}px`
  canvas.style.height = `${height}px`

  const context = canvas.getContext('2d')
  context?.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0)
  return context
}

export function drawDensityLayer(
  context: CanvasRenderingContext2D,
  cells: ActionGridCell[],
  transform: PitchTransform,
  color = defaultLayerOptions.densityColor,
  style: 'cells' | 'smooth' = 'cells',
  domainMaximum?: number,
) {
  let maximumShare = domainMaximum ?? 0
  if (domainMaximum == null) for (const cell of cells) maximumShare = Math.max(maximumShare, cell.share)
  if (maximumShare === 0) return
  const columnCount = Math.max(1, ...cells.map(cell => cell.column + 1))
  const rowCount = Math.max(1, ...cells.map(cell => cell.row + 1))

  context.save()
  context.fillStyle = color

  if (style === 'smooth') {
    const pitchCellWidth = transform.bounds.width / columnCount
    const pitchCellHeight = transform.bounds.height / rowCount
    context.filter = `blur(${Math.max(5, Math.min(pitchCellWidth, pitchCellHeight) * 1.35)}px)`
    for (const cell of cells) {
      if (cell.share <= 0) continue
      const bounds = actionGridCellBounds(cell.column, cell.row, columnCount, rowCount)
      const centre = transform.toScreen({
        x: (bounds.xMin + bounds.xMax) / 2,
        y: (bounds.yMin + bounds.yMax) / 2,
      })
      const intensity = Math.sqrt(cell.share / maximumShare)
      context.globalAlpha = 0.08 + intensity * 0.34
      context.beginPath()
      context.arc(
        centre.x,
        centre.y,
        Math.max(pitchCellWidth, pitchCellHeight) * (0.72 + intensity * 0.35),
        0,
        Math.PI * 2,
      )
      context.fill()
    }
    context.restore()
    return
  }

  for (const cell of cells) {
    if (cell.share <= 0) continue
    const bounds = actionGridCellBounds(cell.column, cell.row, columnCount, rowCount)
    const topLeft = transform.toScreen({ x: bounds.xMin, y: bounds.yMin })
    const bottomRight = transform.toScreen({ x: bounds.xMax, y: bounds.yMax })
    const intensity = Math.sqrt(cell.share / maximumShare)
    context.globalAlpha = 0.08 + intensity * 0.48
    context.fillRect(
      topLeft.x + 0.5,
      topLeft.y + 0.5,
      Math.max(0, bottomRight.x - topLeft.x - 1),
      Math.max(0, bottomRight.y - topLeft.y - 1),
    )
  }

  context.restore()
}

export function drawPassLayer(
  context: CanvasRenderingContext2D,
  passes: EventPass[],
  transform: PitchTransform,
  options: DenseLayerOptions = {},
) {
  const colors = { ...defaultLayerOptions, ...options }
  const hasSelection = Boolean(options.selectedEventId)
  const densityOpacity = passes.length > 120 ? 0.28 : passes.length > 50 ? 0.5 : 0.82

  context.save()
  context.lineCap = 'butt'

  for (const pass of passes) {
    const start = transform.toScreen(pass.start)
    const end = transform.toScreen(pass.end)
    const selected = pass.id === options.selectedEventId
    context.beginPath()
    context.moveTo(start.x, start.y)
    context.lineTo(end.x, end.y)
    context.strokeStyle = pass.color ?? (
      pass.outcome === 'successful' ? colors.successfulColor : colors.unsuccessfulColor
    )
    context.globalAlpha = selected ? 1 : hasSelection ? 0.2 : densityOpacity
    context.lineWidth = selected ? (pass.keyPass ? 2.1 : 1.65) : pass.keyPass ? 1.35 : 0.95
    context.stroke()

    const deltaX = end.x - start.x
    const deltaY = end.y - start.y
    const distance = Math.hypot(deltaX, deltaY)
    if (distance < 4) continue
    const unitX = deltaX / distance
    const unitY = deltaY / distance
    const arrowSize = selected ? 4.5 : passes.length > 120 ? 2.2 : 3
    context.beginPath()
    context.moveTo(end.x, end.y)
    context.lineTo(end.x - unitX * arrowSize - unitY * arrowSize * 0.65, end.y - unitY * arrowSize + unitX * arrowSize * 0.65)
    context.lineTo(end.x - unitX * arrowSize + unitY * arrowSize * 0.65, end.y - unitY * arrowSize - unitX * arrowSize * 0.65)
    context.closePath()
    context.fillStyle = context.strokeStyle
    context.fill()
  }

  context.restore()
}

export function drawCarryLayer(
  context: CanvasRenderingContext2D,
  carries: EventCarry[],
  transform: PitchTransform,
  options: DenseLayerOptions = {},
) {
  const colors = { ...defaultLayerOptions, ...options }
  const hasSelection = Boolean(options.selectedEventId)

  context.save()
  context.lineCap = 'round'
  context.setLineDash([5, 3])

  for (const carry of carries) {
    const start = transform.toScreen(carry.start)
    const end = transform.toScreen(carry.end)
    const selected = carry.id === options.selectedEventId
    context.beginPath()
    context.moveTo(start.x, start.y)
    context.lineTo(end.x, end.y)
    context.strokeStyle = carry.color ?? colors.carryColor ?? '#F0A832'
    context.globalAlpha = selected ? 1 : hasSelection ? 0.24 : 0.9
    context.lineWidth = selected ? 2.5 : 1.5
    context.stroke()

    context.setLineDash([])
    context.beginPath()
    context.arc(end.x, end.y, selected ? 3 : 1.8, 0, Math.PI * 2)
    context.fillStyle = context.strokeStyle
    context.fill()
    context.setLineDash([5, 3])
  }

  context.restore()
}

export function drawFlowLayer(
  context: CanvasRenderingContext2D,
  flows: TeamPassFlow[],
  transform: PitchTransform,
  options: Pick<DenseLayerOptions, 'flowColor' | 'flowDensityColor' | 'selectedFlowId'> = {},
) {
  const densityColor = options.flowDensityColor ?? defaultLayerOptions.flowDensityColor
  const bins = new Map<string, { flows: TeamPassFlow[]; volume: number }>()

  for (const flow of flows) {
    const key = `${flow.bin.column}-${flow.bin.row}`
    const bin = bins.get(key) ?? { flows: [], volume: 0 }
    bin.flows.push(flow)
    bin.volume += flow.gameState
      ? flow.attemptsPerStateMinute ?? 0
      : flow.attemptedCount ?? flow.completedCount
    bins.set(key, bin)
  }

  const maximumVolume = Math.max(0, ...Array.from(bins.values(), bin => bin.volume))
  if (maximumVolume === 0) return

  context.save()
  context.lineCap = 'round'
  context.lineJoin = 'round'

  for (const bin of bins.values()) {
    if (bin.volume === 0) continue
    const flow = bin.flows[0]
    const xMin = (flow.bin.column / 6) * 100
    const xMax = ((flow.bin.column + 1) / 6) * 100
    const yMin = (flow.bin.row / 4) * 100
    const yMax = ((flow.bin.row + 1) / 4) * 100
    const topLeft = transform.toScreen({ x: xMin, y: yMin })
    const bottomRight = transform.toScreen({ x: xMax, y: yMax })
    const volume = Math.sqrt(bin.volume / maximumVolume)
    const selected = bin.flows.some(candidate => candidate.id === options.selectedFlowId)
    const hasSelection = Boolean(options.selectedFlowId)

    context.fillStyle = densityColor
    context.globalAlpha = selected ? 0.28 : hasSelection ? 0.035 : 0.035 + volume * 0.12
    context.fillRect(
      topLeft.x + 1,
      topLeft.y + 1,
      Math.max(0, bottomRight.x - topLeft.x - 2),
      Math.max(0, bottomRight.y - topLeft.y - 2),
    )
    if (selected) {
      context.strokeStyle = '#E4EAF8'
      context.globalAlpha = 0.82
      context.lineWidth = 1.5
      context.strokeRect(
        topLeft.x + 1.5,
        topLeft.y + 1.5,
        Math.max(0, bottomRight.x - topLeft.x - 3),
        Math.max(0, bottomRight.y - topLeft.y - 3),
      )
    }
  }

  for (const flow of flows) {
    const volumeCount = flow.attemptedCount ?? flow.completedCount
    if (volumeCount === 0) continue

    const color = flow.color ?? options.flowColor ?? defaultLayerOptions.flowColor
    const selected = flow.id === options.selectedFlowId
    const hasSelection = Boolean(options.selectedFlowId)
    const laneOffset = (flow.comparisonLane ?? 0) * (transform.bounds.height / 4) * 0.2
    const origin = transform.toScreen(flow.origin)
    const binTop = transform.toScreen({ x: 0, y: (flow.bin.row / 4) * 100 }).y
    const binBottom = transform.toScreen({ x: 0, y: ((flow.bin.row + 1) / 4) * 100 }).y
    const start = {
      x: origin.x,
      y: Math.min(binBottom - 5, Math.max(binTop + 5, origin.y + laneOffset)),
    }
    const destination = transform.toScreen(flow.destination)
    const rawDeltaX = destination.x - origin.x
    const rawDeltaY = destination.y - origin.y
    const rawDistance = Math.hypot(rawDeltaX, rawDeltaY)
    if (rawDistance < 1) continue
    const maximumArrowLength = Math.min(transform.bounds.width / 6, transform.bounds.height / 3.2)
    const arrowDistance = Math.min(rawDistance, maximumArrowLength * (0.6 + Math.min(1, flow.meanLength / 35) * 0.65))
    const unitX = rawDeltaX / rawDistance
    const unitY = rawDeltaY / rawDistance
    const end = { x: start.x + unitX * arrowDistance, y: start.y + unitY * arrowDistance }
    const fromX = start.x
    const fromY = start.y
    const toX = end.x
    const toY = end.y

    const arrowSize = 5
    const shaftEndX = toX - unitX * arrowSize * 0.82
    const shaftEndY = toY - unitY * arrowSize * 0.82
    context.beginPath()
    context.moveTo(fromX, fromY)
    context.lineTo(shaftEndX, shaftEndY)
    context.strokeStyle = color
    context.globalAlpha = selected ? 1 : hasSelection ? 0.2 : 0.94
    context.lineWidth = selected ? 3.25 : flow.gameState ? 1.8 : 2.25
    context.stroke()

    context.beginPath()
    context.moveTo(toX, toY)
    context.lineTo(toX - unitX * arrowSize - unitY * arrowSize * 0.72, toY - unitY * arrowSize + unitX * arrowSize * 0.72)
    context.lineTo(toX - unitX * arrowSize + unitY * arrowSize * 0.72, toY - unitY * arrowSize - unitX * arrowSize * 0.72)
    context.closePath()
    context.fillStyle = color
    context.fill()
  }

  context.restore()
}

export function drawDensePitchLayers(
  context: CanvasRenderingContext2D,
  viewport: Pick<CanvasViewport, 'width' | 'height'>,
  layers: {
    passes?: EventPass[]
    carries?: EventCarry[]
    densityCells?: ActionGridCell[]
    flows?: TeamPassFlow[]
  },
  options: DenseLayerOptions = {},
  pitchView: 'full' | 'attacking-half' = 'full',
) {
  context.clearRect(0, 0, viewport.width, viewport.height)
  const transform = createPitchTransform(
    pitchView === 'attacking-half' ? viewport.width * 2 : viewport.width,
    viewport.height,
  )
  context.save()
  if (pitchView === 'attacking-half') context.translate(-viewport.width, 0)
  if (layers.densityCells?.length) {
    drawDensityLayer(context, layers.densityCells, transform, options.densityColor, options.densityStyle, options.densityDomainMax)
  }
  if (layers.flows?.length) {
    drawFlowLayer(context, layers.flows, transform, options)
  }
  if (layers.passes?.length) {
    drawPassLayer(context, layers.passes, transform, options)
  }
  if (layers.carries?.length) {
    drawCarryLayer(context, layers.carries, transform, options)
  }
  context.restore()
}
