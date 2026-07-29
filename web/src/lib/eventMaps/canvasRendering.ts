import type { ActionGridCell, EventPass, TeamPassFlow } from '../../types/eventMaps'
import {
  actionGridCellBounds,
  createPitchTransform,
  flowZoneCentre,
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
  flowColor?: string
}

const defaultLayerOptions = {
  successfulColor: '#4A9EF5',
  unsuccessfulColor: '#EF5C66',
  densityColor: '#1FD17C',
  flowColor: '#F0A832',
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
) {
  let maximumShare = 0
  for (const cell of cells) maximumShare = Math.max(maximumShare, cell.share)
  if (maximumShare === 0) return

  context.save()
  context.fillStyle = color

  for (const cell of cells) {
    if (cell.share <= 0) continue
    const bounds = actionGridCellBounds(cell.column, cell.row)
    const topLeft = transform.toScreen({ x: bounds.xMax, y: bounds.yMin })
    const bottomRight = transform.toScreen({ x: bounds.xMin, y: bounds.yMax })
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

  context.save()
  context.lineCap = 'round'

  for (const pass of passes) {
    const start = transform.toScreen(pass.start)
    const end = transform.toScreen(pass.end)
    const selected = pass.id === options.selectedEventId
    context.beginPath()
    context.moveTo(start.x, start.y)
    context.lineTo(end.x, end.y)
    context.strokeStyle =
      pass.outcome === 'successful' ? colors.successfulColor : colors.unsuccessfulColor
    context.globalAlpha = selected ? 1 : hasSelection ? 0.4 : 1
    context.lineWidth = selected ? (pass.keyPass ? 2.1 : 1.65) : pass.keyPass ? 1.35 : 0.95
    context.stroke()

    const endpointRadius = selected ? 2.8 : 1.2
    context.beginPath()
    context.arc(end.x, end.y, endpointRadius, 0, Math.PI * 2)
    context.fillStyle = context.strokeStyle
    context.fill()
  }

  context.restore()
}

export function drawFlowLayer(
  context: CanvasRenderingContext2D,
  flows: TeamPassFlow[],
  transform: PitchTransform,
  color = defaultLayerOptions.flowColor,
) {
  let maximumCount = 0
  for (const flow of flows) maximumCount = Math.max(maximumCount, flow.completedCount)
  if (maximumCount === 0) return

  context.save()
  context.strokeStyle = color
  context.lineCap = 'round'

  for (const flow of flows) {
    if (flow.completedCount === 0) continue
    const start = transform.toScreen(flowZoneCentre(flow.startZone))
    const end = transform.toScreen(flowZoneCentre(flow.endZone))
    const volume = Math.sqrt(flow.completedCount / maximumCount)
    const controlX = (start.x + end.x) / 2 + (end.y - start.y) * 0.045
    const controlY = (start.y + end.y) / 2 - (end.x - start.x) * 0.045

    context.beginPath()
    context.moveTo(start.x, start.y)
    context.quadraticCurveTo(controlX, controlY, end.x, end.y)
    context.globalAlpha = 1
    context.lineWidth = 1.5 + volume * 6
    context.stroke()
  }

  context.restore()
}

export function drawDensePitchLayers(
  context: CanvasRenderingContext2D,
  viewport: Pick<CanvasViewport, 'width' | 'height'>,
  layers: {
    passes?: EventPass[]
    densityCells?: ActionGridCell[]
    flows?: TeamPassFlow[]
  },
  options: DenseLayerOptions = {},
) {
  context.clearRect(0, 0, viewport.width, viewport.height)
  const transform = createPitchTransform(viewport.width, viewport.height)
  if (layers.densityCells?.length) {
    drawDensityLayer(context, layers.densityCells, transform, options.densityColor)
  }
  if (layers.flows?.length) {
    drawFlowLayer(context, layers.flows, transform, options.flowColor)
  }
  if (layers.passes?.length) {
    drawPassLayer(context, layers.passes, transform, options)
  }
}
