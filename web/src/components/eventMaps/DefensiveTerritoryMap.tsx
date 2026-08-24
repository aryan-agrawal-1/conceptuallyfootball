import { useState } from 'react'
import type {
  DefensiveTerritoryGroup,
  TeamDefensiveTerritoryPayload,
} from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventMapCard,
  EventMapNotice,
  EventMapViewTabs,
  EventMetricStrip,
  EventPitchStage,
} from './EventMapUi'

const viewOptions = [
  { value: 'all', label: 'All actions' },
  { value: 'nonClearance', label: 'Without clearances' },
  { value: 'clearance', label: 'Clearances' },
] satisfies Array<{ value: DefensiveTerritoryGroup; label: string }>

function pitchHeight(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}%`
}

function rate(value: number | null) {
  return value == null ? '—' : value.toFixed(2)
}

function familyLabel(value: string) {
  return value.replaceAll('_', ' ')
}

export function DefensiveTerritoryMap({
  payload,
  loading,
  error,
  retry,
  expanded,
  onExpandedChange,
}: {
  payload?: TeamDefensiveTerritoryPayload
  loading: boolean
  error?: string
  retry: () => void
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
}) {
  const [view, setView] = useState<DefensiveTerritoryGroup>('all')
  if (loading) return <EventMapNotice kind="loading" title="Loading defensive territory" />
  if (error || !payload) {
    return <EventMapNotice kind="error" title="Defensive territory failed to load" onRetry={retry}>{error}</EventMapNotice>
  }
  const evidence = payload.selected
  const selectedHeight = view === 'clearance'
    ? evidence.heights.clearance
    : view === 'nonClearance'
      ? evidence.heights.nonClearanceAction
      : evidence.heights.all
  const selectedHeightLabel = view === 'clearance'
    ? 'Clearance depth'
    : view === 'nonClearance'
      ? 'Non-clearance median'
      : 'All-action median'
  const selectedRate = evidence.ratesPerStateMinute[view]
  const selectedLocated = evidence.grids[view].reduce((sum, cell) => sum + cell.rawCount, 0)
  const baselineHeight = payload.baseline
    ? view === 'clearance'
      ? payload.baseline.heights.clearance
      : view === 'nonClearance'
        ? payload.baseline.heights.nonClearanceAction
        : payload.baseline.heights.all
    : null

  return (
    <EventMapCard
      title="Defensive action territory"
      description="Observed action locations from the focal team's own goal (0) toward the opponent's goal (100)."
      controls={<EventMapViewTabs value={view} options={viewOptions} onChange={setView} label="Defensive action family" />}
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      footer={(
        <div className="space-y-2">
          {evidence.evidence.sparse ? (
            <EventMapNotice kind="sparse" title="Sparse location sample">
              {evidence.evidence.locatedSampleSize} located actions; interpret the territory pattern cautiously below {evidence.evidence.sparseThreshold}.
            </EventMapNotice>
          ) : null}
          <EventMetricStrip metrics={[
            { label: selectedHeightLabel, value: pitchHeight(selectedHeight.median) },
            { label: 'Recovery height', value: pitchHeight(evidence.heights.recovery.median) },
            { label: 'Per state min', value: rate(selectedRate) },
            { label: 'Located', value: evidence.counts.withLocation },
            { label: 'No location', value: evidence.counts.withoutLocation },
          ]} />
          {baselineHeight ? (
            <p className="text-[9px] text-ink-dim">
              Baseline median {pitchHeight(baselineHeight.median)} · comparison median {pitchHeight(selectedHeight.median)}. The API supplies identical 12×8 bins for both scopes for State Delta Map comparison.
            </p>
          ) : null}
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-[8px] uppercase tracking-[0.1em] text-ink-dim" aria-label="Defensive event family composition">
            {evidence.familyComposition.filter(row => row.count > 0).map(row => (
              <span key={row.family}>{familyLabel(row.family)} {row.count}</span>
            ))}
          </div>
          <p className="text-[9px] leading-relaxed text-gold">{evidence.disclaimer}</p>
        </div>
      )}
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        {selectedLocated ? (
          <PortraitPitch
            densityCells={evidence.grids[view]}
            densityStyle="cells"
            layerOptions={{ densityColor: view === 'clearance' ? '#F0A832' : '#4A9EF5' }}
            ariaLabel={`${payload.teamName} ${view === 'clearance' ? 'clearance' : 'defensive action'} territory. Own goal at zero, opponent goal at one hundred.`}
          />
        ) : <EventMapNotice kind="empty" title="No located defensive actions in this state" />}
      </EventPitchStage>
    </EventMapCard>
  )
}
