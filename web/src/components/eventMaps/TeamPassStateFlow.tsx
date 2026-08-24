import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { fetchTeamPassState, type StateLensRequest } from '../../lib/eventMaps/api'
import type { PassStateCategory, TeamPassFlow } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import { EventMapCard, EventMapNotice, EventPitchStage } from './EventMapUi'

function percent(value: number | null) {
  return value == null ? '—' : `${(value * 100).toFixed(1)}%`
}

function metres(value: number | null) {
  return value == null ? '—' : `${value.toFixed(1)}m`
}

function EvidenceBands({ title, rows }: { title: string; rows: PassStateCategory[] }) {
  return (
    <div>
      <p className="mb-1 text-[8px] font-bold uppercase tracking-[0.12em] text-ink-muted">{title}</p>
      <div className="grid grid-cols-3 gap-1">
        {rows.map(row => (
          <div key={row.category} className="rounded border border-line/60 bg-paper/40 px-2 py-1.5">
            <p className="text-[8px] font-bold uppercase text-ink-dim">{row.category}</p>
            <p className="font-mono text-[10px] text-ink">{percent(row.attemptShare)} choice</p>
            <p className="font-mono text-[9px] text-ink-muted">{percent(row.completionRate)} complete</p>
          </div>
        ))}
      </div>
    </div>
  )
}

export function TeamPassStateFlow({
  teamId,
  teamName,
  competition,
  season,
  matchRef,
  stateLens,
  expanded,
  onExpandedChange,
}: {
  teamId: number
  teamName: string
  competition: string
  season: string
  matchRef: string | null
  stateLens: StateLensRequest
  expanded: boolean
  onExpandedChange: (expanded: boolean) => void
}) {
  const [selectedFlow, setSelectedFlow] = useState<TeamPassFlow | null>(null)
  const query = useQuery({
    queryKey: ['team-pass-state', teamId, competition, season, matchRef, stateLens],
    queryFn: () => fetchTeamPassState(teamId, competition, season, matchRef, stateLens),
    staleTime: 10 * 60 * 1000,
  })
  const evidence = query.data?.selected

  if (query.isLoading) return <EventMapNotice kind="loading" title="Loading state passing evidence" />
  if (query.isError || !evidence) {
    return <EventMapNotice kind="error" title="State passing evidence failed to load" onRetry={() => query.refetch()}>
      {query.error?.message ?? 'The pass-state service returned no data.'}
    </EventMapNotice>
  }

  const summary = evidence.summary
  const disclosure = [
    evidence.evidence.sparse ? 'Sparse cohort' : null,
    evidence.evidence.truncated ? `Capped at ${summary.attempts.toLocaleString()} located passes` : null,
    evidence.evidence.excludedMissingCoordinates
      ? `${evidence.evidence.excludedMissingCoordinates.toLocaleString()} passes excluded for missing coordinates`
      : null,
  ].filter(Boolean).join(' · ')

  return (
    <EventMapCard
      expanded={expanded}
      onExpandedChange={onExpandedChange}
      title="Pass flow by game state"
      description="Attempt volume and mean pass shape in each origin zone; completion is shown separately."
      footer={(
        <div className="space-y-2">
          <div className="grid grid-cols-3 gap-2 text-[9px]">
            <p><span className="block font-bold uppercase text-ink-dim">Tempo</span>{summary.attemptsPerStateMinute?.toFixed(2) ?? '—'} / state min</p>
            <p><span className="block font-bold uppercase text-ink-dim">Completion</span>{percent(summary.completionRate)}</p>
            <p><span className="block font-bold uppercase text-ink-dim">Mean pass</span>{metres(summary.meanLengthMetres)}</p>
          </div>
          <EvidenceBands title="Attempted direction · execution within direction" rows={evidence.directions} />
          <EvidenceBands title="Attempted length · execution within length" rows={evidence.lengthBands} />
          <p className="text-[9px] text-ink-muted">
            {summary.attempts.toLocaleString()} attempted · {summary.completions.toLocaleString()} completed · {evidence.exposureMinutes.toFixed(1)} eligible state minutes
            {disclosure ? ` · ${disclosure}` : ''}
          </p>
        </div>
      )}
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        {evidence.flows.length ? (
          <PortraitPitch
            flows={evidence.flows}
            selectedFlowId={selectedFlow?.id ?? null}
            onSelectedFlowChange={setSelectedFlow}
            ariaLabel={`${teamName} state-conditioned pass flow. Origin shade shows attempts; arrows show attempted mean direction and length; completion is disclosed separately.`}
          />
        ) : <EventMapNotice kind="empty" title="No located passes in this state scope" />}
      </EventPitchStage>
    </EventMapCard>
  )
}
