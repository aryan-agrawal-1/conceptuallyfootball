import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { fetchTeamEventProfile } from '../../lib/eventMaps/api'
import type { SelectablePitchEvent } from '../../lib/eventMaps/selection'
import type { TeamPassFlow } from '../../types/eventMaps'
import { PortraitPitch } from './PortraitPitch'
import {
  EventCoverage,
  EventMapNotice,
  EventMapViewTabs,
  EventMetricStrip,
  EventPitchStage,
  EventSelectionDetails,
} from './EventMapUi'

type TeamMapView = 'flow' | 'shots_for' | 'shots_against' | 'territory' | 'territory_against'

const TEAM_VIEWS = [
  { value: 'flow', label: 'Pass flow' },
  { value: 'shots_for', label: 'Shots for' },
  { value: 'shots_against', label: 'Shots against' },
  { value: 'territory', label: 'Territory' },
  { value: 'territory_against', label: 'Opp. territory' },
] satisfies Array<{ value: TeamMapView; label: string }>

function zoneLabel(zone: TeamPassFlow['startZone']) {
  const lanes = ['Left', 'Centre', 'Right']
  return `${lanes[zone.row]} ${zone.column + 1}`
}

export function TeamEventMaps({
  teamId,
  competition,
  season,
}: {
  teamId: number
  competition: string
  season: string
}) {
  const [view, setView] = useState<TeamMapView>('flow')
  const [selection, setSelection] = useState<SelectablePitchEvent | null>(null)
  const [showAllFlows, setShowAllFlows] = useState(false)
  const [expanded, setExpanded] = useState(false)
  const profileQuery = useQuery({
    queryKey: ['team-event-profile', teamId, competition, season],
    queryFn: () => fetchTeamEventProfile(teamId, competition, season),
    staleTime: 10 * 60 * 1000,
  })

  const profile = profileQuery.data
  const nonzeroFlows = useMemo(
    () => profile?.passFlows.filter(flow => flow.completedCount > 0) ?? [],
    [profile],
  )
  const visibleThreshold = useMemo(() => {
    let maximum = 0
    for (const flow of nonzeroFlows) maximum = Math.max(maximum, flow.completedCount)
    return Math.max(8, Math.ceil(maximum * 0.12))
  }, [nonzeroFlows])
  const visibleFlows = useMemo(
    () => showAllFlows
      ? nonzeroFlows
      : nonzeroFlows.filter(flow => flow.completedCount >= visibleThreshold),
    [nonzeroFlows, showAllFlows, visibleThreshold],
  )

  if (profileQuery.isLoading) {
    return <EventMapNotice kind="loading" title="Loading team event profile" />
  }
  if (profileQuery.isError || !profile) {
    return (
      <EventMapNotice kind="error" title="Team event profile failed to load" onRetry={() => profileQuery.refetch()}>
        {profileQuery.error?.message ?? 'The event-profile service returned no data.'}
      </EventMapNotice>
    )
  }

  const shots = view === 'shots_against'
    ? profile.shots.filter(shot => shot.perspective === 'against')
    : profile.shots.filter(shot => shot.perspective === 'for')
  const territory = view === 'territory_against'
    ? profile.opponentActionTerritory
    : profile.actionTerritory
  const sparse = view === 'flow'
    ? nonzeroFlows.reduce((total, flow) => total + flow.completedCount, 0) < 100
    : view === 'shots_for' || view === 'shots_against'
      ? shots.length < 5
      : territory.reduce((total, cell) => total + cell.rawCount, 0) < 100

  const renderPitch = () => {
    if (view === 'flow') {
      if (!visibleFlows.length) return <EventMapNotice kind="empty" title="No completed pass flows recorded" />
      return (
        <PortraitPitch
          flows={visibleFlows}
          ariaLabel={`${profile.teamName} completed pass flow. Acting team attacks bottom to top.`}
        />
      )
    }
    if (view === 'shots_for' || view === 'shots_against') {
      if (!shots.length) return <EventMapNotice kind="empty" title={`No ${view === 'shots_against' ? 'opponent ' : ''}shots recorded`} />
      return (
        <PortraitPitch
          shots={shots}
          selectedEventId={selection?.id ?? null}
          onSelectedEventChange={setSelection}
          ariaLabel={`${profile.teamName} ${view === 'shots_against' ? 'shots against' : 'shots for'} map. Acting team attacks bottom to top.`}
        />
      )
    }
    if (!territory.some(cell => cell.rawCount > 0)) {
      return <EventMapNotice kind="empty" title="No located actions recorded for this territory map" />
    }
    return (
      <PortraitPitch
        densityCells={territory}
        layerOptions={{ densityColor: view === 'territory_against' ? '#EF5C66' : '#1FD17C' }}
        ariaLabel={`${profile.teamName} ${view === 'territory_against' ? 'opponent ' : ''}action-territory share map. Acting team attacks bottom to top.`}
      />
    )
  }

  return (
    <section aria-labelledby="team-event-maps-heading">
      <div className="mb-4 border-b border-line-bright pb-4">
        <p className="mb-1 font-mono text-[9px] uppercase tracking-[0.2em] text-electric/80">
          WhoScored season events
        </p>
        <h2 id="team-event-maps-heading" className="text-[20px] font-black tracking-tight text-ink">
          Event Maps
        </h2>
        <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-ink-dim">
          Flow, shooting and territory views use the same portrait orientation on every screen.
        </p>
      </div>

      <div className="mb-4 flex flex-col gap-3">
        <EventMapViewTabs
          value={view}
          options={TEAM_VIEWS}
          onChange={nextView => {
            setSelection(null)
            setView(nextView)
          }}
          label="Team event map"
        />
        {view === 'flow' ? (
          <div className="flex flex-wrap items-center justify-between gap-2 border border-line-bright bg-panel px-3 py-2">
            <p className="text-[9px] leading-relaxed text-ink-dim">
              {showAllFlows
                ? `Showing all ${nonzeroFlows.length} non-zero edges.`
                : `Showing ${visibleFlows.length} edges with at least ${visibleThreshold} completed passes.`}
            </p>
            <button
              type="button"
              onClick={() => setShowAllFlows(current => !current)}
              className="text-[9px] font-bold uppercase tracking-[0.13em] text-electric hover:text-ink"
            >
              {showAllFlows ? 'Apply visible threshold' : 'Show every edge'}
            </button>
          </div>
        ) : null}
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(250px,0.42fr)] lg:items-start">
        <div className="min-w-0">
          <EventPitchStage expanded={expanded} onExpandedChange={setExpanded}>
            {renderPitch()}
          </EventPitchStage>
        </div>
        <aside className="flex min-w-0 flex-col gap-3">
          <EventMetricStrip metrics={[
            { label: 'Passes', value: profile.summary.pass_attempts?.toLocaleString() ?? '—' },
            { label: 'Shots for', value: profile.summary.shots_for?.toLocaleString() ?? '—' },
            { label: 'Shots against', value: profile.summary.shots_against?.toLocaleString() ?? '—' },
          ]} />
          <EventCoverage coverage={profile.coverage} />
          {sparse ? (
            <EventMapNotice kind="sparse" title="Small event sample">
              Treat the visible pattern as directional context, not a settled season tendency.
            </EventMapNotice>
          ) : null}
          {(view === 'shots_for' || view === 'shots_against') ? (
            <EventSelectionDetails selection={selection} matches={profile.matches} />
          ) : null}
          {view === 'flow' ? (
            <details className="border border-line-bright bg-panel">
              <summary className="cursor-pointer px-4 py-3 text-[9px] font-bold uppercase tracking-[0.14em] text-control-fg hover:text-ink">
                Inspect complete 5×3 matrix
              </summary>
              <div className="max-h-72 overflow-auto border-t border-line-bright">
                <table className="w-full border-collapse text-left text-[9px]">
                  <thead className="sticky top-0 bg-raised text-ink-dim">
                    <tr>
                      <th className="px-3 py-2 font-bold uppercase tracking-[0.1em]">Route</th>
                      <th className="px-3 py-2 text-right font-bold uppercase tracking-[0.1em]">Cmp</th>
                      <th className="px-3 py-2 text-right font-bold uppercase tracking-[0.1em]">Att</th>
                    </tr>
                  </thead>
                  <tbody>
                    {profile.passFlows.map(flow => (
                      <tr key={flow.id} className="border-t border-line/80 text-ink-dim">
                        <td className="px-3 py-2">{zoneLabel(flow.startZone)} → {zoneLabel(flow.endZone)}</td>
                        <td className="px-3 py-2 text-right font-mono text-ink">{flow.completedCount}</td>
                        <td className="px-3 py-2 text-right font-mono">{flow.attemptedCount}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          ) : null}
        </aside>
      </div>
    </section>
  )
}
