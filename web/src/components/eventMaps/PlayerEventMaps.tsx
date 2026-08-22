import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { fetchGkShotZones, fetchPlayerEventProfile, fetchPlayerPassMap, fetchPlayerShotZones } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { PlayerPassFilter, PlayerPassOutcome, ShotZoneVariantKey } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import { GoalZoneGridView, GoalZoneTotals } from './GoalZones'
import {
  EventCoverage, EventMapCard, EventMapNotice, EventMatchFilter, EventMetricStrip,
  EventPitchStage, EventSelectionDetails, ShotMapLegend,
} from './EventMapUi'

const PASS_FILTERS: Array<{ value: PlayerPassFilter; label: string }> = [
  { value: 'all', label: 'All types' },
  { value: 'progressive', label: 'Progressive' },
  { value: 'final_third_entry', label: 'Final third' },
  { value: 'box_entry', label: 'Box entries' },
  { value: 'key_pass', label: 'Key passes' },
  { value: 'cross', label: 'Crosses' },
  { value: 'long_ball', label: 'Long balls' },
]

const PASS_OUTCOMES: Array<{ value: PlayerPassOutcome; label: string }> = [
  { value: 'all', label: 'All outcomes' },
  { value: 'completed', label: 'Completed' },
  { value: 'incomplete', label: 'Incomplete' },
]

export type PlayerEventMapTeam = { id: number; name: string }
type PlayerMap = 'passes' | 'shots' | 'actions' | 'zones' | 'gk-zones'

type PenaltyOption = ShotZoneVariantKey

const PENALTY_OPTIONS: Array<{ value: PenaltyOption; label: string }> = [
  { value: 'all', label: 'All shots' },
  { value: 'open_play', label: 'Non-penalties' },
  { value: 'penalties_only', label: 'Penalties' },
]

