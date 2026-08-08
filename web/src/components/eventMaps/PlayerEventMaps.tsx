import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchPlayerEventProfile, fetchPlayerPassMap } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type {
  PlayerEventProfilePayload,
  PlayerPassFilter,
  PlayerPassMapPayload,
} from '../../types/eventMaps'
import { cn } from '../../lib/utils'
import { PortraitPitch } from './PortraitPitch'
import {
  EventCoverage,
  EventMapNotice,
  EventMapViewTabs,
  EventMetricStrip,
  EventPitchStage,
  EventSelectionDetails,
} from './EventMapUi'

type PlayerMapView = 'passes' | 'shots' | 'actions' | 'touch'

const PLAYER_VIEWS = [
  { value: 'passes', label: 'Passes' },
  { value: 'shots', label: 'Shots' },
  { value: 'actions', label: 'Actions' },
  { value: 'touch', label: 'Avg touch' },
] satisfies Array<{ value: PlayerMapView; label: string }>

const PASS_FILTERS: Array<{ value: PlayerPassFilter; label: string }> = [
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

type PlayerEventProfileLoader = (
  playerId: number,
  competition: string,
  season: string,
  teamId?: number | null,
) => Promise<PlayerEventProfilePayload>

type PlayerPassMapLoader = (
  playerId: number,
  competition: string,
  season: string,
  filter: PlayerPassFilter,
  teamId?: number | null,
) => Promise<PlayerPassMapPayload>

export function PlayerEventMaps({
  playerId,
  competition,
  season,
  teams,
  loadProfile = fetchPlayerEventProfile,
  loadPasses = fetchPlayerPassMap,
}: {
  playerId: number
  competition: string
  season: string
  teams: PlayerEventMapTeam[]
  loadProfile?: PlayerEventProfileLoader
  loadPasses?: PlayerPassMapLoader
}) {
  const [view, setView] = useState<PlayerMapView>('passes')
  const [passFilter, setPassFilter] = useState<PlayerPassFilter>('completed')
  const [teamId, setTeamId] = useState<number | null>(null)
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [expanded, setExpanded] = useState(false)

  const profileQuery = useQuery({
    queryKey: ['player-event-profile', playerId, competition, season, teamId],
    queryFn: () => loadProfile(playerId, competition, season, teamId),
    staleTime: 10 * 60 * 1000,
  })

  const passQuery = useQuery({
    queryKey: ['player-event-passes', playerId, competition, season, teamId, passFilter],
    queryFn: () => loadPasses(playerId, competition, season, passFilter, teamId),
    enabled: view === 'passes' && profileQuery.data?.modules.passMap.available === true,
    staleTime: 10 * 60 * 1000,
  })

  const profile = profileQuery.data
  const selectedMatches = view === 'passes' ? passQuery.data?.matches ?? {} : profile?.matches ?? {}
  const availableViews = useMemo(
    () => PLAYER_VIEWS.map(option => ({
      ...option,
      disabled:
        option.value === 'passes'
          ? profile?.modules.passMap.available === false
          : option.value === 'shots'
            ? profile?.modules.shotMap.available === false
            : option.value === 'actions'
              ? profile?.modules.actionGrid.available === false
              : profile?.averageTouchLocation == null,
    })),
    [profile],
  )

  if (profileQuery.isLoading) {
    return <EventMapNotice kind="loading" title="Loading player event profile" />
  }
  if (profileQuery.isError || !profile) {
    return (
      <EventMapNotice
        kind="error"
        title="Player event profile failed to load"
        onRetry={() => profileQuery.refetch()}
      >
        {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
      </EventMapNotice>
    )
  }

  const moduleState =
    view === 'passes'
      ? profile.modules.passMap
      : view === 'shots'
        ? profile.modules.shotMap
        : profile.modules.actionGrid

  const renderPitch = () => {
    if (view === 'passes') {
      if (passQuery.isLoading) {
        return <EventMapNotice kind="loading" title="Loading pass rows" />
      }
      if (passQuery.isError || !passQuery.data) {
        return (
          <EventMapNotice kind="error" title="Pass map failed to load" onRetry={() => passQuery.refetch()}>
            {passQuery.error?.message ?? 'Pass rows are temporarily unavailable.'}
          </EventMapNotice>
        )
      }
      if (!passQuery.data.passes.length) {
        return (
          <EventMapNotice kind="empty" title="No passes match this filter">
            Choose another pass type or season/team split.
          </EventMapNotice>
        )
      }
      return (
        <PortraitPitch
          passes={passQuery.data.passes}
          selectedEventId={selection?.id ?? null}
          onSelectedEventChange={setSelection}
          ariaLabel={`${profile.playerName} ${PASS_FILTERS.find(item => item.value === passFilter)?.label.toLowerCase()} pass map. Attacking bottom to top.`}
        />
      )
    }
    if (view === 'shots') {
      if (!profile.shots.length) {
        return <EventMapNotice kind="empty" title="No shots recorded for this scope" />
      }
      return (
        <PortraitPitch
          shots={profile.shots}
          selectedEventId={selection?.id ?? null}
          onSelectedEventChange={setSelection}
          ariaLabel={`${profile.playerName} shot map. Attacking bottom to top.`}
        />
      )
    }
    if (view === 'actions') {
      if (!profile.actionGrid.some(cell => cell.rawCount > 0)) {
        return <EventMapNotice kind="empty" title="No located actions recorded for this scope" />
      }
      return (
        <PortraitPitch
          densityCells={profile.actionGrid}
          ariaLabel={`${profile.playerName} action-density share map. Attacking bottom to top.`}
        />
      )
    }
    if (!profile.averageTouchLocation) {
      return <EventMapNotice kind="empty" title="No average touch location is available" />
    }
    return (
      <PortraitPitch
        markers={[{
          id: 'average-touch',
          coordinate: profile.averageTouchLocation,
          kind: 'jersey',
          ariaLabel: `Average touch location from ${profile.averageTouchLocation.sampleSize} touches`,
          label: `${profile.averageTouchLocation.sampleSize.toLocaleString()} touches`,
          tone: 'accent',
        }]}
        ariaLabel={`${profile.playerName} average touch location. Attacking bottom to top.`}
      />
    )
  }

  return (
    <section aria-labelledby="player-event-maps-heading" className="relative">
      <div className="mb-4 flex flex-col gap-3 border-b border-line-bright pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-electric/80">
            WhoScored season events
          </p>
          <h2 id="player-event-maps-heading" className="text-[20px] font-black tracking-tight text-ink">
            Event Maps
          </h2>
          <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-ink-dim">
            Portrait maps share one direction: the player&apos;s team attacks from bottom to top.
          </p>
        </div>
        {teams.length > 1 ? (
          <label className="flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.14em] text-ink-dim">
            Team split
            <select
              value={teamId ?? ''}
              onChange={event => {
                setSelection(null)
                setTeamId(event.target.value ? Number(event.target.value) : null)
              }}
              className="h-9 min-w-40 border border-control-border bg-panel px-3 text-[10px] text-control-fg outline-none hover:border-electric focus:border-electric"
            >
              <option value="">Season total</option>
              {teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}
            </select>
          </label>
        ) : null}
      </div>

      <div className="mb-4 flex flex-col gap-3">
        <EventMapViewTabs
          value={view}
          options={availableViews}
          onChange={nextView => {
            setSelection(null)
            setView(nextView)
          }}
          label="Player event map"
        />
        {view === 'passes' ? (
          <div className="flex gap-1.5 overflow-x-auto pb-1" aria-label="Pass filter">
            {PASS_FILTERS.map(filter => (
              <button
                key={filter.value}
                type="button"
                onClick={() => {
                  setSelection(null)
                  setPassFilter(filter.value)
                }}
                className={cn(
                  'h-8 shrink-0 border px-2.5 text-[9px] font-bold uppercase tracking-[0.11em] transition-colors',
                  filter.value === passFilter
                    ? 'border-electric/50 bg-electric/12 text-electric'
                    : 'border-control-border text-control-fg hover:border-electric hover:text-ink',
                )}
              >
                {filter.label}
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(250px,0.42fr)] lg:items-start">
        <div className="min-w-0">
          {!moduleState.available && view !== 'touch' ? (
            <EventMapNotice kind="unavailable" title="This map is unavailable for the selected scope" />
          ) : (
            <EventPitchStage expanded={expanded} onExpandedChange={setExpanded}>
              {renderPitch()}
            </EventPitchStage>
          )}
        </div>
        <aside className="flex min-w-0 flex-col gap-3">
          <EventMetricStrip metrics={[
            { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
            { label: 'Shots', value: profile.summary.shots?.toLocaleString() ?? '—' },
            { label: 'Actions', value: profile.summary.valid_location_actions?.toLocaleString() ?? '—' },
          ]} />
          <EventCoverage coverage={profile.coverage} />
          {moduleState.sparse && view !== 'touch' ? (
            <EventMapNotice kind="sparse" title="Small event sample">
              Treat the visible pattern as directional context, not a settled season tendency.
            </EventMapNotice>
          ) : null}
          {view === 'passes' && passQuery.data?.truncated ? (
            <EventMapNotice kind="truncated" title="Pass response capped at 5,000 rows">
              {passQuery.data.totalMatching.toLocaleString()} passes match. Choose a narrower filter or team split to inspect every row.
            </EventMapNotice>
          ) : null}
          {view === 'touch' && profile.averageTouchLocation ? (
            <div className="border border-line-bright bg-panel px-4 py-3">
              <p className="text-[9px] font-bold uppercase tracking-[0.15em] text-electric">Sample context</p>
              <p className="mt-2 text-[12px] leading-relaxed text-ink">
                Mean location across <span className="font-mono text-electric">{profile.averageTouchLocation.sampleSize.toLocaleString()}</span> located touches.
              </p>
            </div>
          ) : null}
          {(view === 'passes' || view === 'shots') ? (
            <EventSelectionDetails selection={selection} matches={selectedMatches} />
          ) : null}
        </aside>
      </div>
    </section>
  )
}
