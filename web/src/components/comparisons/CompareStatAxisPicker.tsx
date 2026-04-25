import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, X } from 'lucide-react'
import { HudCornerMarks } from '../hud/Hud'
import type { PositionGroup, StatMeta } from '../../types/api'
import {
  COMPARISON_STAT_MAX,
  COMPARISON_STAT_MIN,
} from '../../lib/comparisonConstants'
import { groupMetricsForPizzaPicker, stripPer90Suffix } from '../../lib/profileMetrics'
import { cn } from '../../lib/utils'

interface CompareStatAxisPickerProps {
  meta: StatMeta
  positionGroup: PositionGroup
  selectedKeys: string[]
  onChangeKeys: (keys: string[]) => void
}

export function CompareStatAxisPicker({
  meta,
  positionGroup,
  selectedKeys,
  onChangeKeys,
}: CompareStatAxisPickerProps) {
  const sectionOrder = useMemo(() => Object.keys(meta.metric_groups), [meta.metric_groups])

  function removeKey(k: string) {
    if (selectedKeys.length <= COMPARISON_STAT_MIN) return
    onChangeKeys(selectedKeys.filter(x => x !== k))
  }

  function addKey(k: string) {
    if (selectedKeys.includes(k)) return
    if (selectedKeys.length >= COMPARISON_STAT_MAX) return
    onChangeKeys([...selectedKeys, k])
  }

  const canRemove = selectedKeys.length > COMPARISON_STAT_MIN
  const canAdd = selectedKeys.length < COMPARISON_STAT_MAX

  return (
    <div className="w-full max-w-sm flex flex-col gap-3">
      <p className="text-[10px] uppercase tracking-[0.2em] text-electric/80">Active axes</p>
      <div className="flex flex-wrap gap-1.5">
        {selectedKeys.map(k => {
          const label = stripPer90Suffix(meta.metrics[k]?.label ?? k)
          return (
            <button
              key={k}
              type="button"
              disabled={!canRemove}
              onClick={() => removeKey(k)}
              className={cn(
                'relative flex items-center gap-1 pl-2 pr-1 py-1 text-[10px] uppercase tracking-wide border',
                canRemove
                  ? 'border-electric/35 bg-electric/5 text-ink-dim hover:text-ink hover:border-electric/60'
                  : 'border-line opacity-50 cursor-not-allowed',
              )}
            >
              {canRemove && <HudCornerMarks size="size-1" />}
              <span className="truncate max-w-[140px]">{label}</span>
              <X size={11} className="opacity-60 shrink-0" />
            </button>
          )
        })}
      </div>

      <CompareStatAddDropdown
        meta={meta}
        sectionOrder={sectionOrder}
        excludeMetricKeys={positionGroup === 'GK' ? ['rating'] : undefined}
        selectedKeys={selectedKeys}
        onAdd={addKey}
        disabled={!canAdd}
      />

      <p className="text-[10px] text-ink-muted leading-relaxed">
        Minimum {COMPARISON_STAT_MIN} stats, up to {COMPARISON_STAT_MAX}. With no{' '}
        <span className="font-mono text-electric/70">stats</span> in the URL, defaults match polar profile presets.
      </p>
    </div>
  )
}

function CompareStatAddDropdown({
  meta,
  sectionOrder,
  excludeMetricKeys,
  selectedKeys,
  onAdd,
  disabled,
}: {
  meta: StatMeta
  sectionOrder: string[]
  excludeMetricKeys?: readonly string[]
  selectedKeys: string[]
  onAdd: (k: string) => void
  disabled: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function close(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const grouped = useMemo(
    () =>
      groupMetricsForPizzaPicker(
        meta,
        excludeMetricKeys?.length ? [...excludeMetricKeys] : undefined,
      ),
    [meta, excludeMetricKeys],
  )

  const available = useMemo(() => {
    const sel = new Set(selectedKeys)
    return sectionOrder.flatMap(sec =>
      (grouped[sec] ?? [])
        .filter(({ key }) => !sel.has(key))
        .map(item => ({ ...item, section: sec })),
    )
  }, [grouped, sectionOrder, selectedKeys])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(o => !o)}
        className={cn(
          'relative w-full flex items-center justify-between gap-2 px-3 py-2 border text-[11px] uppercase tracking-[0.15em]',
          disabled
            ? 'border-line text-ink-muted opacity-50 cursor-not-allowed'
            : 'border-electric/25 text-electric/90 hover:bg-electric/5',
        )}
      >
        <span>Add stat</span>
        <ChevronDown size={14} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && !disabled && (
        <div className="absolute left-0 right-0 top-full mt-1 z-50 max-h-64 overflow-y-auto border border-electric/25 bg-panel/98 shadow-xl">
          {available.length === 0 ? (
            <p className="p-3 text-[11px] text-ink-muted">All metrics selected.</p>
          ) : (
            sectionOrder.map(sec => {
              const items = available.filter(a => a.section === sec)
              if (!items.length) return null
              return (
                <div key={sec} className="border-b border-electric/10 last:border-0">
                  <p className="px-2 py-1.5 text-[9px] uppercase tracking-widest text-ink-muted bg-mat/80 sticky top-0">
                    {meta.metric_groups[sec] ?? sec}
                  </p>
                  {items.map(({ key, label }) => (
                    <button
                      key={key}
                      type="button"
                      className="w-full text-left px-3 py-1.5 text-[12px] text-ink-dim hover:bg-electric/10 hover:text-ink"
                      onClick={() => {
                        onAdd(key)
                        setOpen(false)
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              )
            })
          )}
        </div>
      )}
    </div>
  )
}
