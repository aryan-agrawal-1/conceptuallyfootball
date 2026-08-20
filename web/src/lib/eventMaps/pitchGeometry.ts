import type { PitchCoordinate } from '../../types/eventMaps'

export const PITCH_VIEWBOX_WIDTH = 1050
export const PITCH_VIEWBOX_HEIGHT = 680
export const PITCH_ASPECT_RATIO = PITCH_VIEWBOX_WIDTH / PITCH_VIEWBOX_HEIGHT
export const PITCH_LENGTH_METRES = 105
export const PITCH_WIDTH_METRES = 68

export type ScreenCoordinate = {
  x: number
  y: number
}

export type PitchBounds = {
  left: number
  top: number
  width: number
  height: number
  right: number
  bottom: number
}

export type PitchTransform = {
  bounds: PitchBounds
  toScreen: (coordinate: PitchCoordinate) => ScreenCoordinate
  toPitch: (coordinate: ScreenCoordinate) => PitchCoordinate
}

function clampCoordinate(value: number) {
  return Math.min(100, Math.max(0, value))
}

export function fitPortraitPitch(
  viewportWidth: number,
  viewportHeight: number,
  inset = 0,
): PitchBounds {
  const safeWidth = Math.max(0, viewportWidth - inset * 2)
  const safeHeight = Math.max(0, viewportHeight - inset * 2)
  const scale = Math.min(safeWidth / PITCH_VIEWBOX_WIDTH, safeHeight / PITCH_VIEWBOX_HEIGHT)
  const width = PITCH_VIEWBOX_WIDTH * scale
  const height = PITCH_VIEWBOX_HEIGHT * scale
  const left = (viewportWidth - width) / 2
  const top = (viewportHeight - height) / 2

  return {
    left,
    top,
    width,
    height,
    right: left + width,
    bottom: top + height,
  }
}

export function createPitchTransform(
  viewportWidth: number,
  viewportHeight: number,
  inset = 0,
): PitchTransform {
  const bounds = fitPortraitPitch(viewportWidth, viewportHeight, inset)

  return {
    bounds,
    toScreen(coordinate) {
      const sourceX = clampCoordinate(coordinate.x)
      const sourceY = clampCoordinate(coordinate.y)

      return {
        x: bounds.left + (sourceX / 100) * bounds.width,
        y: bounds.top + (sourceY / 100) * bounds.height,
      }
    },
    toPitch(coordinate) {
      if (bounds.width === 0 || bounds.height === 0) return { x: 0, y: 0 }

      return {
        x: clampCoordinate(((coordinate.x - bounds.left) / bounds.width) * 100),
        y: clampCoordinate(((coordinate.y - bounds.top) / bounds.height) * 100),
      }
    },
  }
}

export function actionGridCellBounds(
  column: number,
  row: number,
  columnCount = 12,
  rowCount = 8,
) {
  const safeColumnCount = Math.max(1, columnCount)
  const safeRowCount = Math.max(1, rowCount)
  const safeColumn = Math.min(safeColumnCount - 1, Math.max(0, column))
  const safeRow = Math.min(safeRowCount - 1, Math.max(0, row))

  return {
    xMin: (safeColumn / safeColumnCount) * 100,
    xMax: ((safeColumn + 1) / safeColumnCount) * 100,
    yMin: (safeRow / safeRowCount) * 100,
    yMax: ((safeRow + 1) / safeRowCount) * 100,
  }
}

export function clientPointToViewport(
  clientX: number,
  clientY: number,
  bounds: Pick<DOMRect, 'left' | 'top' | 'width' | 'height'>,
  viewportWidth = PITCH_VIEWBOX_WIDTH,
  viewportHeight = PITCH_VIEWBOX_HEIGHT,
): ScreenCoordinate {
  if (bounds.width === 0 || bounds.height === 0) return { x: 0, y: 0 }

  return {
    x: ((clientX - bounds.left) / bounds.width) * viewportWidth,
    y: ((clientY - bounds.top) / bounds.height) * viewportHeight,
  }
}
