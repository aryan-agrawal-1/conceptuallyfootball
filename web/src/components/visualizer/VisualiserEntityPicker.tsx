import { useMemo, useState } from 'react'
import { Check, Loader2 } from 'lucide-react'
import { foldForSearch } from '../../lib/foldAccents'
import { HudFrame } from '../hud/Hud'
import { cn } from '../../lib/utils'

export interface VisualiserEntityOption {
  id: number
  label: string
  sublabel?: string
  meta?: string
}

interface VisualiserEntityPickerProps {
  open: boolean
  title: string
  description?: string
  options: VisualiserEntityOption[]
  selectedIds: number[]
  onChange: (ids: number[]) => void
  onClose: () => void
  maxSelected?: number
  isLoading?: boolean
  isError?: boolean
  emptyLabel?: string
  closeLabel?: string
}

export function VisualiserEntityPicker({
  open,
  title,
  description,
  options,
  selectedIds,
  onChange,
  onClose,
  maxSelected,
  isLoading = false,
  isError = false,
  emptyLabel = 'No matching entities.',
  closeLabel = 'Close',
}: VisualiserEntityPickerProps) {
  const [query, setQuery] = useState('')
  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds])

  const filtered = useMemo(() => {
    const needle = foldForSearch(query.trim())
    if (!needle) return options
    return options.filter(option =>
      foldForSearch(`${option.label} ${option.sublabel ?? ''} ${option.meta ?? ''}`).includes(needle),
    )
  }, [options, query])

  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[96] flex items-start justify-center bg-mat/75 px-4 pt-[min(14vh,112px)] backdrop-blur-[2px]"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onClick={onClose}
    >
      <div className="w-full max-w-lg" onClick={e => e.stopPropagation()}>
        <HudFrame
          className="border-electric/30 shadow-[0_0_48px_-12px_rgba(74,158,245,0.35)]"
          header={<span>{title}</span>}
          footer={
            <div className="flex items-center justify-between gap-3">
              <span>{selectedIds.length} selected</span>
              {maxSelected ? <span>Max {maxSelected}</span> : <span>Click rows to toggle</span>}
            </div>
          }
        >
          <div className="flex flex-col gap-3 p-3">
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Search…"
                className="min-w-0 flex-1 border border-electric/25 bg-transparent px-3 py-2 text-[16px] text-ink outline-none placeholder:text-ink-muted focus:border-electric/50 lg:text-[13px]"
              />
              <button
                type="button"
                onClick={() => {
                  setQuery('')
                  onClose()
                }}
                className="shrink-0 border border-electric/20 px-3 py-2 text-[10px] uppercase tracking-widest text-ink-muted hover:border-electric/40 hover:text-electric/80"
              >
                {closeLabel}
              </button>
            </div>

            {description && <p className="text-[11px] leading-relaxed text-ink-dim">{description}</p>}

            {isLoading && (
              <div className="flex items-center justify-center gap-2 py-10 text-ink-muted">
                <Loader2 className="size-4 animate-spin text-electric" />
                <span className="text-[11px] uppercase tracking-wider">Loading options…</span>
              </div>
            )}

            {isError && !isLoading && (
              <p className="py-8 text-center text-[12px] text-ember">Could not load entities.</p>
            )}

            {!isLoading && !isError && (
              <ul className="max-h-[min(50vh,380px)] overflow-y-auto border border-electric/15 divide-y divide-electric/10">
                {filtered.length === 0 ? (
                  <li className="px-3 py-8 text-center text-[12px] text-ink-muted">{emptyLabel}</li>
                ) : (
                  filtered.map(option => {
                    const on = selectedSet.has(option.id)
                    const limitReached = !on && maxSelected != null && selectedIds.length >= maxSelected
                    return (
                      <li key={option.id}>
                        <button
                          type="button"
                          disabled={limitReached}
                          onClick={() => {
                            onChange(
                              on
                                ? selectedIds.filter(id => id !== option.id)
                                : [...selectedIds, option.id].slice(0, maxSelected ?? Number.MAX_SAFE_INTEGER),
                            )
                          }}
                          className={cn(
                            'flex w-full items-center gap-3 border border-transparent px-3 py-2.5 text-left transition-colors',
                            on
                              ? 'bg-electric/12 text-electric'
                              : 'text-ink hover:border-electric/25 hover:bg-electric/8',
                            limitReached && 'cursor-not-allowed opacity-45',
                          )}
                        >
                          <span
                            className={cn(
                              'flex size-5 shrink-0 items-center justify-center border',
                              on ? 'border-electric bg-electric/15' : 'border-electric/20 text-transparent',
                            )}
                          >
                            <Check className="size-3.5" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="truncate text-[13px] font-medium">{option.label}</div>
                            {(option.sublabel || option.meta) && (
                              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-ink-muted">
                                {option.sublabel && <span className="truncate">{option.sublabel}</span>}
                                {option.meta && <span className="font-mono">{option.meta}</span>}
                              </div>
                            )}
                          </div>
                        </button>
                      </li>
                    )
                  })
                )}
              </ul>
            )}
          </div>
        </HudFrame>
      </div>
    </div>
  )
}
