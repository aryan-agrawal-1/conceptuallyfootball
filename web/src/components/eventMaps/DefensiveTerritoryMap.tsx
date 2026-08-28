import { useState } from 'react'
import type {
  ActionGridCell,
  DefensiveActionFamily,
  DefensiveTerritoryEvidence,
  TeamDefensiveTerritoryPayload,
} from '../../types/eventMaps'
import type { EventMapExportContext } from '../../lib/eventMaps/exportContext'
import { buildDeltaCell, buildDeltaGrid, type StateDeltaMapContract } from '../../lib/eventMaps/deltaMap'
import { PortraitPitch } from './PortraitPitch'
import {
  EventMapCard,
  EventMapNotice,
  EventPitchStage,
} from './EventMapUi'
import { StateDeltaMap } from './StateDeltaMap'
import {
  ALL_DEFENSIVE_ACTION_FAMILIES,
  defensiveActionFamilyLabel,
} from './defensiveActionFamilies'
import { DefensiveActionSelector } from './DefensiveActionSelector'
import { PairedStatePitch } from './PairedStatePitch'
import { statePresentation } from '../../lib/eventMaps/statePresentation'

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
    included: located + unlocated,
    located,
    unlocated,
    rate: evidence.counts.included ? rate : null,
    meanHeight: heightWeight ? weightedHeight / heightWeight : null,
    medianHeight: selected.length === 1
      ? composition.get(selected[0])
        ? evidence.familyEvidence[selected[0]].height.median
        : null
      : selected.length === ALL_DEFENSIVE_ACTION_FAMILIES.length
        ? evidence.heights.all.median
        : null,
  }
}

function defensiveReliability(
  evidence: DefensiveTerritoryEvidence,
  lensEvidence: TeamDefensiveTerritoryPayload['stateLens']['evidence'] | null | undefined,
) {
  if (lensEvidence?.empty || !lensEvidence?.exposureMinutes) return 'unavailable' as const
  if (evidence.evidence.sparse) return 'sparse' as const
  if (lensEvidence.matchesExcluded) return 'partial' as const
  return 'verified' as const
}

function stateLabel(value: string | undefined) {
  if (!value || value === 'all') return 'All states'
  return value.replaceAll('_', ' ').replace(/^./, character => character.toUpperCase())
}

function scopeLabel(scope: TeamDefensiveTerritoryPayload['stateLens']['selected'] | null | undefined) {
  if (!scope) return 'All states'
  const qualifiers = [
    scope.goalDifference == null ? null : `GD ${scope.goalDifference > 0 ? '+' : ''}${scope.goalDifference}`,
    scope.phase?.replaceAll('_', ' '),
    scope.drawProvenance && scope.drawProvenance !== 'none' ? scope.drawProvenance : null,
  ].filter(Boolean)
  const label = stateLabel(scope.state)
  return qualifiers.length ? `${label} · ${qualifiers.join(' · ')}` : label
}

