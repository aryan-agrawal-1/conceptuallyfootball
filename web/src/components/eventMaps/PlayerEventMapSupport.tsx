import type { ReactNode } from 'react'
import type { ProfileRateMode } from '../../lib/profileMetrics'
import type { PlayerStateComparisonPayload, PlayerStateCohort } from '../../types/eventMaps'
import { ProfileSelectControl } from '../profile/ProfileScopeSelector'
import { statePresentation } from '../../lib/eventMaps/statePresentation'
import { EventPitchStage } from './EventMapUi'
import {
  PENALTY_OPTIONS,
  SHOT_CHANCE_FILTERS,
  SHOT_OUTCOME_FILTERS,
  cohortReliability,
  formatCohortMetric,
  formatComparisonMetric,
  formatMetres,
  formatPercent,
  scopeLabel,
  type PenaltyOption,
  type PlayerMap,
  type ShotChanceFilter,
  type ShotOutcomeFilter,
} from './PlayerEventMapLogic'

export function EvidenceRow({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-line-bright pt-2 text-[10px]">
      <span className="text-ink-dim">{label}</span>
      <span className="text-right font-mono text-ink">{value}{detail ? <span className="ml-1 text-[8px] text-ink-muted">{detail}</span> : null}</span>
    </div>
  )
}

function ReliabilityBadge({ status, label }: { status: 'verified' | 'partial' | 'sparse' | 'unsupported' | 'unavailable'; label?: string }) {
  return <span className={`text-[9px] font-bold uppercase tracking-[0.08em] ${status === 'verified' ? 'text-mint' : status === 'unavailable' ? 'text-ember' : 'text-gold'}`}>{label ?? status}</span>
}

export function StateEvidenceCard({ label, state, children }: { label: string; state: string; children: ReactNode }) {
  const presentation = statePresentation(state)
  return (
    <section className="border border-line/60 bg-paper/40 px-3 py-2" style={{ borderTopColor: presentation.color }}>
      <p className="text-[9px] font-bold uppercase tracking-[0.1em]" style={{ color: presentation.color }}>{label}</p>
      <div className="mt-2 space-y-2">{children}</div>
    </section>
  )
}

function PassingCohortCard({ label, state, cohort, rateMode }: { label: string; state: string; cohort: PlayerStateCohort; rateMode: ProfileRateMode }) {
  return (
    <StateEvidenceCard label={label} state={state}>
      <EvidenceRow label="Attempts" value={formatCohortMetric(cohort, 'pass_attempts', rateMode)} />
      <EvidenceRow label="Completion" value={formatPercent(cohort.passing.completionRate)} />
      <EvidenceRow label="Progressive passes" value={formatCohortMetric(cohort, 'progressive_passes', rateMode)} />
      <EvidenceRow label="Mean length · forward" value={`${formatMetres(cohort.passing.meanLengthMetres)} · ${formatMetres(cohort.passing.meanForwardMetres)}`} />
      <EvidenceRow label="Forward share" value={formatPercent(cohort.passing.forwardShare)} />
      <EvidenceRow label="Carries" value={formatCohortMetric(cohort, 'carries', rateMode)} />
      <EvidenceRow label="Progressive carries" value={formatCohortMetric(cohort, 'progressive_carries', rateMode)} />
      <EvidenceRow label="Carry length · forward" value={`${formatMetres(cohort.carrying.meanLengthMetres)} · ${formatMetres(cohort.carrying.meanForwardMetres)}`} />
      <EvidenceRow label="Team pass share" value={formatPercent(cohort.teamActionShares.passes?.share)} detail="matched" />
      <EvidenceRow label="Team progression share" value={formatPercent(cohort.teamActionShares.progressive_actions?.share)} detail="matched" />
    </StateEvidenceCard>
  )
}

export function PlayerPassingEvidence({ comparison, rateMode }: { comparison: PlayerStateComparisonPayload; rateMode: ProfileRateMode }) {
  const selected = comparison.selected
  const baseline = comparison.baseline
  const selectedState = comparison.stateLens.selected.state
  const baselineState = comparison.stateLens.comparison.baseline?.state ?? 'all'
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Player passing and carrying evidence">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Passing & carrying evidence</h3>
        <p className="text-[9px] text-ink-muted">{rateMode === 'per90' ? 'Rate view · verified state minutes' : 'Selected-context totals'}</p>
      </div>
      <div className={`mt-3 grid gap-3 ${baseline ? 'sm:grid-cols-2' : ''}`}>
        <PassingCohortCard label={scopeLabel(selectedState)} state={selectedState} cohort={selected} rateMode={rateMode} />
        {baseline ? <PassingCohortCard label={scopeLabel(baselineState)} state={baselineState} cohort={baseline} rateMode={rateMode} /> : null}
      </div>
      {baseline ? <div className="mt-3 border-t border-line-bright pt-2">
        <p className="text-[8px] font-bold uppercase tracking-[0.12em] text-ink-dim">Selected minus comparison</p>
        <div className="mt-2 grid gap-x-4 gap-y-1 sm:grid-cols-2">
          {(['pass_attempts', 'progressive_passes', 'carries', 'progressive_carries'] as const).map(key => <EvidenceRow key={key} label={key.replaceAll('_', ' ')} value={formatComparisonMetric(comparison, key, rateMode)} />)}
          <EvidenceRow label="Team pass share" value={comparison.comparison?.actionShareChange.passes == null ? '—' : `${comparison.comparison.actionShareChange.passes >= 0 ? '+' : ''}${(comparison.comparison.actionShareChange.passes * 100).toFixed(1)}pp`} />
          <EvidenceRow label="Team progression share" value={comparison.comparison?.actionShareChange.progressive_actions == null ? '—' : `${comparison.comparison.actionShareChange.progressive_actions >= 0 ? '+' : ''}${(comparison.comparison.actionShareChange.progressive_actions * 100).toFixed(1)}pp`} />
        </div>
      </div> : null}
      <p className="mt-3 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-muted">{comparison.teamContext.available ? 'Team shares use team events and derived carries from the same verified intervals.' : 'Choose one team split to enable matched-team shares.'}</p>
    </section>
  )
}

