export const STATE_PRESENTATION = {
  losing: { label: 'Losing', color: '#EF5C66', shape: 'square' },
  drawing: { label: 'Drawing', color: '#4A9EF5', shape: 'diamond' },
  winning: { label: 'Winning', color: '#1FD17C', shape: 'circle' },
  all: { label: 'All states', color: '#8A95B8', shape: 'diamond' },
} as const

export type PresentedState = keyof typeof STATE_PRESENTATION

export function statePresentation(state: string | null | undefined) {
  return STATE_PRESENTATION[state as PresentedState] ?? STATE_PRESENTATION.all
}
