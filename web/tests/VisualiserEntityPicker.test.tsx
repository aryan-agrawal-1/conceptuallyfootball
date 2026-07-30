// @vitest-environment jsdom

import React from 'react'
import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { VisualiserEntityPicker } from '../src/components/visualizer/VisualiserEntityPicker'

afterEach(cleanup)

describe('VisualiserEntityPicker pin management', () => {
  it('groups pins first without losing option relevance order and clears them in bulk', () => {
    const onChange = vi.fn()
    const view = render(
      <VisualiserEntityPicker
        open
        title="Highlight players"
        options={[
          { id: 2, label: 'Second-ranked pin' },
          { id: 1, label: 'Top available' },
          { id: 3, label: 'Third-ranked pin' },
          { id: 4, label: 'Fourth available' },
        ]}
        selectedIds={[2, 3]}
        onChange={onChange}
        onClose={() => undefined}
        groupSelected
        selectedSectionLabel="Pinned"
        clearAllLabel="Unpin all"
      />,
    )

    const labels = [...view.container.querySelectorAll('li button')]
      .map(button => button.textContent?.trim())
    expect(labels).toEqual([
      'Second-ranked pin',
      'Third-ranked pin',
      'Top available',
      'Fourth available',
    ])

    fireEvent.change(view.getByPlaceholderText('Search…'), {
      target: { value: 'fourth' },
    })
    expect(
      [...view.container.querySelectorAll('li button')].map(button => button.textContent?.trim()),
    ).toEqual(['Fourth available'])

    fireEvent.click(view.getByRole('button', { name: 'Unpin all' }))
    expect(onChange).toHaveBeenCalledWith([])
  })
})
