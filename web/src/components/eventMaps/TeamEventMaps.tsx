import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { fetchTeamEventProfile } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { EventShot, TeamPassFlow } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventCoverage, EventMapCard, EventMapNotice, EventMetricStrip,
  EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'

type TeamMap = 'flow' | 'shots-for' | 'shots-against' | 'territory' | 'territory-against'

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
      <span className="inline-flex items-center gap-1.5"><span className="h-px w-5 bg-gold" aria-hidden /> Arrow = direction</span>
      <span className="inline-flex items-center gap-1.5"><span className="h-1 w-5 bg-gold" aria-hidden /> Width + opacity = volume</span>
      <span>{total.toLocaleString()} completed passes across visible routes</span>
    </div>
  )
}

export function TeamEventMaps({ teamId, competition, season }: {
  teamId: number
  competition: string
  season: string
}) {
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [showAllFlows, setShowAllFlows] = useState(false)
  const [expanded, setExpanded] = useState<TeamMap | null>(null)
  const profileQuery = useQuery({
    queryKey: ['team-event-profile', teamId, competition, season],
    queryFn: () => fetchTeamEventProfile(teamId, competition, season),
    staleTime: 10 * 60 * 1000,
  })
  const profile = profileQuery.data
  const nonzeroFlows = useMemo(() => profile?.passFlows.filter(flow => flow.completedCount > 0) ?? [], [profile])
  const visibleThreshold = useMemo(() => {
    const maximum = nonzeroFlows.reduce((value, flow) => Math.max(value, flow.completedCount), 0)
    return Math.max(8, Math.ceil(maximum * 0.12))
  }, [nonzeroFlows])
  const visibleFlows = useMemo(
    () => showAllFlows ? nonzeroFlows : nonzeroFlows.filter(flow => flow.completedCount >= visibleThreshold),
    [nonzeroFlows, showAllFlows, visibleThreshold],
  )

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
      <EventMapCard key={map} title={title} description={pitchView === 'attacking-half' ? 'Attacking half shown; every shot originates beyond halfway.' : 'Full pitch shown because at least one shot originates behind halfway.'} footer={(
        <div className="space-y-2">
          <ShotMapLegend />
          {selection?.kind === 'shot' && shots.some(shot => shot.id === selection.id) ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : null}
        </div>
      )}>
        <MapStage map={map} expanded={expanded} setExpanded={setExpanded}>
          {shots.length ? <PortraitPitch shots={shots} pitchView={pitchView} selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.teamName} ${title.toLowerCase()} map. ${pitchView === 'attacking-half' ? 'Attacking half' : 'Full pitch'}; acting team attacks bottom to top.`} /> : <EventMapNotice kind="empty" title={`No ${title.toLowerCase()} recorded`} />}
        </MapStage>
      </EventMapCard>
    )
  }

  return (
    <section aria-labelledby="team-event-maps-heading">
      <div className="mb-3 border-b border-line-bright pb-3">
        <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-electric/80">WhoScored season events</p>
        <h2 id="team-event-maps-heading" className="text-[20px] font-black tracking-tight text-ink">Event Maps</h2>
        <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-ink-dim">Flow, shooting and territory maps appear together and share one bottom-to-top attacking direction.</p>
      </div>

      <div className="mb-4 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(220px,0.55fr)]">
        <EventMetricStrip metrics={[
          { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
          { label: 'Shots for', value: profile.summary.shots_for?.toLocaleString() ?? '—' },
          { label: 'Shots against', value: profile.summary.shots_against?.toLocaleString() ?? '—' },
        ]} />
        <EventCoverage coverage={profile.coverage} />
      </div>

      <div className="grid items-start gap-4 md:grid-cols-2">
        <EventMapCard title="Completed pass flow" description={showAllFlows ? `All ${visibleFlows.length} non-zero routes.` : `${visibleFlows.length} routes with at least ${visibleThreshold} completions.`} controls={(
          <button type="button" onClick={() => setShowAllFlows(value => !value)} className="h-8 border border-control-border bg-raised px-2 text-[8px] font-bold uppercase tracking-[0.1em] text-control-fg hover:border-electric hover:text-ink">
            {showAllFlows ? 'Focus routes' : 'Show all'}
          </button>
        )} footer={<FlowLegend flows={visibleFlows} />}>
          <MapStage map="flow" expanded={expanded} setExpanded={setExpanded}>
            {visibleFlows.length ? <PortraitPitch flows={visibleFlows} ariaLabel={`${profile.teamName} completed pass flow. Arrowheads show direction; width and opacity show volume. Acting team attacks bottom to top.`} /> : <EventMapNotice kind="empty" title="No completed pass flows recorded" />}
          </MapStage>
        </EventMapCard>

        {shotCard('for', shotsFor, 'shots-for')}
        {shotCard('against', shotsAgainst, 'shots-against')}

        <EventMapCard title="Territory" description="Fine-grained share of the team's located actions." footer={<p className="text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim"><span className="mr-1.5 inline-block size-3 bg-mint/55 align-middle" /> More team action share</p>}>
          <MapStage map="territory" expanded={expanded} setExpanded={setExpanded}>
            {profile.actionTerritory.some(cell => cell.rawCount > 0) ? <PortraitPitch densityCells={profile.actionTerritory} ariaLabel={`${profile.teamName} action-territory share map. Acting team attacks bottom to top.`} /> : <EventMapNotice kind="empty" title="No located team actions recorded" />}
          </MapStage>
        </EventMapCard>

        <EventMapCard title="Opponent territory" description="Fine-grained share of opponents' located actions in these matches." footer={<p className="text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim"><span className="mr-1.5 inline-block size-3 bg-ember/55 align-middle" /> More opponent action share</p>}>
          <MapStage map="territory-against" expanded={expanded} setExpanded={setExpanded}>
            {profile.opponentActionTerritory.some(cell => cell.rawCount > 0) ? <PortraitPitch densityCells={profile.opponentActionTerritory} layerOptions={{ densityColor: '#EF5C66' }} ariaLabel={`${profile.teamName} opponent action-territory share map. Acting team attacks bottom to top.`} /> : <EventMapNotice kind="empty" title="No located opponent actions recorded" />}
          </MapStage>
        </EventMapCard>
      </div>
    </section>
  )
}