function PenaltyToggle({ value, onChange }: {
  value: PenaltyOption
  onChange: (value: PenaltyOption) => void
}) {
  return (
    <span className="relative inline-flex">
      <select
        aria-label="Penalty inclusion"
        value={value}
        onChange={event => onChange(event.target.value as PenaltyOption)}
        className="h-8 max-w-36 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric"
      >
        {PENALTY_OPTIONS.map(option => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
      <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
    </span>
  )
}

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

export function PlayerEventMaps({ playerId, competition, season, teams, positionGroup }: {
  playerId: number
  competition: string
  season: string
  teams: PlayerEventMapTeam[]
  positionGroup?: string
}) {
  const [passFilter, setPassFilter] = useState<PlayerPassFilter>('all')
  const [passOutcome, setPassOutcome] = useState<PlayerPassOutcome>('all')
  const [teamId, setTeamId] = useState<number | null>(null)
  const [matchRef, setMatchRef] = useState<string | null>(null)
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [expanded, setExpanded] = useState<PlayerMap | null>(null)
  const [shotPenalties, setShotPenalties] = useState<PenaltyOption>('all')
  const isGoalkeeper = positionGroup === 'GK'
  const profileQuery = useQuery({
    queryKey: ['player-event-profile', playerId, competition, season, teamId, matchRef],
    queryFn: () => fetchPlayerEventProfile(playerId, competition, season, teamId, matchRef),
    staleTime: 10 * 60 * 1000,
  })
  const profile = profileQuery.data
  const passQuery = useQuery({
    queryKey: ['player-event-passes', playerId, competition, season, teamId, matchRef, passFilter, passOutcome],
    queryFn: () => fetchPlayerPassMap(playerId, competition, season, passFilter, passOutcome, teamId, matchRef),
    enabled: profile?.modules.passMap.available === true,
    staleTime: 10 * 60 * 1000,
  })
  const zoneVariantKey: ShotZoneVariantKey = shotPenalties
  const shotZonesQuery = useQuery({
    queryKey: ['player-shot-zones', playerId, competition, season, teamId, matchRef],
    queryFn: () => fetchPlayerShotZones(playerId, competition, season, teamId, matchRef),
    enabled: !isGoalkeeper && profile?.modules.shotMap.available === true,
    staleTime: 10 * 60 * 1000,
  })
  const gkZonesQuery = useQuery({
    queryKey: ['player-gk-shot-zones', playerId, competition, season, matchRef],
    queryFn: () => fetchGkShotZones(playerId, competition, season, matchRef),
    enabled: isGoalkeeper,
    staleTime: 10 * 60 * 1000,
  })
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
        <EventMatchFilter matches={profile.matches} value={matchRef} onChange={value => { setSelection(null); setMatchRef(value) }} />
        {teams.length > 1 ? (
          <label className="flex items-center justify-between gap-2 border border-line-bright bg-panel px-3 text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim sm:justify-start">
            Team split
            <select value={teamId ?? ''} onChange={event => { setSelection(null); setMatchRef(null); setTeamId(event.target.value ? Number(event.target.value) : null) }} className="h-9 min-w-40 max-w-full border border-control-border bg-panel px-3 text-[10px] text-control-fg outline-none hover:border-electric focus:border-electric">
              <option value="">Season total</option>
              {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      <div className="grid gap-3 lg:grid-cols-12">
        {profile.modules.passMap.available ? (
          <EventMapCard className={isGoalkeeper ? 'lg:col-span-12' : 'lg:col-span-6'} expanded={expanded === 'passes'} onExpandedChange={next => setExpanded(next ? 'passes' : null)} title="Pass map" description={`${passQuery.data?.totalMatching.toLocaleString() ?? '—'} ${PASS_OUTCOMES.find(item => item.value === passOutcome)?.label.toLowerCase()} · ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} in this scope.`} controls={(
            <span className="flex flex-wrap gap-1.5">
              <span className="relative inline-flex">
                <select aria-label="Pass outcome" value={passOutcome} onChange={event => { setSelection(null); setPassOutcome(event.target.value as PlayerPassOutcome) }} className="h-8 max-w-36 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric">
                  {PASS_OUTCOMES.map(outcome => <option key={outcome.value} value={outcome.value}>{outcome.label}</option>)}
                </select>
                <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
              </span>
              <span className="relative inline-flex">
              <select aria-label="Pass category" value={passFilter} onChange={event => { setSelection(null); setPassFilter(event.target.value as PlayerPassFilter) }} className="h-8 max-w-36 appearance-none border border-control-border bg-raised py-0 pl-2.5 pr-9 text-[9px] font-bold uppercase tracking-[0.08em] text-control-fg outline-none focus:border-electric">
                {PASS_FILTERS.map(filter => <option key={filter.value} value={filter.value}>{filter.label}</option>)}
              </select>
              <ChevronDown size={13} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-control-fg" aria-hidden="true" />
              </span>
            </span>
          )} footer={(
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim" aria-label="Pass map legend">
                <span className="inline-flex items-center gap-1.5"><span className="h-px w-4 bg-electric" aria-hidden /> Pass</span>
                <span className="inline-flex items-center gap-1.5"><span className="inline-block h-px w-4 border-t border-dashed border-ink-dim" aria-hidden /> Derived carry</span>
              </div>
              {passQuery.data?.truncated ? (
                <EventMapNotice kind="truncated" title="Pass response capped at 5,000 rows">{passQuery.data.totalMatching.toLocaleString()} passes match; choose a narrower category to inspect every row.</EventMapNotice>
              ) : selection?.kind === 'pass' ? (
                <EventSelectionDetails selection={selection} matches={passQuery.data?.matches ?? {}} />
              ) : <p className="text-[9px] text-ink-dim">Click, tap or focus a pass to inspect it.</p>}
            </div>
          )}>
            <MapStage map="passes" expanded={expanded} setExpanded={setExpanded}>
              {passQuery.isLoading ? <EventMapNotice kind="loading" title="Loading pass rows" /> : passQuery.isError || !passQuery.data ? (
                <EventMapNotice kind="error" title="Pass map failed to load" onRetry={() => passQuery.refetch()} />
              ) : passQuery.data.passes.length || passQuery.data.carries.length ? (
                <PortraitPitch passes={passQuery.data.passes} carries={passQuery.data.carries} eventSelectionMode="click" selectedEventId={selection?.kind === 'pass' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} ${PASS_OUTCOMES.find(item => item.value === passOutcome)?.label.toLowerCase()} ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} pass and carry map. Attacking left to right.`} />
              ) : <EventMapNotice kind="empty" title="No passes match this category" />}
            </MapStage>
          </EventMapCard>
        ) : null}

        {profile.modules.shotMap.available ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'shots'} onExpandedChange={next => setExpanded(next ? 'shots' : null)} title="Shot map" description={profile.shots.length === 0 ? 'No shots were recorded in this scope.' : 'Select a shot to see where it was aimed in the goal.'} footer={(
            <div className="space-y-2">
              <ShotMapLegend />
              {selection?.kind === 'shot' ? <EventSelectionDetails selection={selection} matches={profile.matches} /> : <p className="text-[9px] text-ink-dim">Click, tap or focus a shot to inspect it.</p>}
            </div>
          )}>
            <MapStage map="shots" expanded={expanded} setExpanded={setExpanded}>
              {profile.shots.length ? <PortraitPitch shots={profile.shots} eventSelectionMode="click" selectedEventId={selection?.kind === 'shot' ? selection.id : null} onSelectedEventChange={setSelection} ariaLabel={`${profile.playerName} shot map. Attacking left to right.`} /> : <EventMapNotice kind="empty" title="No shots recorded" />}
            </MapStage>
          </EventMapCard>
        ) : null}

        {!isGoalkeeper && profile.modules.shotMap.available ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'zones'} onExpandedChange={next => setExpanded(next ? 'zones' : null)} title="Shooting zones" description={`Where ${profile.playerName}'s on-target shots end up in the goal, split into a 3×2 grid. Blocked and off-target shots are excluded.`} controls={(
            <PenaltyToggle value={shotPenalties} onChange={setShotPenalties} />
          )} footer={
            shotZonesQuery.data ? (
              <GoalZoneTotals variant={shotZonesQuery.data.variants[zoneVariantKey]} mode="shooter" />
            ) : null
          }>
            <MapStage map="zones" expanded={expanded} setExpanded={setExpanded}>
              <div className="w-full">
                {expanded === 'zones' && shotZonesQuery.data ? (
                  <div className="mx-auto mb-3 max-w-[860px]">
                    <GoalZoneTotals variant={shotZonesQuery.data.variants[zoneVariantKey]} mode="shooter" />
                  </div>
                ) : null}
                {shotZonesQuery.isLoading ? <EventMapNotice kind="loading" title="Loading shooting zones" /> : shotZonesQuery.isError || !shotZonesQuery.data ? (
                  <EventMapNotice kind="error" title="Shooting zones failed to load" onRetry={() => shotZonesQuery.refetch()} />
                ) : shotZonesQuery.data.shotCount === 0 ? (
                  <EventMapNotice kind="empty" title="No shots recorded in this scope" />
                ) : (
                  <GoalZoneGridView grid={shotZonesQuery.data.grid} variant={shotZonesQuery.data.variants[zoneVariantKey]} mode="shooter" />
                )}
              </div>
            </MapStage>
          </EventMapCard>
        ) : null}

        {isGoalkeeper ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'gk-zones'} onExpandedChange={next => setExpanded(next ? 'gk-zones' : null)} title="Shot-facing zones" description="Where opponents' on-target shots were aimed at this goalkeeper's goal, with save rates per zone." controls={(
            <PenaltyToggle value={shotPenalties} onChange={setShotPenalties} />
          )} footer={(
            <div className="space-y-2">
              {gkZonesQuery.data ? <GoalZoneTotals variant={gkZonesQuery.data.variants[zoneVariantKey]} mode="keeper" /> : null}
              {gkZonesQuery.data && gkZonesQuery.data.matchesExcluded > 0 ? (
                <EventMapNotice kind="sparse" title="Some matches excluded">
                  {gkZonesQuery.data.matchesIncluded} of {gkZonesQuery.data.matchesIncluded + gkZonesQuery.data.matchesExcluded} matches included — only matches with one verifiable goalkeeper are counted.
                </EventMapNotice>
              ) : null}
            </div>
          )}>
            <MapStage map="gk-zones" expanded={expanded} setExpanded={setExpanded}>
              <div className="w-full">
                {expanded === 'gk-zones' && gkZonesQuery.data ? (
                  <div className="mx-auto mb-3 max-w-[860px]">
                    <GoalZoneTotals variant={gkZonesQuery.data.variants[zoneVariantKey]} mode="keeper" />
                  </div>
                ) : null}
                {gkZonesQuery.isLoading ? <EventMapNotice kind="loading" title="Loading shot-facing zones" /> : gkZonesQuery.isError || !gkZonesQuery.data ? (
                  <EventMapNotice kind="error" title="Shot-facing zones failed to load" onRetry={() => gkZonesQuery.refetch()} />
                ) : !gkZonesQuery.data.selectedMatchIncluded ? (
                  <EventMapNotice kind="empty" title="Keeper attribution unverified for this match">
                    The selected match could not be attributed to a single goalkeeper, so it is excluded.
                  </EventMapNotice>
                ) : gkZonesQuery.data.shotsFaced === 0 ? (
                  <EventMapNotice kind="empty" title="No on-target shots faced in this scope" />
                ) : (
                  <GoalZoneGridView grid={gkZonesQuery.data.grid} variant={gkZonesQuery.data.variants[zoneVariantKey]} mode="keeper" />
                )}
              </div>
            </MapStage>
          </EventMapCard>
        ) : null}

        {locatedTouchCount > 0 || matchRef !== null ? (
          <EventMapCard className="lg:col-span-6" expanded={expanded === 'actions'} onExpandedChange={next => setExpanded(next ? 'actions' : null)} title="Touch heatmap" description="Smoothed density of located touches only, with the average touch position overlaid." footer={(
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-3 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-dim">
              <span className="inline-flex items-center gap-1.5"><span className="size-3 rounded-full bg-mint/55 blur-[2px]" aria-hidden /> Higher touch density</span>
              {profile.averageTouchLocation ? <span className="inline-flex items-center gap-1.5 text-electric"><span aria-hidden>◆</span> Average touch · {profile.averageTouchLocation.sampleSize.toLocaleString()} touches</span> : null}
              </div>
              {locatedTouchCount < 100 ? <EventMapNotice kind="sparse" title="Small located-touch sample">The heatmap is directional context, not a settled season tendency.</EventMapNotice> : null}
            </div>
          )}>
            <MapStage map="actions" expanded={expanded} setExpanded={setExpanded}>
              {locatedTouchCount ? <PortraitPitch densityCells={profile.touchGrid} densityStyle="smooth" markers={profile.averageTouchLocation ? [{ id: 'average-touch', coordinate: profile.averageTouchLocation, kind: 'jersey', ariaLabel: `Average touch location from ${profile.averageTouchLocation.sampleSize} located touches`, label: 'Avg touch', tone: 'accent' }] : []} ariaLabel={`${profile.playerName} touch-only heatmap with average touch overlay. Attacking left to right.`} /> : <EventMapNotice kind="empty" title="No located touches recorded" />}
            </MapStage>
          </EventMapCard>
        ) : null}
      </div>
    </section>
  )
}
