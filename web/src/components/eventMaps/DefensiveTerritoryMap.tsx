import { useState } from 'react'
import type {
  ActionGridCell,
  DefensiveActionFamily,
  DefensiveTerritoryEvidence,
  TeamDefensiveTerritoryPayload,
} from '../../types/eventMaps'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import { PortraitPitch } from './PortraitPitch'
import {
  EventMapCard,
  EventMapNotice,
  EventPitchStage,
} from './EventMapUi'

const ACTION_FAMILIES: Array<{ value: DefensiveActionFamily; label: string }> = [
  { value: 'recovery', label: 'Recoveries' },
  { value: 'tackle', label: 'Tackles' },
  { value: 'interception', label: 'Interceptions' },
  { value: 'blocked_pass', label: 'Blocked passes' },
  { value: 'defensive_aerial', label: 'Defensive aerials' },
  { value: 'defensive_challenge', label: 'Defensive challenges' },
  { value: 'clearance', label: 'Clearances' },
]
const ALL_FAMILIES = ACTION_FAMILIES.map(option => option.value)
const ACTION_FAMILY_LABELS = new Map(
  ACTION_FAMILIES.map(({ value, label }) => [value, label]),
)

function pitchHeight(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function rate(value: number | null) {
  return value == null ? '—' : value.toFixed(2)
}

function combineGrid(evidence: DefensiveTerritoryEvidence, selected: DefensiveActionFamily[]) {
  const composition = new Map(evidence.familyComposition.map(row => [row.family, row]))
  const total = selected.reduce((sum, family) => (
    sum + (composition.get(family)?.withLocation ?? 0)
  ), 0)
  return evidence.gridsByFamily[selected[0]].map((cell, index): ActionGridCell => {
    const values = selected.map(family => evidence.gridsByFamily[family][index])
    const rawCount = values.reduce((sum, value) => sum + value.rawCount, 0)
    return {
      column: cell.column,
      row: cell.row,
      rawCount,
      per90Count: values.reduce((sum, value) => sum + value.per90Count, 0),
      share: total ? rawCount / total : 0,
    }
  })
}

function combinedSummary(evidence: DefensiveTerritoryEvidence, selected: DefensiveActionFamily[]) {
  const composition = new Map(evidence.familyComposition.map(row => [row.family, row]))
  let located = 0
  let unlocated = 0
  let rate = 0
  let heightWeight = 0
  let weightedHeight = 0
  selected.forEach(family => {
    const familyComposition = composition.get(family)
    if (!familyComposition) return
    const familyEvidence = evidence.familyEvidence[family]
    located += familyComposition.withLocation
    unlocated += familyComposition.withoutLocation
    rate += familyEvidence.ratePerStateMinute ?? 0
    if (familyEvidence.height.mean != null) {
      heightWeight += familyEvidence.height.sampleSize
      weightedHeight += familyEvidence.height.mean * familyEvidence.height.sampleSize
    }
  })
  return {
    located,
    unlocated,
    rate: evidence.counts.included ? rate : null,
    meanHeight: heightWeight ? weightedHeight / heightWeight : null,
  }
}

function DefensiveActionSelect({ selected, onChange }: {
  selected: DefensiveActionFamily[]
  onChange: (selected: DefensiveActionFamily[]) => void
}) {
  const allSelected = selected.length === ACTION_FAMILIES.length
  const label = allSelected
    ? 'All defensive actions'
    : selected.length === 1
      ? ACTION_FAMILY_LABELS.get(selected[0]) ?? selected[0]
      : `${selected.length} action types`
  const toggle = (family: DefensiveActionFamily) => {
    if (selected.includes(family)) {
      if (selected.length > 1) onChange(selected.filter(value => value !== family))
    } else {
      onChange(ALL_FAMILIES.filter(value => selected.includes(value) || value === family))
    }
  }
  return (
    <details className="relative">
      <summary className="event-lens-control flex min-w-48 list-none items-center justify-between gap-3 whitespace-nowrap text-left marker:hidden">
        <span>{label}</span><span aria-hidden className="text-electric">▾</span>
      </summary>
      <div className="absolute right-0 z-30 mt-1 min-w-60 border border-control-border bg-overlay p-2 shadow-2xl">
        <label className="flex min-h-9 items-center gap-2 border-b border-line-bright px-2 text-[10px] font-bold text-ink">
          <input type="checkbox" checked={allSelected} onChange={() => onChange(ALL_FAMILIES)} />
          All defensive actions
        </label>
        {ACTION_FAMILIES.map(option => (
          <label key={option.value} className="flex min-h-9 items-center gap-2 px-2 text-[10px] text-control-fg hover:bg-raised hover:text-ink">
            <input type="checkbox" checked={selected.includes(option.value)} onChange={() => toggle(option.value)} />
            {option.label}
          </label>
        ))}
      </div>
    </details>
  )
}

export function DefensiveTerritoryMap({
  payload,
  loading,
  error,
  retry,
  exportContext,
  expanded,
  onExpandedChange,
}: {
  payload?: TeamDefensiveTerritoryPayload
  loading: boolean
  error?: string
  retry: () => void
  exportContext: EventMapExportContext
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
}) {
  const [selectedFamilies, setSelectedFamilies] = useState<DefensiveActionFamily[]>(ALL_FAMILIES)
  if (loading) return <EventMapNotice kind="loading" title="Loading defensive territory" />
  if (error || !payload) {
    return <EventMapNotice kind="error" title="Defensive territory failed to load" onRetry={retry}>{error}</EventMapNotice>
  }
  const evidence = payload.selected
  const selectedFamilySet = new Set(selectedFamilies)
  const selectedGrid = combineGrid(evidence, selectedFamilies)
  const selectedSummary = combinedSummary(evidence, selectedFamilies)
  const baselineSummary = payload.baseline
    ? combinedSummary(payload.baseline, selectedFamilies)
    : null

  return (
    <EventMapCard
      title="Defensive action territory"
      description="Choose the action types to map. Positions run from the team's own goal (0) to the opponent's goal (100)."
      controls={<DefensiveActionSelect selected={selectedFamilies} onChange={setSelectedFamilies} />}
      exportContext={{
        ...exportContext,
        filters: [...exportContext.filters, {
          label: 'Defensive actions',
          value: selectedFamilies.length === ACTION_FAMILIES.length
            ? 'All action types'
            : selectedFamilies.map(family => ACTION_FAMILY_LABELS.get(family) ?? family).join(' · '),
        }],
      }}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        <div className="grid w-full max-w-[1120px] items-start gap-4 lg:grid-cols-[minmax(0,760px)_minmax(280px,1fr)]">
          <div>
            {selectedSummary.located ? (
              <PortraitPitch
                densityCells={selectedGrid}
                densityStyle="cells"
                ariaLabel={`${payload.teamName} selected defensive action territory. Own goal at zero, opponent goal at one hundred.`}
              />
            ) : <EventMapNotice kind="empty" title="No located defensive actions in this state" />}
          </div>
          <aside className="space-y-3 border-t border-line-bright pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0" aria-label="Defensive territory evidence">
            <div className="grid grid-cols-2 gap-3 text-[12px] leading-relaxed lg:grid-cols-1">
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Average action position</span>{pitchHeight(selectedSummary.meanHeight)}</p>
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Actions per minute</span>{rate(selectedSummary.rate)}</p>
              <p className="col-span-2 text-[11px] text-ink-dim lg:col-span-1">Average distance from the team's own goal for the selected actions.</p>
            </div>
            <p className="text-[11px] leading-relaxed text-ink-dim">Brighter blue cells mean more actions · {selectedSummary.located} located · {selectedSummary.unlocated} unlocated.</p>
            {selectedSummary.located < evidence.evidence.sparseThreshold ? (
              <EventMapNotice kind="sparse" title="Sparse location sample">
                {selectedSummary.located} located actions; interpret the territory pattern cautiously below {evidence.evidence.sparseThreshold}.
              </EventMapNotice>
            ) : null}
            {baselineSummary ? (
              <p className="text-[11px] leading-relaxed text-ink-dim">
                Baseline average position {pitchHeight(baselineSummary.meanHeight)} · comparison average {pitchHeight(selectedSummary.meanHeight)}. Both scopes use identical 12×8 bins for State Delta Map comparison.
              </p>
            ) : null}
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] uppercase tracking-[0.08em] text-ink-dim" aria-label="Defensive event family composition">
              {evidence.familyComposition.flatMap(row => (
                selectedFamilySet.has(row.family) && row.count > 0
                  ? [<span key={row.family}>{ACTION_FAMILY_LABELS.get(row.family) ?? row.family} {row.count}</span>]
                  : []
              ))}
            </div>
            <p className="text-[11px] leading-relaxed text-gold">{evidence.disclaimer}</p>
          </aside>
        </div>
      </EventPitchStage>
    </EventMapCard>
  )
}
