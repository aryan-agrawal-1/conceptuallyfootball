import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, Search, X } from 'lucide-react'
import { cn } from '../../lib/utils'
import { HudCornerMarks, HudPopover } from './Hud'

export type HudDropdownOption = {
  value: string
  label: string
}

export type HudDropdownGroup = {
  key: string
  label: string
  options: HudDropdownOption[]
}

function useOutsideClose<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T>(null)

  useEffect(() => {
    if (!open) return
    function close(event: MouseEvent) {
      if (ref.current && !ref.current.contains(event.target as Node)) onClose()
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open, onClose])

  return ref
}

export function HudSelectDropdown({
  label,
  value,
  groups,
  onChange,
  disabled = false,
  className,
  align = 'start',
}: {
  label: string
  value: string | undefined
  groups: HudDropdownGroup[]
  onChange: (value: string) => void
  disabled?: boolean
  className?: string
  align?: 'start' | 'end'
}) {
  const [open, setOpen] = useState(false)
  const ref = useOutsideClose<HTMLDivElement>(open, () => setOpen(false))
  const selected = groups.flatMap(group => group.options).find(option => option.value === value)

  return (
    <div ref={ref} className={cn('relative min-w-0', className)}>
      <button
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => setOpen(current => !current)}
        className={cn(
          'relative flex w-full min-w-0 items-center justify-between gap-2 border px-3 py-2 text-left text-[11px] font-medium uppercase tracking-[0.15em] transition-colors',
          open
            ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
            : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
          disabled && 'pointer-events-none opacity-50',
        )}
      >
        {open && <HudCornerMarks size="size-1" />}
        <span className="truncate">{selected?.label ?? label}</span>
        <ChevronDown size={11} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <HudPopover align={align} className="max-h-72 w-full min-w-[min(15rem,calc(100vw-1.5rem))] overflow-y-auto p-1">
          <div role="listbox" aria-label={label} className="flex flex-col gap-1">
            {groups.map(group => (
              <div key={group.key} className="border-b border-electric/10 pb-1 last:border-b-0 last:pb-0">
                {groups.length > 1 && (
                  <p className="px-2 py-1 text-[9px] uppercase tracking-[0.22em] text-ink-muted">
                    {group.label}
                  </p>
                )}
                {group.options.map(option => {
                  const active = option.value === value
                  return (
                    <button
                      key={option.value}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => {
                        onChange(option.value)
                        setOpen(false)
                      }}
                      className={cn(
                        'flex w-full items-center justify-between gap-2 border px-2.5 py-1.5 text-left text-[12px] transition-colors',
                        active
                          ? 'border-electric/40 bg-electric/10 text-electric'
                          : 'border-transparent text-ink-dim hover:bg-electric/5 hover:text-ink',
                      )}
                    >
                      <span className="truncate">{option.label}</span>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        </HudPopover>
      )}
    </div>
  )
}

export function HudMultiSelectDropdown({
  label,
  options,
  selected,
  onChange,
  emptyLabel = 'All',
  searchPlaceholder,
  maxSelected,
  className,
  align = 'start',
}: {
  label: string
  options: HudDropdownOption[]
  selected: string[]
  onChange: (selected: string[]) => void
  emptyLabel?: string
  searchPlaceholder?: string
  maxSelected?: number
  className?: string
  align?: 'start' | 'end'
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const ref = useOutsideClose<HTMLDivElement>(open, () => setOpen(false))
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (!needle) return options
    return options.filter(option => option.label.toLowerCase().includes(needle))
  }, [options, search])
  const displayLabel =
    selected.length === 0
      ? emptyLabel
      : selected.length === 1
        ? options.find(option => option.value === selected[0])?.label ?? selected[0]
        : `${selected.length} ${label}`

  function toggle(value: string) {
    if (selected.includes(value)) {
      onChange(selected.filter(entry => entry !== value))
      return
    }
    if (maxSelected != null && selected.length >= maxSelected) return
    onChange([...selected, value])
  }

  return (
    <div ref={ref} className={cn('relative min-w-0', className)}>
      <button
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(current => !current)}
        className={cn(
          'relative flex w-full min-w-0 items-center justify-between gap-1.5 border px-3 py-2 text-[11px] font-medium uppercase tracking-[0.15em] transition-colors',
          selected.length || open
            ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
            : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
        )}
      >
        {(selected.length > 0 || open) && <HudCornerMarks size="size-1" />}
        <span className="truncate">{displayLabel}</span>
        {selected.length > 0 ? (
          <X
            size={11}
            className="shrink-0 opacity-70"
            onClick={event => {
              event.stopPropagation()
              onChange([])
            }}
          />
        ) : (
          <ChevronDown size={11} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
        )}
      </button>
      {open && (
        <HudPopover align={align} className="w-[min(15rem,calc(100vw-1.5rem))]">
          {searchPlaceholder && (
            <div className="border-b border-electric/20 p-2">
              <div className="flex items-center gap-2 border border-electric/20 bg-mat/60 px-2 py-1.5">
                <Search size={12} className="shrink-0 text-electric/60" />
                <input
                  autoFocus
                  value={search}
                  onChange={event => setSearch(event.target.value)}
                  placeholder={searchPlaceholder}
                  className="min-w-0 flex-1 bg-transparent text-[16px] tracking-wide text-ink outline-none placeholder:text-electric/30 lg:text-[11px]"
                />
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch('')}
                    className="text-electric/50 hover:text-electric"
                  >
                    <X size={10} />
                  </button>
                )}
              </div>
            </div>
          )}
          <div className="max-h-56 overflow-y-auto p-1">
            {selected.length > 0 && (
              <button
                type="button"
                className="mb-0.5 w-full px-3 py-1.5 text-left text-[10px] uppercase tracking-[0.2em] text-electric/70 transition-colors hover:bg-electric/10 hover:text-electric"
                onClick={() => onChange([])}
              >
                Clear selection
              </button>
            )}
            {filtered.map(option => {
              const on = selected.includes(option.value)
              const disabled = !on && maxSelected != null && selected.length >= maxSelected
              return (
                <button
                  key={option.value}
                  type="button"
                  disabled={disabled}
                  onClick={() => toggle(option.value)}
                  className={cn(
                    'flex w-full items-center gap-2.5 px-3 py-1.5 text-left text-[12px] transition-colors',
                    on ? 'bg-electric/10 text-electric' : 'text-ink-dim hover:bg-electric/5 hover:text-ink',
                    disabled && 'cursor-not-allowed opacity-40',
                  )}
                >
                  <span
                    className={cn(
                      'flex h-3.5 w-3.5 shrink-0 items-center justify-center border transition-colors',
                      on ? 'border-electric bg-electric/30' : 'border-electric/30',
                    )}
                  >
                    {on && (
                      <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                        <path
                          d="M1 3L3 5L7 1"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="text-electric"
                        />
                      </svg>
                    )}
                  </span>
                  <span className="truncate">{option.label}</span>
                </button>
              )
            })}
            {filtered.length === 0 && (
              <p className="px-3 py-3 text-center text-[11px] uppercase tracking-[0.2em] text-electric/40">
                No results
              </p>
            )}
          </div>
        </HudPopover>
      )}
    </div>
  )
}
