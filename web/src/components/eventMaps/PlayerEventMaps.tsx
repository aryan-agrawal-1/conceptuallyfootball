import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
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
  const locatedTouchCount = useMemo(
    () => profile?.touchGrid.reduce((total, cell) => total + cell.rawCount, 0) ?? 0,
    [profile?.touchGrid],
  )

  if (profileQuery.isLoading) return <EventMapNotice kind="loading" title="Loading player event profile" />
  if (profileQuery.isError || !profile) {
    return <EventMapNotice kind="error" title="Player event profile failed to load" onRetry={() => profileQuery.refetch()}>
      {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
    </EventMapNotice>
  }

  return (
    <section aria-label="Player event maps" className="relative">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <div className="min-w-0 flex-1">
          <EventMetricStrip metrics={[
            { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
            { label: 'Shots', value: profile.summary.shots?.toLocaleString() ?? '—' },
            { label: 'Touches', value: locatedTouchCount.toLocaleString() },
          ]} />
        </div>
        <div className="min-w-[220px]"><EventCoverage coverage={profile.coverage} /></div>
        {teams.length > 1 ? (
          <label className="flex items-center justify-between gap-2 border border-line-bright bg-panel px-3 text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim sm:justify-start">
            Team split
            <select value={teamId ?? ''} onChange={event => { setSelection(null); setTeamId(event.target.value ? Number(event.target.value) : null) }} className="h-9 min-w-40 max-w-full border border-control-border bg-panel px-3 text-[10px] text-control-fg outline-none hover:border-electric focus:border-electric">
              <option value="">Season total</option>
              {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      <div className="grid items-start gap-3 lg:grid-cols-12">
        {profile.modules.passMap.available ? (
          <EventMapCard className="lg:col-span-8" expanded={expanded === 'passes'} onExpandedChange={next => setExpanded(next ? 'passes' : null)} title="Pass map" description={`${passQuery.data?.totalMatching.toLocaleString() ?? '—'} ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} in this scope.`} controls={(
            <span className="relative inline-flex">
              <select aria-label="Pass category" value={passFilter} onChange={event => { setSelection(null); setPassFilter(event.target.value as PlayerPassFilter) }} className="h-8 max-w-36 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric">
                {PASS_FILTERS.map(filter => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
              </select>
              <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
            </span>
          )} footer={passQuery.data?.truncated ? (
            <EventMapNotice kind="truncated" title="Pass response capped at 5,000 rows">{passQuery.data.totalMatching.toLocaleString()} passes match; choose a narrower category to inspect every row.</EventMapNotice>
          ) : selection?.kind === 'pass' ? (
            <EventSelectionDetails selection={selection} matches={passQuery.data?.matches ?? {}} />
          ) : <p className="text-[9px] text-ink-dim">Hover, tap or focus a pass to inspect it.</p>}>
            <MapStage map="passes" expanded={expanded} setExpanded={setExpanded}>
              {passQuery.isLoading ? <EventMapNotice kind="loading" title="Loading pass rows" /> : passQuery.isError || !passQuery.data ? (
                <EventMapNotice kind="error" title="Pass map failed to load" onRetry={() => passQuery.refetch()} />
              ) : passQuery.data.passes.length ? (
                <PortraitPitch passes={passQuery.data.passes} selectedEventId={selection?.kind === 'pass' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} pass map. Attacking left to right.`} />
              ) : <EventMapNotice kind="empty" title="No passes match this category" />}
            </MapStage>
          </EventMapCard>
        ) : null}

        {profile.modules.shotMap.available ? (
          <EventMapCard className="lg:col-span-4" expanded={expanded === 'shots'} onExpandedChange={next => setExpanded(next ? 'shots' : null)} title="Shot map" description={shotPitchView === 'attacking-half' ? 'Attacking half shown; all shots originate beyond halfway.' : 'Full pitch shown because this scope includes a shot from behind halfway.'} footer={(
            <div className="space-y-2">
              <ShotMapLegend />
              {selection?.kind === 'shot' ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : <p className="text-[9px] text-ink-dim">Click, tap or focus a shot to inspect it.</p>}
            </div>
          )}>
            <MapStage map="shots" expanded={expanded} setExpanded={setExpanded}>
              <PortraitPitch shots={profile.shots} pitchView={shotPitchView} eventSelectionMode="click" selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} shot map. ${shotPitchView === 'attacking-half' ? 'Attacking half' : 'Full pitch'}; attacking left to right.`} />
            </MapStage>
          </EventMapCard>
        ) : null}

        {locatedTouchCount > 0 ? (
          <EventMapCard className="lg:col-span-12" expanded={expanded === 'actions'} onExpandedChange={next => setExpanded(next ? 'actions' : null)} title="Touch heatmap" description="Smoothed density of located touches only, with the average touch position overlaid." footer={(
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim">
              <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full bg-mint/55 blur-[2px]" aria-hidden /> Higher touch density</span>
              {profile.averageTouchLocation ? <span className="inline-flex items-center gap-1.5 text-electric"><span aria-hidden>◆</span> Average touch · {profile.averageTouchLocation.sampleSize.toLocaleString()} touches</span> : null}
              </div>
              {locatedTouchCount < 100 ? <EventMapNotice kind="sparse" title="Small located-touch sample">The heatmap is directional context, not a settled season tendency.</EventMapNotice> : null}
            </div>
          )}>
            <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
              <PortraitPitch densityCells={profile.touchGrid} densityStyle="smooth" markers={profile.averageTouchLocation ? [{ id: 'average-touch', coordinate: profile.averageTouchLocation, kind: 'jersey', ariaLabel: `Average touch location from ${profile.averageTouchLocation.sampleSize} located touches`, label: 'Avg touch', tone: 'accent' }] : []} ariaLabel={`${profile.playerName} touch-only heatmap with average touch overlay. Attacking left to right.`} />
            </MapStage>
          </EventMapCard>
        ) : null}
      </div>
    </section>
  )
}
