import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQueries } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { fetchPlayerDetail } from '../lib/api'
import { useSearchPaletteIndex } from '../hooks/useSearchPaletteIndex'
import { useScope } from '../context/ScopeContext'
import type { PlayerDetailResponse, PlayerRow, PositionGroup } from '../types/api'
import {
  parsePlayerRefsParam,
  parseRateModeParam,
  parseStatsParam,
  playerRowToScopedRef,
  scopedPlayerToken,
  type ScopedPlayerRef,
} from '../lib/comparisonUrl'
import { resolveComparisonStatKeys } from '../lib/comparisonStatKeys'
import {
  COMPARISON_MIN_MINUTES_WARNING,
  COMPARISON_STAT_MAX,
  COMPARISON_STAT_MIN,
} from '../lib/comparisonConstants'
import type { ProfileRateMode } from '../lib/profileMetrics'
import { HudActionButton, HudFrame, HudLabel } from '../components/hud/Hud'
import { ProfileRateToggle } from '../components/profile/ProfileRateToggle'
import { CompareRadarChart } from '../components/comparisons/CompareRadarChart'
import { CompareStatAxisPicker } from '../components/comparisons/CompareStatAxisPicker'
import { CompareStatTable } from '../components/comparisons/CompareStatTable'
import { ComparePlayerPicker } from '../components/comparisons/ComparePlayerPicker'
import { ProfileEligibilityBanner } from '../components/profile/ProfileEligibilityBanner'
import { ChartShareCard } from '../components/visualizer/ChartShareCard'
import { scopeIncludesMembership } from '../lib/scopeMembership'

const POSITION_COHORT_LABEL: Record<PositionGroup, string> = {
  FWD: 'Forwards',
  MID: 'Midfielders',
  DEF: 'Defenders',
  GK: 'Goalkeepers',
  UNK: 'Players',
}

type PickerState = { kind: 'add' } | { kind: 'replace'; index: number }

function rowToken(row: PlayerRow): string {
  return scopedPlayerToken(playerRowToScopedRef(row))
}

function refsEqual(left: ScopedPlayerRef[], right: ScopedPlayerRef[]): boolean {
  return left.length === right.length && left.every((ref, index) => scopedPlayerToken(ref) === scopedPlayerToken(right[index]))
}

