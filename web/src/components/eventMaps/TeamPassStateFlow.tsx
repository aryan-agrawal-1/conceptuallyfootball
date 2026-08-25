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
      <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-ink-dim">{title}</p>
      <div className="grid grid-cols-3 gap-2">
        {rows.map(row => (
          <div key={row.category} className="rounded border border-line/60 bg-paper/40 px-2 py-1.5">
            <p className="text-[10px] font-bold uppercase text-ink-dim">{row.category}</p>
            <p className="font-mono text-[12px] text-ink">{percent(row.attemptShare)} choice</p>
            <p className="whitespace-nowrap font-mono text-[11px] text-ink-dim">{percent(row.completionRate)} completion</p>
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
    >
      <EventPitchStage expanded={expanded} onExpandedChange={onExpandedChange}>
        <div className="grid w-full items-start gap-8 lg:grid-cols-[minmax(0,1.45fr)_minmax(400px,0.75fr)]">
          <div>
            {evidence.flows.length ? (
              <PortraitPitch
                flows={evidence.flows}
                selectedFlowId={selectedFlow?.id ?? null}
                onSelectedFlowChange={setSelectedFlow}
                ariaLabel={`${teamName} state-conditioned pass flow. Origin shade shows attempts; arrows show attempted mean direction and length; completion is disclosed separately.`}
              />
            ) : <EventMapNotice kind="empty" title="No located passes in this state scope" />}
          </div>
          <aside className="space-y-4 border-t border-line-bright pt-5 lg:border-t-0 lg:pt-0" aria-label="Passing evidence">
            <div className="grid grid-cols-3 gap-3 text-[12px] leading-relaxed lg:grid-cols-1">
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Passes per minute</span>{summary.attemptsPerStateMinute?.toFixed(2) ?? '—'}</p>
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Pass completion</span>{percent(summary.completionRate)}</p>
              <p><span className="block text-[10px] font-bold uppercase tracking-[0.08em] text-ink-dim">Mean pass length</span>{metres(summary.meanLengthMetres)}</p>
            </div>
            <EvidenceBands title="Direction" rows={evidence.directions} />
            <EvidenceBands title="Length" rows={evidence.lengthBands} />
            <p className="text-[11px] leading-relaxed text-ink-dim">
              Passes per minute uses only the eligible minutes in the selected game state. {summary.attempts.toLocaleString()} attempted · {summary.completions.toLocaleString()} completed · {evidence.exposureMinutes.toFixed(1)} eligible minutes
              {disclosure ? ` · ${disclosure}` : ''}
            </p>
          </aside>
        </div>
      </EventPitchStage>
    </EventMapCard>
  )
}