function defensiveDeltaContract(
  payload: TeamDefensiveTerritoryPayload,
  selectedGrid: ActionGridCell[],
  baselineGrid: ActionGridCell[],
  selectedFamilies: DefensiveActionFamily[],
): StateDeltaMapContract {
  const selectedByCoordinate = new Map(selectedGrid.map(cell => [`${cell.column}:${cell.row}`, cell]))
  const baselineByCoordinate = new Map(baselineGrid.map(cell => [`${cell.column}:${cell.row}`, cell]))
  const selectedLensEvidence = payload.stateLens.evidence
  const baselineLensEvidence = payload.stateLens.comparison.baselineEvidence
  const cells = []
  const rates: number[] = []
  for (let row = 0; row < 8; row += 1) {
    for (let column = 0; column < 12; column += 1) {
      const selectedCell = selectedByCoordinate.get(`${column}:${row}`)
      const baselineCell = baselineByCoordinate.get(`${column}:${row}`)
      const selectedValue = selectedCell?.per90Count ?? (selectedLensEvidence.exposureMinutes > 0 ? 0 : null)
      const baselineValue = baselineCell?.per90Count ?? (baselineLensEvidence && baselineLensEvidence.exposureMinutes > 0 ? 0 : null)
      if (selectedValue != null) rates.push(selectedValue)
      if (baselineValue != null) rates.push(baselineValue)
      cells.push(buildDeltaCell({
        column,
        row,
        selectedValue,
        baselineValue,
        selectedRawCount: selectedCell?.rawCount ?? 0,
        baselineRawCount: baselineCell?.rawCount ?? 0,
        selectedSupported: selectedValue != null,
        baselineSupported: baselineValue != null,
        selectedSparse: payload.selected.evidence.sparse,
        baselineSparse: payload.baseline?.evidence.sparse ?? false,
      }))
    }
  }
  const selectedSummary = combinedSummary(payload.selected, selectedFamilies)
  const baselineSummary = payload.baseline ? combinedSummary(payload.baseline, selectedFamilies) : null
  const selectedHeightSampleSize = selectedFamilies.length === 1
    ? payload.selected.familyEvidence[selectedFamilies[0]].height.sampleSize
    : payload.selected.heights.all.sampleSize
  const baselineHeightSampleSize = payload.baseline && selectedFamilies.length === 1
    ? payload.baseline.familyEvidence[selectedFamilies[0]].height.sampleSize
    : payload.baseline?.heights.all.sampleSize ?? null
  return {
    contractVersion: 'state-delta-map/team-defensive-territory/v1',
    subject: { type: 'team', id: payload.teamId, name: payload.teamName },
    metric: {
      label: 'Defensive territory delta',
      unit: 'actions / state min',
      mode: 'absolute-rate',
      smoothing: 'none',
      description: 'Cell colour compares per-minute defensive-action density. Median-height markers remain separate from the density delta.',
      domain: Math.max(0.01, ...rates),
    },
    selected: {
      label: scopeLabel(payload.stateLens.selected),
      exposureMinutes: selectedLensEvidence.exposureMinutes,
      matchCount: selectedLensEvidence.matchCount,
      episodeCount: selectedLensEvidence.episodeCount,
      eventCount: selectedSummary.included,
      locatedEventCount: selectedSummary.located,
      excludedEventCount: selectedSummary.unlocated,
      excludedMatchCount: selectedLensEvidence.matchesExcluded,
      exclusions: {
        ...selectedLensEvidence.exclusionReasons,
        ...payload.selected.evidence.exclusions,
      },
      reliability: defensiveReliability(payload.selected, selectedLensEvidence),
    },
    baseline: {
      label: scopeLabel(payload.stateLens.comparison.baseline),
      exposureMinutes: baselineLensEvidence?.exposureMinutes ?? null,
      matchCount: baselineLensEvidence?.matchCount ?? null,
      episodeCount: baselineLensEvidence?.episodeCount ?? null,
      eventCount: baselineSummary?.included ?? null,
      locatedEventCount: baselineSummary?.located ?? null,
      excludedEventCount: baselineSummary?.unlocated ?? null,
      excludedMatchCount: baselineLensEvidence?.matchesExcluded ?? null,
      exclusions: {
        ...(baselineLensEvidence?.exclusionReasons ?? {}),
        ...(payload.baseline?.evidence.exclusions ?? {}),
      },
      reliability: payload.baseline
        ? defensiveReliability(payload.baseline, baselineLensEvidence)
        : 'unavailable',
    },
    grid: buildDeltaGrid({ columns: 12, rows: 8, cells }),
    markers: {
      selected: selectedSummary.medianHeight == null ? null : {
        id: 'selected-median-height',
        label: 'Selected median',
        coordinate: { x: selectedSummary.medianHeight, y: 50 },
        sampleSize: selectedHeightSampleSize,
        tone: 'selected',
        description: 'Median defensive-action height from the selected action scope.',
      },
      baseline: baselineSummary?.medianHeight == null ? null : {
        id: 'baseline-median-height',
        label: 'Baseline median',
        coordinate: { x: baselineSummary.medianHeight, y: 50 },
        sampleSize: baselineHeightSampleSize,
        tone: 'baseline',
        description: 'Median defensive-action height from the baseline action scope.',
      },
    },
    notes: [
      'Own goal is 0 and opponent goal is 100. Density uses supplied per-state-minute values; raw event totals are disclosed separately.',
      payload.selected.disclaimer,
    ],
  }
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
  const [selectedFamilies, setSelectedFamilies] = useState<DefensiveActionFamily[]>(ALL_DEFENSIVE_ACTION_FAMILIES)
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
  const deltaContract = payload.baseline
    ? defensiveDeltaContract(payload, selectedGrid, combineGrid(payload.baseline, selectedFamilies), selectedFamilies)
    : null

  return (
    <EventMapCard
      title="Defensive action territory"
      description="Choose the action types to map. Positions run from the team's own goal (0) to the opponent's goal (100)."
      controls={<DefensiveActionSelector selected={selectedFamilies} onChange={setSelectedFamilies} />}
      exportContext={{
        ...exportContext,
        filters: [...exportContext.filters, {
          label: 'Defensive actions',
          value: selectedFamilies.length === ALL_DEFENSIVE_ACTION_FAMILIES.length
            ? 'All action types'
            : selectedFamilies.map(defensiveActionFamilyLabel).join(' · '),
        }],
      }}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        <div className="grid w-full max-w-[1120px] items-start gap-4 lg:grid-cols-[minmax(0,760px)_minmax(280px,1fr)]">
          <div>
            {payload.baseline && baselineSummary ? (
              <PairedStatePitch
                selected={{ state: payload.stateLens.selected.state, label: payload.stateLens.selected.state === 'all' ? 'All states' : payload.stateLens.selected.state, cells: selectedGrid, average: selectedSummary.meanHeight == null ? null : { x: selectedSummary.meanHeight, y: 50, sampleSize: selectedSummary.located }, exposureMinutes: payload.stateLens.evidence.exposureMinutes, matchCount: payload.stateLens.evidence.matchCount }}
                comparison={{ state: payload.stateLens.comparison.baseline?.state ?? 'all', label: payload.stateLens.comparison.baseline?.state ?? 'All states', cells: combineGrid(payload.baseline, selectedFamilies), average: baselineSummary.meanHeight == null ? null : { x: baselineSummary.meanHeight, y: 50, sampleSize: baselineSummary.located }, exposureMinutes: payload.stateLens.comparison.baselineEvidence?.exposureMinutes ?? 0, matchCount: payload.stateLens.comparison.baselineEvidence?.matchCount ?? 0 }}
                unit="share of located defensive actions"
                ariaLabel={`${payload.teamName} paired defensive territory comparison`}
              />
            ) : selectedSummary.located ? (
              <PortraitPitch
                densityCells={selectedGrid}
                densityStyle="cells"
                ariaLabel={`${payload.teamName} selected defensive action territory. Own goal at zero, opponent goal at one hundred.`}
              />
            ) : <EventMapNotice kind="empty" title="No located defensive actions in this state" />}
            {deltaContract ? <details className="mt-3 border border-line-bright px-3 py-2 text-[9px] text-ink-dim"><summary className="cursor-pointer text-control-fg">Change evidence</summary><div className="mt-2"><StateDeltaMap contract={deltaContract} compact /></div></details> : null}
          </div>
          <aside className="space-y-3 border-t border-line-bright pt-3 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0" aria-label="Defensive territory evidence">
            <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">Game-state comparison</p>
            {[
              { label: payload.stateLens.selected.state === 'all' ? 'All states' : payload.stateLens.selected.state, state: payload.stateLens.selected.state, summary: selectedSummary },
              ...(baselineSummary ? [{ label: payload.stateLens.comparison.baseline?.state ?? 'All states', state: payload.stateLens.comparison.baseline?.state ?? 'all', summary: baselineSummary }] : []),
            ].map(item => {
              const presentation = statePresentation(item.state)
              return <section key={`${item.state}-${item.label}`} className="border border-line/60 bg-paper/40 px-3 py-2" style={{ borderTopColor: presentation.color }}>
                <p className="text-[9px] font-bold uppercase tracking-[0.08em]" style={{ color: presentation.color }}>{item.label}</p>
                <dl className="mt-2 space-y-2 text-[10px]">
                  <div className="flex items-baseline justify-between gap-3 border-t border-line-bright pt-2"><dt className="text-ink-dim">Average action position</dt><dd className="font-mono text-ink">{pitchHeight(item.summary.meanHeight)}</dd></div>
                  <div className="flex items-baseline justify-between gap-3 border-t border-line-bright pt-2"><dt className="text-ink-dim">Actions per minute</dt><dd className="font-mono text-ink">{rate(item.summary.rate)}</dd></div>
                  <div className="flex items-baseline justify-between gap-3 border-t border-line-bright pt-2"><dt className="text-ink-dim">Located · unlocated</dt><dd className="font-mono text-ink">{item.summary.located} · {item.summary.unlocated}</dd></div>
                </dl>
              </section>
            })}
            <p className="text-[11px] leading-relaxed text-ink-dim">Average position is measured from the team's own goal. Brighter blue cells mean more actions within that cohort.</p>
            {selectedSummary.located < evidence.evidence.sparseThreshold ? (
              <EventMapNotice kind="sparse" title="Sparse location sample">
                {selectedSummary.located} located actions; interpret the territory pattern cautiously below {evidence.evidence.sparseThreshold}.
              </EventMapNotice>
            ) : null}
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-[10px] uppercase tracking-[0.08em] text-ink-dim" aria-label="Defensive event family composition">
              {evidence.familyComposition.flatMap(row => (
                selectedFamilySet.has(row.family) && row.count > 0
                  ? [<span key={row.family}>{defensiveActionFamilyLabel(row.family)} {row.count}</span>]
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