export function Comparisons() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [picker, setPicker] = useState<PickerState | null>(null)
  const [hoveredStatIndex, setHoveredStatIndex] = useState<number | null>(null)
  const [lockedStatIndex, setLockedStatIndex] = useState<number | null>(null)
  const [cohortConfirm, setCohortConfirm] = useState<PlayerRow | null>(null)
  const { scope, scopeLabel, buildScopedPath } = useScope()

  const parsedPlayerRefs = useMemo(() => parsePlayerRefsParam(searchParams.get('players')), [searchParams])
  const urlStats = useMemo(() => parseStatsParam(searchParams.get('stats')), [searchParams])
  const rateMode: ProfileRateMode = useMemo(
    () => parseRateModeParam(searchParams.get('mode')),
    [searchParams],
  )

  const { playersSorted, isLoading: indexLoading, isError: indexError } = useSearchPaletteIndex(true)

  const competition = scope.competition
  const isAggregateScope = competition === 'BIG5' || competition === 'ALL'

  const playerRefs = useMemo(
    () =>
      parsedPlayerRefs.filter(ref =>
        scopeIncludesMembership(scope, {
          competition: ref.competition,
          season: ref.season,
        }),
      ),
    [parsedPlayerRefs, scope],
  )

  const playerTokens = useMemo(() => playerRefs.map(scopedPlayerToken), [playerRefs])

  useEffect(() => {
    if (refsEqual(parsedPlayerRefs, playerRefs)) return
    setSearchParams(
      prev => {
        const p = new URLSearchParams(prev)
        if (playerRefs.length) p.set('players', playerRefs.map(scopedPlayerToken).join(','))
        else p.delete('players')
        return p
      },
      { replace: true },
    )
  }, [parsedPlayerRefs, playerRefs, setSearchParams])

  const detailQueries = useQueries({
    queries: playerRefs.map(ref => {
      return {
        queryKey: [
          'player-detail',
          ref.competition,
          ref.season,
          ref.id,
          isAggregateScope ? competition : null,
        ],
        queryFn: () => {
          return fetchPlayerDetail(ref.id, {
            competition: ref.competition,
            season: ref.season,
            include: isAggregateScope ? 'meta,scope_percentiles' : 'meta',
            percentile_scope: isAggregateScope ? competition : undefined,
          })
        },
        enabled: Number.isFinite(ref.id) && ref.id > 0,
      }
    }),
  })

  const detailsOrdered = useMemo((): Array<PlayerDetailResponse | undefined> => {
    return playerRefs.map((_, i) => detailQueries[i]?.data as PlayerDetailResponse | undefined)
  }, [playerRefs, detailQueries])

  const meta = useMemo(() => {
    for (const d of detailsOrdered) {
      if (d?.meta) return d.meta
    }
    return undefined
  }, [detailsOrdered])

  const anchorRow: PlayerRow | null = useMemo(() => {
    const fromDetail = detailsOrdered[0]
    if (fromDetail) return fromDetail
    const first = playerRefs[0]
    if (!first) return null
    return playersSorted.find(p => rowToken(p) === scopedPlayerToken(first)) ?? null
  }, [detailsOrdered, playerRefs, playersSorted])

  const cohortPosition: PositionGroup | null = anchorRow?.position_group ?? null

  const pickerLockPosition: PositionGroup | null =
    playerRefs.length === 0 ? null : cohortPosition

  const pickerTitle =
    picker?.kind === 'replace'
      ? 'Replace player'
      : playerRefs.length === 0
        ? 'Select first player'
        : 'Add player'

  const statKeys = useMemo(() => {
    if (!meta || !cohortPosition) return []
    return resolveComparisonStatKeys(urlStats, cohortPosition, meta)
  }, [urlStats, cohortPosition, meta])

  const radarPlayers = useMemo(() => {
    return playerRefs
      .map((_, i) => {
        const d = detailsOrdered[i]
        return d ? { row: d, slot: i as 0 | 1 | 2 } : null
      })
      .filter((x): x is { row: PlayerDetailResponse; slot: 0 | 1 | 2 } => x != null)
  }, [playerRefs, detailsOrdered])

  const detailsLoading = detailQueries.some(q => q.isLoading)
  const detailsError = detailQueries.some(q => q.isError)

  const anyLowMinutesOrIneligible = useMemo(() => {
    return radarPlayers.some(
      p => p.row.minutes < COMPARISON_MIN_MINUTES_WARNING || !p.row.eligibility.percentiles_eligible,
    )
  }, [radarPlayers])

  const percentileMapForRow = useCallback(
    (row: PlayerRow) => (isAggregateScope ? row.scope_percentiles ?? {} : row.percentiles),
    [isAggregateScope],
  )

  const writeParams = useCallback(
    (next: { playerRefs: ScopedPlayerRef[]; stats: string[] | null; mode: ProfileRateMode }) => {
      setSearchParams(
        prev => {
          const p = new URLSearchParams(prev)
          if (next.playerRefs.length) p.set('players', next.playerRefs.map(scopedPlayerToken).join(','))
          else p.delete('players')
          if (next.stats && next.stats.length) p.set('stats', next.stats.join(','))
          else p.delete('stats')
          if (next.mode === 'full') p.set('mode', 'full')
          else p.delete('mode')
          return p
        },
        { replace: true },
      )
    },
    [setSearchParams],
  )

  useEffect(() => {
    if (!cohortPosition || radarPlayers.length <= 1) return
    const nextRefs = playerRefs.filter((_, index) => {
      const row = detailsOrdered[index]
      return !row || row.position_group === cohortPosition
    })
    if (refsEqual(nextRefs, playerRefs)) return
    writeParams({ playerRefs: nextRefs, stats: urlStats, mode: rateMode })
  }, [cohortPosition, detailsOrdered, playerRefs, radarPlayers.length, rateMode, urlStats, writeParams])

  const setRateMode = useCallback(
    (mode: ProfileRateMode) => {
      writeParams({ playerRefs, stats: urlStats, mode })
    },
    [writeParams, playerRefs, urlStats],
  )

  const setStatKeys = useCallback(
    (keys: string[]) => {
      const trimmed = keys.slice(0, COMPARISON_STAT_MAX)
      if (trimmed.length < COMPARISON_STAT_MIN) return
      writeParams({ playerRefs, stats: trimmed, mode: rateMode })
    },
    [writeParams, playerRefs, rateMode],
  )

  const commitPlayerRefs = useCallback(
    (refs: ScopedPlayerRef[], opts?: { clearStats?: boolean }) => {
      writeParams({
        playerRefs: refs.slice(0, 3),
        stats: opts?.clearStats ? null : urlStats,
        mode: rateMode,
      })
      setLockedStatIndex(null)
      setHoveredStatIndex(null)
    },
    [writeParams, urlStats, rateMode],
  )

  function tryPickPlayer(row: PlayerRow) {
    if (!picker) return

    if (picker.kind === 'add') {
      if (playerRefs.length >= 3) return
      if (playerRefs.length === 0) {
        commitPlayerRefs([playerRowToScopedRef(row)])
        setPicker(null)
        return
      }
      const anchor = anchorRow
      if (!anchor || row.position_group !== anchor.position_group) return
      commitPlayerRefs([...playerRefs, playerRowToScopedRef(row)])
      setPicker(null)
      return
    }

    const idx = picker.index
    const next = [...playerRefs]
    const oldAnchor = detailsOrdered[0] ?? anchorRow

    if (
      idx === 0 &&
      playerRefs.length > 1 &&
      oldAnchor &&
      row.position_group !== oldAnchor.position_group
    ) {
      setCohortConfirm(row)
      setPicker(null)
      return
    }

    next[idx] = playerRowToScopedRef(row)
    const clearStats = Boolean(
      idx === 0 && oldAnchor && row.position_group !== oldAnchor.position_group,
    )
    commitPlayerRefs(next, { clearStats })
    setPicker(null)
  }

  function confirmCohortResetPlayer() {
    if (!cohortConfirm) return
    commitPlayerRefs([playerRowToScopedRef(cohortConfirm)], { clearStats: true })
    setCohortConfirm(null)
  }

  function removePlayerAt(index: number) {
    const next = playerRefs.filter((_, i) => i !== index)
    commitPlayerRefs(next, { clearStats: next.length === 0 })
  }

  const excludeTokens = useMemo(() => new Set(playerTokens), [playerTokens])

  const empty = playerRefs.length === 0
  const compareTitle = useMemo(() => {
    if (!radarPlayers.length) return 'Comparisons · Radar'
    const names = radarPlayers.map(player => player.row.canonical_player_name)
    if (names.length === 1) return `${names[0]} · Radar profile`
    if (names.length === 2) return `${names[0]} vs ${names[1]}`
    return `${names[0]} vs ${names[1]} vs ${names[2]}`
  }, [radarPlayers])
  const compareSubtitle = useMemo(() => {
    const cohort = cohortPosition ? POSITION_COHORT_LABEL[cohortPosition] : 'Players'
    return `${scopeLabel} · Percentiles vs ${cohort.toLowerCase()} · ${rateMode === 'per90' ? 'per 90' : 'season'} · ${statKeys.length} axes`
  }, [cohortPosition, rateMode, scopeLabel, statKeys.length])

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:px-10 lg:pb-20">
      <div className="mb-6 flex flex-col gap-4 sm:mb-8 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-[30px] sm:text-[36px] font-black tracking-tight text-ink leading-none mb-2">
            Comparisons
          </h1>
          <p className="text-[12px] text-ink-muted font-mono tabular-nums">
            {scope.competition} · {scope.season}
            {cohortPosition && (
              <>
                {' '}
                ·{' '}
                <span className="text-ink">{POSITION_COHORT_LABEL[cohortPosition]}</span>
              </>
            )}
          </p>
          <p className="mt-2 text-[11px] text-ink-dim leading-relaxed max-w-xl">
            Choose a player to start a same-position comparison. The first player sets the position group; add up to two
            more. Chart nodes use percentiles against the selected scope and position.
          </p>
        </div>
        <ProfileRateToggle value={rateMode} onChange={setRateMode} />
      </div>

      {anyLowMinutesOrIneligible && !empty && (
        <div className="mb-6">
          <HudFrame
            className="w-full border-ember/30"
            header={<span className="text-ember/90">Low sample // Readout</span>}
          >
            <p className="p-4 text-[12px] text-ink-dim leading-relaxed">
              One or more selected players are below {COMPARISON_MIN_MINUTES_WARNING} minutes or not percentile-eligible.
              Raw values and the table still update; the radar omits shapes without eligible percentiles.
            </p>
          </HudFrame>
        </div>
      )}

      {empty ? (
        <HudFrame className="w-full max-w-lg" header={<span>Start // Cohort</span>}>
          <div className="p-6 flex flex-col gap-4">
            <HudLabel>No players selected</HudLabel>
            <p className="text-[13px] text-ink-muted leading-relaxed">
              Select the first player to lock a position group and load default stat axes.
            </p>
            <HudActionButton type="button" onClick={() => setPicker({ kind: 'add' })}>
              Select first player
            </HudActionButton>
          </div>
        </HudFrame>
      ) : (
        <div className="flex flex-col gap-6">
          <HudFrame header={<span>Selected // Roster</span>} className="w-full">
            <div className="flex flex-col gap-4 p-3 sm:p-4">
              <div className="flex flex-col lg:flex-row gap-4 lg:items-start lg:justify-between">
                <div className="grid w-full grid-cols-1 gap-3 sm:flex sm:flex-wrap">
                  {playerRefs.map((ref, index) => {
                    const d = detailsOrdered[index]
                    const label = d?.canonical_player_name ?? `Player ${ref.id}`
                    const team = d?.canonical_team_name
                    const mins = d?.minutes
                    const low =
                      d &&
                      (d.minutes < COMPARISON_MIN_MINUTES_WARNING ||
                        !d.eligibility.percentiles_eligible)
                    return (
                      <div
                        key={`${scopedPlayerToken(ref)}-${index}`}
                        className="relative min-w-0 border border-electric/25 bg-panel/50 px-3 py-2.5 sm:min-w-[200px] sm:max-w-[280px]"
                      >
                        <div className="flex items-start justify-between gap-2 mb-1">
                          <div className="min-w-0">
                            <Link
                              to={buildScopedPath(`/player/${ref.id}`, { competition: ref.competition, season: ref.season })}
                              className="text-[13px] font-semibold text-ink truncate block hover:text-electric/90 hover:underline"
                            >
                              {label}
                            </Link>
                            {team && (
                              <p className="text-[11px] text-ink-muted truncate">
                                {d?.canonical_team_id != null ? (
                                  <Link
                                    className="hover:text-electric hover:underline"
                                    to={buildScopedPath(`/team/${d.canonical_team_id}`, {
                                      competition: d.competition_code,
                                      season: d.season_label,
                                    })}
                                  >
                                    {team}
                                  </Link>
                                ) : (
                                  team
                                )}
                                {d && <span className="text-ink-dim"> · {d.competition_code}</span>}
                              </p>
                            )}
                          </div>
                          <span className="shrink-0 text-[10px] font-mono text-ink-muted tabular-nums">
                            {mins != null ? `${mins.toLocaleString()}′` : '…'}
                          </span>
                        </div>
                        {low && d && (
                          <div className="mt-2 space-y-2">
                            {!d.eligibility.percentiles_eligible && (
                              <ProfileEligibilityBanner
                                reason={d.eligibility.percentiles_ineligibility_reason}
                              />
                            )}
                            {d.minutes < COMPARISON_MIN_MINUTES_WARNING &&
                              d.eligibility.percentiles_eligible && (
                                <p className="text-[10px] text-ember/90 uppercase tracking-wide">
                                  Below {COMPARISON_MIN_MINUTES_WARNING} minutes — interpret percentiles cautiously.
                                </p>
                              )}
                          </div>
                        )}
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            className="text-[10px] uppercase tracking-widest text-electric/80 hover:text-electric border border-electric/20 px-2 py-1"
                            onClick={() => setPicker({ kind: 'replace', index })}
                          >
                            Change
                          </button>
                          <button
                            type="button"
                            className="text-[10px] uppercase tracking-widest text-ink-muted hover:text-ember border border-electric/15 px-2 py-1"
                            onClick={() => removePlayerAt(index)}
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                    )
                  })}
                  {playerRefs.length > 0 && playerRefs.length < 3 && anchorRow && (
                    <button
                      type="button"
                      onClick={() => setPicker({ kind: 'add' })}
                      className="min-h-[72px] min-w-0 border border-dashed border-electric/30 px-3 text-[11px] uppercase tracking-[0.2em] text-electric/70 hover:border-electric/50 hover:text-electric sm:min-h-[96px] sm:min-w-[160px]"
                    >
                      Add player
                    </button>
                  )}
                </div>
                {detailsLoading && (
                  <div className="flex items-center gap-2 text-ink-muted text-[12px]">
                    <Loader2 className="size-4 animate-spin text-electric" />
                    Loading player rows…
                  </div>
                )}
                {detailsError && (
                  <p className="text-[12px] text-ember">Could not load one or more players.</p>
                )}
              </div>
            </div>
          </HudFrame>

          {meta && cohortPosition && statKeys.length >= COMPARISON_STAT_MIN && (
            <>
              <HudFrame
                header={<span>Radar // Percentile overlay</span>}
                className="w-full"
                footer={
                  <span className="text-ink-muted normal-case tracking-normal text-[10px]">
                    Click an axis label to lock a stat; hover nodes for a quick readout. Locked stat highlights the table
                    row.
                  </span>
                }
              >
                <div className="flex flex-col items-start gap-5 p-3 sm:p-4 xl:flex-row xl:gap-8">
                  <div className="flex-1 flex flex-col gap-4 justify-center w-full min-w-0">
                    <div className="flex justify-end">
                      <ChartShareCard
                        title={compareTitle}
                        subtitle={compareSubtitle}
                        contextLabel="Comparisons · Radar"
                        fileName={compareTitle}
                        aspect="square"
                        renderContent={({ exportMode }) => (
                          <CompareRadarChart
                            metricKeys={statKeys}
                            players={radarPlayers}
                            meta={meta}
                            rateMode={rateMode}
                            hoveredStatIndex={hoveredStatIndex}
                            lockedStatIndex={lockedStatIndex}
                            onHoverStat={setHoveredStatIndex}
                            onClickStat={setLockedStatIndex}
                            percentileMapForRow={percentileMapForRow}
                            exportMode={exportMode}
                          />
                        )}
                      />
                    </div>
                    <div className="flex justify-center w-full min-w-0">
                      <CompareRadarChart
                        metricKeys={statKeys}
                        players={radarPlayers}
                        meta={meta}
                        rateMode={rateMode}
                        hoveredStatIndex={hoveredStatIndex}
                        lockedStatIndex={lockedStatIndex}
                        onHoverStat={setHoveredStatIndex}
                        onClickStat={setLockedStatIndex}
                        percentileMapForRow={percentileMapForRow}
                      />
                    </div>
                  </div>
                  <CompareStatAxisPicker
                    meta={meta}
                    positionGroup={cohortPosition}
                    selectedKeys={statKeys}
                    onChangeKeys={setStatKeys}
                  />
                </div>
              </HudFrame>

              <HudFrame header={<span>Table // Values</span>} className="w-full">
                <div className="p-4">
                  <CompareStatTable
                    metricKeys={statKeys}
                    players={radarPlayers}
                    meta={meta}
                    rateMode={rateMode}
                    lockedStatIndex={lockedStatIndex}
                    hoveredStatIndex={hoveredStatIndex}
                    percentileMapForRow={percentileMapForRow}
                  />
                </div>
              </HudFrame>
            </>
          )}
        </div>
      )}

      <ComparePlayerPicker
        open={picker != null}
        title={pickerTitle}
        lockPosition={pickerLockPosition}
        excludeTokens={excludeTokens}
        rows={playersSorted}
        isLoading={indexLoading}
        isError={indexError}
        onClose={() => setPicker(null)}
        onPick={tryPickPlayer}
      />

      {cohortConfirm && (
        <div
          className="fixed inset-0 z-[95] flex items-center justify-center px-4 bg-mat/80 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-label="Reset comparison cohort"
          onClick={() => setCohortConfirm(null)}
        >
          <div className="w-full max-w-md" onClick={e => e.stopPropagation()}>
            <HudFrame header={<span>Cohort reset // Confirm</span>} className="border-ember/30">
              <div className="p-5 flex flex-col gap-4">
                <p className="text-[13px] text-ink-dim leading-relaxed">
                  Replacing the anchor with{' '}
                  <span className="text-ink">{cohortConfirm.canonical_player_name}</span> (
                  {POSITION_COHORT_LABEL[cohortConfirm.position_group]}) will remove other selected players and clear
                  custom stat axes from the URL.
                </p>
                <div className="flex flex-wrap gap-2 justify-end">
                  <button
                    type="button"
                    className="px-3 py-2 text-[11px] uppercase tracking-widest border border-electric/25 text-ink-muted hover:text-ink"
                    onClick={() => setCohortConfirm(null)}
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    className="px-3 py-2 text-[11px] uppercase tracking-widest border border-ember/40 text-ember hover:bg-ember/10"
                    onClick={confirmCohortResetPlayer}
                  >
                    Reset comparison
                  </button>
                </div>
              </div>
            </HudFrame>
          </div>
        </div>
      )}
    </div>
  )
}