export function PlayerShootingEvidence({ comparison, rateMode }: { comparison: PlayerStateComparisonPayload; rateMode: ProfileRateMode }) {
  const selected = comparison.selected
  const baseline = comparison.baseline
  const card = (label: string, state: string, cohort: PlayerStateCohort) => <StateEvidenceCard label={label} state={state}>
    <EvidenceRow label="Shots" value={formatCohortMetric(cohort, 'shots', rateMode)} />
    <EvidenceRow label="Goals" value={formatCohortMetric(cohort, 'goals', rateMode)} />
    <EvidenceRow label="Big chances" value={formatCohortMetric(cohort, 'big_chance_shots', rateMode)} />
    <EvidenceRow label="Team shot share" value={formatPercent(cohort.teamActionShares.shots?.share)} detail="matched" />
  </StateEvidenceCard>
  return (
    <section className="border border-line-bright bg-panel p-3" aria-label="Player shooting evidence">
      <div className="flex flex-col gap-1 sm:flex-row sm:items-baseline sm:justify-between">
        <h3 className="text-[11px] font-black uppercase tracking-[0.14em] text-ink">Shooting evidence</h3>
        <p className="text-[9px] text-ink-muted">Rare shots and goals stay visibly qualified.</p>
      </div>
      <div className={`mt-3 grid gap-3 ${baseline ? 'sm:grid-cols-2' : ''}`}>
        {card(scopeLabel(comparison.stateLens.selected.state), comparison.stateLens.selected.state, selected)}
        {baseline ? card(scopeLabel(comparison.stateLens.comparison.baseline?.state ?? 'all'), comparison.stateLens.comparison.baseline?.state ?? 'all', baseline) : null}
      </div>
      <p className="mt-3 border-t border-line-bright pt-2 text-[9px] leading-relaxed text-ink-muted">Shot locations and goal zones remain event-backed. A low raw count is descriptive evidence, not a stable finishing or clutch claim.</p>
    </section>
  )
}

export function PlayerExposureCard({ label, cohort }: { label: string; cohort: PlayerStateCohort }) {
  const reliability = cohortReliability(cohort)
  return (
    <div className="border border-control-border bg-raised/35 px-3 py-2" data-player-state-cohort={label}>
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.1em] text-ink">{label}</p>
        <ReliabilityBadge status={reliability} />
      </div>
      <div className="mt-1.5 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] text-ink-dim">
        <span>{cohort.exposureMinutes.toLocaleString()} verified min</span>
        <span>{cohort.evidence.matchCount.toLocaleString()} matches</span>
        <span>{cohort.evidence.episodeCount.toLocaleString()} episodes</span>
        <span>{cohort.summary.actions.toLocaleString()} actions</span>
        <span>{cohort.touchLocation.sampleSize.toLocaleString()} located touches</span>
        <span className={cohort.evidence.matchesExcluded ? 'text-gold' : ''}>{cohort.evidence.matchesExcluded.toLocaleString()} excluded matches</span>
      </div>
    </div>
  )
}

export function PenaltyToggle({ value, onChange }: {
  value: PenaltyOption
  onChange: (value: PenaltyOption) => void
}) {
  return (
    <ProfileSelectControl compact ariaLabel="Penalty inclusion" value={value} options={PENALTY_OPTIONS} onChange={next => onChange(next as PenaltyOption)} className="w-36" />
  )
}

export function ShotMapFilters({
  outcome,
  chance,
  onOutcomeChange,
  onChanceChange,
}: {
  outcome: ShotOutcomeFilter
  chance: ShotChanceFilter
  onOutcomeChange: (value: ShotOutcomeFilter) => void
  onChanceChange: (value: ShotChanceFilter) => void
}) {
  return (
    <span className="flex flex-wrap justify-end gap-1.5">
      <ProfileSelectControl compact ariaLabel="Shot outcome" value={outcome} options={SHOT_OUTCOME_FILTERS} onChange={next => onOutcomeChange(next as ShotOutcomeFilter)} className="w-36" />
      <ProfileSelectControl compact ariaLabel="Shot chance classification" value={chance} options={SHOT_CHANCE_FILTERS} onChange={next => onChanceChange(next as ShotChanceFilter)} className="w-40" />
    </span>
  )
}

export function MapStage({ map, expanded, setExpanded, children }: {
  map: PlayerMap
  expanded: PlayerMap | null
  setExpanded: (map: PlayerMap | null) => void
  children: ReactNode
}) {
  return (
    <EventPitchStage expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)}>
      {children}
    </EventPitchStage>
  )
}
