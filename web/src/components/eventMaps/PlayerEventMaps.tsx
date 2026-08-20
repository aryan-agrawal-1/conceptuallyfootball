import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { fetchPlayerEventProfile, fetchPlayerPassMap } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { PlayerPassFilter } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventCoverage, EventMapCard, EventMapNotice, EventMetricStrip,
  EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'

const PASS_FILTERS: Array<{ value: PlayerPassFilter; label: string }> = [
  { value: 'all', label: 'All passes' },
  { value: 'completed', label: 'Completed' },
  { value: 'progressive', label: 'Progressive' },
  { value: 'final_third_entry', label: 'Final third' },
  { value: 'box_entry', label: 'Box entries' },
  { value: 'key_pass', label: 'Key passes' },
  { value: 'cross', label: 'Crosses' },
  { value: 'long_ball', label: 'Long balls' },
  { value: 'failed', label: 'Failed' },
]

export type PlayerEventMapTeam = { id: number; name: string }
type PlayerMap = 'passes' | 'shots' | 'actions'

function MapStage({ map, expanded, setExpanded, children }: {
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

export function PlayerEventMaps({ playerId, competition, season, teams }: {
  playerId: number
  competition: string
  season: string
  teams: PlayerEventMapTeam[]
}) {
  const [passFilter, setPassFilter] = useState<PlayerPassFilter>('all')
  const [teamId, setTeamId] = useState<number | null>(null)
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [expanded, setExpanded] = useState<PlayerMap | null>(null)
  const profileQuery = useQuery({
    queryKey: ['player-event-profile', playerId, competition, season, teamId],
    queryFn: () => fetchPlayerEventProfile(playerId, competition, season, teamId),
    staleTime: 10 * 60 * 1000,
  })
  const profile = profileQuery.data
  const passQuery = useQuery({
    queryKey: ['player-event-passes', playerId, competition, season, teamId, passFilter],
    queryFn: () => fetchPlayerPassMap(playerId, competition, season, passFilter, teamId),
    enabled: profile?.modules.passMap.available === true,
    staleTime: 10 * 60 * 1000,
  })
  const shotPitchView = useMemo(
    () => profile?.shots.some(shot => shot.location.x < 50) ? 'full' as const : 'attacking-half' as const,
    [profile?.shots],
  )

  if (profileQuery.isLoading) return <EventMapNotice kind="loading" title="Loading player event profile" />
  if (profileQuery.isError || !profile) {
    return <EventMapNotice kind="error" title="Player event profile failed to load" onRetry={() => profileQuery.refetch()}>
      {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
    </EventMapNotice>
  }

  return (
    <section aria-labelledby="player-event-maps-heading" className="relative">
      <div className="mb-3 flex flex-col gap-3 border-b border-line-bright pb-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-electric/80">WhoScored season events</p>
          <h2 id="player-event-maps-heading" className="text-[20px] font-black tracking-tight text-ink">Event Maps</h2>
          <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-ink-dim">Every map uses the same direction: the player&apos;s team attacks from bottom to top.</p>
        </div>
        {teams.length > 1 ? (
          <label className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim">
            Team split
            <select value={teamId ?? ''} onChange={event => { setSelection(null); setTeamId(event.target.value ? Number(event.target.value) : null) }} className="h-9 min-w-40 max-w-full border border-control-border bg-panel px-3 text-[10px] text-control-fg outline-none hover:border-electric focus:border-electric">
              <option value="">Season total</option>
              {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      <div className="mb-4 grid gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(220px,0.55fr)]">
        <EventMetricStrip metrics={[
          { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
          { label: 'Shots', value: profile.summary.shots?.toLocaleString() ?? '—' },
          { label: 'Actions', value: profile.summary.valid_location_actions?.toLocaleString() ?? '—' },
        ]} />
        <EventCoverage coverage={profile.coverage} />
      </div>

      <div className="grid items-start gap-4 md:grid-cols-2">
        {profile.modules.passMap.available ? (
          <EventMapCard title="Pass map" description={`${passQuery.data?.totalMatching.toLocaleString() ?? '—'} ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} in this scope.`} controls={(
            <select aria-label="Pass category" value={passFilter} onChange={event => { setSelection(null); setPassFilter(event.target.value as PlayerPassFilter) }} className="h-8 max-w-36 border border-control-border bg-raised px-2 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric">
              {PASS_FILTERS.map(filter => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
            </select>
          )} footer={passQuery.data?.truncated ? (
            <EventMapNotice kind="truncated" title="Pass response capped at 5,000 rows">{passQuery.data.totalMatching.toLocaleString()} passes match; choose a narrower category to inspect every row.</EventMapNotice>
          ) : selection?.kind === 'pass' ? (
            <EventSelectionDetails selection={selection} matches={passQuery.data?.matches ?? {}} />
          ) : <p className="text-[9px] text-ink-dim">Hover, tap or focus a pass to inspect it.</p>}>
            <MapStage map="passes" expanded={expanded} setExpanded={setExpanded}>
              {passQuery.isLoading ? <EventMapNotice kind="loading" title="Loading pass rows" /> : passQuery.isError || !passQuery.data ? (
                <EventMapNotice kind="error" title="Pass map failed to load" onRetry={() => passQuery.refetch()} />
              ) : passQuery.data.passes.length ? (
                <PortraitPitch passes={passQuery.data.passes} selectedEventId={selection?.kind === 'pass' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} pass map. Attacking bottom to top.`} />
              ) : <EventMapNotice kind="empty" title="No passes match this category" />}
            </MapStage>
          </EventMapCard>
        ) : null}

        {profile.modules.shotMap.available ? (
          <EventMapCard title="Shot map" description={shotPitchView === 'attacking-half' ? 'Attacking half shown; all shots originate beyond halfway.' : 'Full pitch shown because this scope includes a shot from behind halfway.'} footer={(
            <div className="space-y-2">
              <ShotMapLegend />
              {selection?.kind === 'shot' ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : null}
            </div>
          )}>
            <MapStage map="shots" expanded={expanded} setExpanded={setExpanded}>
              <PortraitPitch shots={profile.shots} pitchView={shotPitchView} selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} shot map. ${shotPitchView === 'attacking-half' ? 'Attacking half' : 'Full pitch'}; attacking bottom to top.`} />
            </MapStage>
          </EventMapCard>
        ) : null}

        {profile.modules.actionGrid.available ? (
          <EventMapCard title="Action map" description="Fine-grained share of located actions, with average touch position overlaid." footer={(
            <div className="flex flex-wrap items-center gap-3 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim">
              <span className="inline-flex items-center gap-1.5"><span className="size-3 bg-mint/55" aria-hidden /> More action share</span>
              {profile.averageTouchLocation ? <span className="inline-flex items-center gap-1.5 text-electric"><span aria-hidden>◆</span> Average touch · {profile.averageTouchLocation.sampleSize.toLocaleString()} touches</span> : null}
            </div>
          )}>
            <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
              <PortraitPitch densityCells={profile.actionGrid} markers={profile.averageTouchLocation ? [{ id: 'average-touch', coordinate: profile.averageTouchLocation, kind: 'jersey', ariaLabel: `Average touch location from ${profile.averageTouchLocation.sampleSize} touches`, label: 'Avg touch', tone: 'accent' }] : []} ariaLabel={`${profile.playerName} action-density map with average touch overlay. Attacking bottom to top.`} />
            </MapStage>
          </EventMapCard>
        ) : null}
      </div>
    </section>
  )
}
