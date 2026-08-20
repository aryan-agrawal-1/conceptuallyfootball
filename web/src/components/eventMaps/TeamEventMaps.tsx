import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { fetchTeamEventProfile } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { EventShot, TeamPassFlow } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventCoverage, EventMapCard, EventMapNotice, EventMetricStrip,
  EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'

type TeamMap = 'flow' | 'shots-for' | 'shots-against'

function MapStage({ map, expanded, setExpanded, children }: {
  map: TeamMap
  expanded: TeamMap | null
  setExpanded: (map: TeamMap | null) => void
  children: ReactNode
}) {
  return (
    <EventPitchStage expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)}>
      {children}
    </EventPitchStage>
  )
}

function shotPitchView(shots: EventShot[]) {
  return shots.some(shot => shot.location.x < 50) ? 'full' as const : 'attacking-half' as const
}

function FlowLegend({ flows }: { flows: TeamPassFlow[] }) {
  const total = flows.reduce((sum, flow) => sum + flow.completedCount, 0)
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim">
      <span className="inline-flex items-center gap-1.5"><span className="h-px w-5 bg-gold" aria-hidden /> Arrow = mean destination direction + length</span>
      <span className="inline-flex items-center gap-1.5"><span className="h-3 w-5 bg-gold/35" aria-hidden /> Origin shade = completed-pass volume</span>
      <span>{total.toLocaleString()} completed passes across {flows.length} occupied origin bins</span>
    </div>
  )
}

export function TeamEventMaps({ teamId, competition, season }: {
  teamId: number
  competition: string
  season: string
}) {
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [selectedFlow, setSelectedFlow] = useState<TeamPassFlow | null>(null)
  const [expanded, setExpanded] = useState<TeamMap | null>(null)
  const profileQuery = useQuery({
    queryKey: ['team-event-profile', teamId, competition, season],
    queryFn: () => fetchTeamEventProfile(teamId, competition, season),
    staleTime: 10 * 60 * 1000,
  })
  const profile = profileQuery.data
  if (profileQuery.isLoading) return <EventMapNotice kind="loading" title="Loading team event profile" />
  if (profileQuery.isError || !profile) {
    return <EventMapNotice kind="error" title="Team event profile failed to load" onRetry={() => profileQuery.refetch()}>
      {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
    </EventMapNotice>
  }

  const shotsFor = profile.shots.filter(shot => shot.perspective === 'for')
  const shotsAgainst = profile.shots.filter(shot => shot.perspective === 'against')

  const shotCard = (kind: 'for' | 'against', shots: EventShot[], map: TeamMap) => {
    const pitchView = shotPitchView(shots)
    const title = kind === 'for' ? 'Shots for' : 'Shots against'
    return (
      <EventMapCard key={map} expanded={expanded === map} onExpandedChange={next => setExpanded(next ? map : null)} title={title} description={pitchView === 'attacking-half' ? 'Attacking half shown; every shot originates beyond halfway.' : 'Full pitch shown because at least one shot originates behind halfway.'} footer={(
        <div className="space-y-2">
          <ShotMapLegend />
          {selection?.kind === 'shot' && shots.some(shot => shot.id === selection.id) ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : <p className="text-[9px] text-ink-dim">Click, tap or focus a shot to inspect it.</p>}
        </div>
      )}>
        <MapStage map={map} expanded={expanded} setExpanded={setExpanded}>
          {shots.length ? <PortraitPitch shots={shots} pitchView={pitchView} eventSelectionMode="click" selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.teamName} ${title.toLowerCase()} map. ${pitchView === 'attacking-half' ? 'Attacking half' : 'Full pitch'}; acting team attacks left to right.`} /> : <EventMapNotice kind="empty" title={`No ${title.toLowerCase()} recorded`} />}
        </MapStage>
      </EventMapCard>
    )
  }

  return (
    <section aria-label="Team event maps">
      <div className="mb-3 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(220px,0.55fr)]">
        <EventMetricStrip metrics={[
          { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
          { label: 'Shots for', value: profile.summary.shots_for?.toLocaleString() ?? '—' },
          { label: 'Shots against', value: profile.summary.shots_against?.toLocaleString() ?? '—' },
        ]} />
        <EventCoverage coverage={profile.coverage} />
      </div>

      <div className="space-y-3">
        <EventMapCard expanded={expanded === 'flow'} onExpandedChange={next => setExpanded(next ? 'flow' : null)} title="Pass flow field" description="Each arrow summarises completed passes beginning in one occupied 6×4 origin bin." footer={(
          <div className="space-y-2">
            <FlowLegend flows={profile.passFlows} />
            <p className="text-[9px] text-ink-muted">Hover, tap or focus anywhere in an origin bin to inspect its field vector on the pitch.</p>
          </div>
        )}>
          <MapStage map="flow" expanded={expanded} setExpanded={setExpanded}>
            {profile.passFlows.length ? <PortraitPitch flows={profile.passFlows} selectedFlowId={selectedFlow?.id ?? null} onSelectedFlowChange={setSelectedFlow} ariaLabel={`${profile.teamName} completed-pass flow field. Arrows show mean destination direction and length; origin shade shows completed-pass volume. Acting team attacks left to right.`} /> : <EventMapNotice kind="empty" title="No completed pass flows recorded" />}
          </MapStage>
        </EventMapCard>

        <div className="grid items-start gap-3 lg:grid-cols-2">
          {shotCard('for', shotsFor, 'shots-for')}
          {shotCard('against', shotsAgainst, 'shots-against')}
        </div>
      </div>
    </section>
  )
}
