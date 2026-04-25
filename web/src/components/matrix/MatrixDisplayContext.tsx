import { createContext, useContext } from 'react'
import type { MatrixRateMode } from '../../lib/matrixRateMode'
import type { MinutesHeatRange } from '../../lib/heatmap'

export type MatrixVariant = 'outfield' | 'gk'

export interface MatrixDisplayContextValue {
  heatmapEnabled: boolean
  minutesRange: MinutesHeatRange | null
  rateMode: MatrixRateMode
  matrixVariant: MatrixVariant
}

export const MatrixDisplayContext = createContext<MatrixDisplayContextValue | null>(null)

export function useMatrixDisplay(): MatrixDisplayContextValue {
  const v = useContext(MatrixDisplayContext)
  if (!v) throw new Error('useMatrixDisplay must be used inside MatrixDisplayContext.Provider')
  return v
}
