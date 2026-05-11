import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import { AlertCircle, ChevronDown, ChevronUp, Copy, Loader2 } from 'lucide-react'
import { HudActionButton, HudFrame, HudLabel, HudPill, HudVSep } from '../components/hud/Hud'
import { LabHelpHover } from '../components/regression/LabHelpHover'
import { RegressionScatterPlot } from '../components/regression/RegressionScatterPlot'
import { applyClientFilters, useStatMatrix } from '../hooks/useStatMatrix'
import { fetchRegressionLabFit } from '../lib/api'
import {
  groupPredictorPool,
  isLabPosition,
  PREDICTOR_METRIC_POOL,
  recommendedPredictorsForTarget,
  TARGETS_BY_POSITION,
  toLabPosition,
  type LabPosition,
} from '../lib/regressionLabConfig'
import { LAB_HELP } from '../lib/regressionLabHelp'
import {
  parseRegressionLabParams,
  writeRegressionLabParams,
  type RegressionLabUrlState,
} from '../lib/regressionLabUrl'
import { cn } from '../lib/utils'
import { hasMetricCoverage } from '../lib/metricAvailability'
import type {
  MatrixFilters,
  PlayerRow,
  RegressionLabPredictionRow,
  StatMeta,
} from '../types/api'
import { useScope } from '../context/ScopeContext'

const EMPTY: PlayerRow[] = []

const LAB_POSITIONS: { value: LabPosition; label: string }[] = [
  { value: 'FWD', label: 'FWD' },
  { value: 'MID', label: 'MID' },
  { value: 'DEF', label: 'DEF' },
]

function targetValue(row: PlayerRow, targetKey: string): number | null {
  return row.metrics[targetKey] ?? null
}

function countUsableRows(rows: PlayerRow[], targetKey: string, predictorKeys: string[]): number {
  if (!predictorKeys.length) return 0
  return rows.filter(p => {
    const y = targetValue(p, targetKey)
    if (y === null) return false
    for (const k of predictorKeys) {
      const x = p.metrics[k]
      if (x === null || x === undefined) return false
    }
    return true
  }).length
}

type CohortSortCol = 'player' | 'club' | 'actual' | 'pred' | 'residual'

function compareCohortRows(
  a: RegressionLabPredictionRow,
  b: RegressionLabPredictionRow,
  col: CohortSortCol,
  dir: 'asc' | 'desc',
): number {
  const m = dir === 'asc' ? 1 : -1
  switch (col) {
    case 'player':
      return m * a.canonical_player_name.localeCompare(b.canonical_player_name, undefined, { sensitivity: 'base' })
    case 'club':
      return m * (a.canonical_team_name ?? '').localeCompare(b.canonical_team_name ?? '', undefined, {
        sensitivity: 'base',
      })
    case 'actual':
      return m * (a.actual - b.actual)
    case 'pred':
      return m * (a.predicted_oof - b.predicted_oof)
    case 'residual':
      return m * (a.residual - b.residual)
    default:
      return 0
  }
}

export function RegressionLab() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { scope, scopeLabel, buildScopedPath } = useScope()
  const [filters, setFilters] = useState<MatrixFilters>(() => {
    const p = parseRegressionLabParams(searchParams)
    return {
      competition: p.competition,
      season: p.season,
      teams: p.teams,
      position_group: p.position_group,
      min_minutes: p.min_minutes,
    }
  })
  const [target, setTarget] = useState<string>(() => searchParams.get('target')?.trim() ?? '')
  const [predictors, setPredictors] = useState<string[]>(() => {
    const raw = searchParams.get('predictors')
    return raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : []
  })
  const [predictorsCustomized, setPredictorsCustomized] = useState(() => {
    const raw = searchParams.get('predictors')
    return Boolean(raw?.trim())
  })
  const [pendingTarget, setPendingTarget] = useState<string | null>(null)
  const [lastFit, setLastFit] = useState<import('../types/api').RegressionLabFitResponse | null>(null)
  const [lastFitKey, setLastFitKey] = useState<string | null>(null)
  const [fitError, setFitError] = useState<string | null>(null)
  const autoRunConsumed = useRef(false)

  const [cohortSortCol, setCohortSortCol] = useState<CohortSortCol>('residual')
  const [cohortSortDir, setCohortSortDir] = useState<'asc' | 'desc'>('desc')

  useEffect(() => {
    setFilters(prev => {
      if (prev.competition === scope.competition && prev.season === scope.season) return prev
      return { ...prev, competition: scope.competition, season: scope.season, teams: undefined }
    })
  }, [scope.competition, scope.season])

  const fetchFilters = useMemo(
    (): MatrixFilters => ({
      competition: filters.competition,
      season: filters.season,
      min_minutes: filters.min_minutes,
    }),
    [filters.competition, filters.season, filters.min_minutes],
  )

  const { data, isLoading, isError, error } = useStatMatrix(fetchFilters)
  const allPlayers = data?.results ?? EMPTY
  const meta: StatMeta | undefined = data?.meta

  const teams = useMemo(() => {
    const names = allPlayers
      .map(p => p.canonical_team_name)
      .filter((t): t is string => t !== null)
    return [...new Set(names)].sort()
  }, [allPlayers])

  const cohortRows = useMemo(() => {
    if (!filters.position_group || !isLabPosition(filters.position_group)) return []
    return applyClientFilters(allPlayers, {
      teams: filters.teams,
      position_group: filters.position_group,
      min_minutes: filters.min_minutes,
    })
  }, [allPlayers, filters])

  const position = toLabPosition(filters.position_group)

  const availableTargetKeys = useMemo(() => {
    if (!position || !meta) return []
    return TARGETS_BY_POSITION[position].filter(key => {
      if (!meta.metrics[key]) return false
      if (!cohortRows.length) return true
      return hasMetricCoverage(cohortRows, row => targetValue(row, key))
    })
  }, [cohortRows, meta, position])

  const availablePredictorKeys = useMemo(() => {
    if (!meta) return []
    return PREDICTOR_METRIC_POOL.filter(key => {
      if (!meta.metrics[key]) return false
      if (!cohortRows.length) return true
      return hasMetricCoverage(cohortRows, row => row.metrics[key])
    })
  }, [cohortRows, meta])

  const availablePredictorKeySet = useMemo(
    () => new Set(availablePredictorKeys),
    [availablePredictorKeys],
  )

  const predictorGroups = useMemo(
    () => groupPredictorPool(meta, availablePredictorKeys),
    [availablePredictorKeys, meta],
  )

  useEffect(() => {
    if (!position) return
    if (isLoading) return
    if (target && !availableTargetKeys.includes(target)) {
      setTarget('')
      setPredictors([])
      setPredictorsCustomized(false)
    }
  }, [availableTargetKeys, isLoading, position, target])

  useEffect(() => {
    if (isLoading || !predictors.length) return
    const next = predictors.filter(key => availablePredictorKeySet.has(key))
    if (next.length !== predictors.length) {
      setPredictors(next)
      setPredictorsCustomized(next.length > 0)
    }
  }, [availablePredictorKeySet, isLoading, predictors])

  const usablePreview = useMemo(
    () => countUsableRows(cohortRows, target, predictors),
    [cohortRows, target, predictors],
  )

  const configKey = useMemo(() => {
    const ids = cohortRows.map(r => r.canonical_player_id).sort((a, b) => a - b)
    return JSON.stringify({
      c: filters.competition,
      s: filters.season,
      p: filters.position_group,
      tms: (filters.teams ?? []).slice().sort(),
      m: filters.min_minutes,
      target,
      preds: [...predictors].sort(),
      ids,
    })
  }, [cohortRows, filters, target, predictors])

  const resultsStale = Boolean(lastFit && lastFitKey && lastFitKey !== configKey)

  useEffect(() => {
    setSearchParams(prev => {
      const keepRun = prev.get('run') === '1' && !autoRunConsumed.current
      const p = writeRegressionLabParams(
        {
          competition: filters.competition,
          season: filters.season,
          position_group: position ?? undefined,
          teams: filters.teams,
          min_minutes: filters.min_minutes,
          target: target || undefined,
          predictors: predictors.length ? predictors : undefined,
          autoRun: keepRun ? true : undefined,
        },
        { includeRunFlag: keepRun },
      )
      return p
    }, { replace: true })
  }, [filters, target, predictors, position, setSearchParams])

  const fitKeyRef = useRef('')

  const fitMutation = useMutation({
    mutationFn: async () => {
      if (!position || !target || !predictors.length) throw new Error('Incomplete model spec.')
      const ids = cohortRows.map(r => r.canonical_player_id)
      return fetchRegressionLabFit({
        competition: filters.competition,
        season: filters.season,
        position_group: position,
        canonical_player_ids: ids,
        target_key: target,
        predictor_keys: predictors,
      })
    },
    onSuccess: res => {
      setFitError(null)
      setLastFit(res)
      setLastFitKey(fitKeyRef.current)
    },
    onError: (e: Error) => {
      setFitError(e.message)
    },
  })

  const runModel = useCallback(() => {
    setFitError(null)
    fitKeyRef.current = configKey
    void fitMutation.mutateAsync()
  }, [configKey, fitMutation])

  useEffect(() => {
    const p = parseRegressionLabParams(searchParams)
    if (!p.autoRun || autoRunConsumed.current) return
    if (!position || !target || predictors.length === 0) return
    if (usablePreview < 30) return
    if (isLoading) return
    autoRunConsumed.current = true
    fitKeyRef.current = configKey
    setSearchParams(prev => {
      const n = new URLSearchParams(prev)
      n.delete('run')
      return n
    }, { replace: true })
    void fitMutation.mutateAsync()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLoading, position, target, predictors, usablePreview, searchParams])

  function handleFiltersChange(partial: Partial<MatrixFilters>) {
    setFilters(prev => ({ ...prev, ...partial }))
  }

  function applyTarget(next: string, opts?: { forceReplacePredictors?: boolean }) {
    if (!position) return
    const replace = opts?.forceReplacePredictors || !predictorsCustomized
    setTarget(next)
    if (replace) {
      setPredictors(recommendedPredictorsForTarget(next, position, availablePredictorKeys))
      setPredictorsCustomized(false)
    }
  }

  function onSelectTarget(next: string) {
    if (!position) {
      setTarget(next)
      return
    }
    if (next === target) return
    if (predictorsCustomized) {
      setPendingTarget(next)
      return
    }
    applyTarget(next, { forceReplacePredictors: true })
  }

  function togglePredictor(key: string) {
    setPredictorsCustomized(true)
    setPredictors(prev =>
      prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key],
    )
  }

  function copyShareLink() {
    const state: RegressionLabUrlState = {
      competition: filters.competition,
      season: filters.season,
      position_group: position ?? undefined,
      teams: filters.teams,
      min_minutes: filters.min_minutes,
      target: target || undefined,
      predictors: predictors.length ? predictors : undefined,
      autoRun: true,
    }
    const q = writeRegressionLabParams(state, { includeRunFlag: true }).toString()
    const url = `${window.location.origin}${window.location.pathname}?${q}`
    void navigator.clipboard.writeText(url)
  }

  const targetLabel =
    meta?.metrics[target]?.label ??
    target

  const canRun =
    Boolean(position) &&
    Boolean(target) &&
    predictors.length > 0 &&
    cohortRows.length > 0 &&
    usablePreview >= 30

  const sortedCohortRows = useMemo(() => {
    if (!lastFit?.predictions) return []
    const rows = [...lastFit.predictions]
    rows.sort((a, b) => compareCohortRows(a, b, cohortSortCol, cohortSortDir))
    return rows
  }, [lastFit, cohortSortCol, cohortSortDir])

  function onCohortSortClick(col: CohortSortCol) {
    if (col === cohortSortCol) {
      setCohortSortDir(d => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setCohortSortCol(col)
      setCohortSortDir(col === 'player' || col === 'club' ? 'asc' : 'desc')
    }
  }

  const coefSpotlight = useMemo(() => {
    if (!lastFit) return { posKey: null as string | null, negKey: null as string | null }
    let posKey: string | null = null
    let negKey: string | null = null
    let posV = 0
    let negV = 0
    for (const c of lastFit.coefficients) {
      if (c.coefficient_std > posV) {
        posV = c.coefficient_std
        posKey = c.key
      }
      if (c.coefficient_std < negV) {
        negV = c.coefficient_std
        negKey = c.key
      }
    }
    return { posKey, negKey }
  }, [lastFit])

  return (
    <div className="flex min-h-[calc(100svh-132px)] flex-col lg:min-h-[calc(100svh-52px)]">
      <div className="sticky top-[64px] z-40 flex shrink-0 items-center gap-2 overflow-x-auto border-b border-electric/25 bg-panel/80 px-3 py-2 backdrop-blur-md lg:top-[52px] lg:flex-wrap lg:gap-3 lg:overflow-visible lg:px-6">
        <HudLabel className="shrink-0 whitespace-nowrap">Regression Lab</HudLabel>
        <HudVSep className="hidden lg:block" />
        <span className="hidden shrink-0 whitespace-nowrap text-[11px] font-mono uppercase tracking-[0.16em] text-electric/85 sm:inline">
          {scopeLabel}
        </span>
        <HudVSep className="hidden lg:block" />
        <div
          className={cn(
            'flex items-center gap-1 rounded border px-1.5 py-0.5 transition-[box-shadow,border-color]',
            !position &&
              'border-ember/70 shadow-[0_0_22px_-6px_rgba(239,68,68,0.55)] ring-1 ring-ember/35 bg-ember/5',
            position && 'border-electric/15',
          )}
        >
          <span
            className={cn(
              'text-[9px] uppercase tracking-[0.22em] px-1 shrink-0',
              !position ? 'text-ember font-semibold' : 'text-ink-muted',
            )}
          >
            Pos
          </span>
          {LAB_POSITIONS.map(({ value, label }) => (
            <HudPill
              key={value}
              active={filters.position_group === value}
              onClick={() => handleFiltersChange({ position_group: value })}
            >
              {label}
            </HudPill>
          ))}
        </div>
        <HudVSep className="hidden lg:block" />
        <TeamStrip
          teams={teams}
          selected={filters.teams ?? []}
          onChange={next => handleFiltersChange({ teams: next.length ? next : undefined })}
        />
        <HudVSep className="hidden lg:block" />
        <MinStrip value={filters.min_minutes} onChange={m => handleFiltersChange({ min_minutes: m })} />
        <div className="hidden flex-1 lg:block lg:min-w-[8px]" />
        <Link
          to={buildScopedPath('/')}
          className="text-[10px] uppercase tracking-[0.2em] text-electric/70 hover:text-electric"
        >
          Matrix
        </Link>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-auto px-4 py-4 sm:px-6">
        {isLoading && (
          <div className="flex items-center justify-center py-16 gap-2 text-electric">
            <Loader2 className="animate-spin size-5" />
            <span className="text-[11px] tracking-[0.2em] uppercase">Loading cohort</span>
          </div>
        )}
        {isError && (
          <HudFrame header="Signal Lost" className="max-w-md border-ember/40">
            <p className="p-4 text-[12px] text-ember">{error?.message}</p>
          </HudFrame>
        )}
        {!isLoading && !isError && (
          <>
            {!position && (
              <p className="text-[12px] text-ink-muted">
                Choose <span className="text-electric">FWD</span>, <span className="text-electric">MID</span>, or{' '}
                <span className="text-electric">DEF</span> to define the cohort.
              </p>
            )}
            {position && cohortRows.length === 0 && (
              <p className="text-[12px] text-ink-muted">No players match these filters.</p>
            )}

            <div className="grid gap-4 lg:grid-cols-2 lg:items-stretch">
              <HudFrame
                header={
                  <>
                    <span className="truncate">Target // Outcome</span>
                    <LabHelpHover label="What is the target?">
                      <p>{LAB_HELP.targetPanel}</p>
                    </LabHelpHover>
                  </>
                }
                className="min-h-[260px] lg:h-[40vh] lg:min-h-0"
                bodyClassName="flex-1 min-h-0 flex flex-col overflow-hidden p-0"
              >
                <div className="flex-1 min-h-0 overflow-y-auto p-3 flex flex-col gap-2">
                  {position &&
                    availableTargetKeys.map(key => (
                      <button
                        key={key}
                        type="button"
                        onClick={() => onSelectTarget(key)}
                        className={cn(
                          'text-left px-2 py-1.5 text-[12px] border transition-colors',
                          target === key
                            ? 'border-electric bg-electric/10 text-electric'
                            : 'border-electric/15 text-ink-dim hover:border-electric/35',
                        )}
                      >
                        {meta?.metrics[key]?.label ?? key}
                      </button>
                    ))}
                  {position && availableTargetKeys.length === 0 && (
                    <p className="text-[11px] text-ink-muted">
                      No populated target metrics are available for this cohort.
                    </p>
                  )}
                  {!position && (
                    <p className="text-[11px] text-ink-muted">Select a position to see targets.</p>
                  )}
                </div>
              </HudFrame>

              <HudFrame
                header={
                  <>
                    <span className="truncate">Predictors // Evidence</span>
                    <LabHelpHover label="What are predictors?">
                      <p>{LAB_HELP.predictorsPanel}</p>
                    </LabHelpHover>
                  </>
                }
                className="min-h-[300px] lg:h-[40vh] lg:min-h-0"
                bodyClassName="flex-1 min-h-0 flex flex-col overflow-hidden p-0"
              >
                <div className="flex-1 min-h-0 overflow-y-auto p-3 flex flex-col gap-3">
                  <p className="text-[10px] text-ink-muted uppercase tracking-[0.18em]">
                    Raw metrics only · grouped by stat family · toggle to add/remove
                  </p>
                  {!meta && (
                    <p className="text-[11px] text-ink-muted">Load cohort data to show predictor groups.</p>
                  )}
                  {meta &&
                    predictorGroups.map(group => (
                      <div key={group.groupId}>
                        <p className="text-[9px] uppercase tracking-[0.22em] text-electric/70 mb-1.5">
                          {group.groupLabel}
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {group.keys.map(key => {
                            const on = predictors.includes(key)
                            return (
                              <HudPill
                                key={key}
                                active={on}
                                onClick={() => togglePredictor(key)}
                                className="font-mono text-[10px]"
                                title={meta.metrics[key]?.description}
                              >
                                {meta.metrics[key]?.label ?? key}
                              </HudPill>
                            )
                          })}
                        </div>
                      </div>
                    ))}
                  {predictors.length > 6 && (
                    <p className="text-[10px] text-amber-300/90 leading-snug">
                      {predictors.length} predictors: large sets overlap more and make coefficients harder to read.
                    </p>
                  )}
                </div>
              </HudFrame>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <HudActionButton
                type="button"
                onClick={() => void runModel()}
                disabled={!canRun || fitMutation.isPending}
              >
                {fitMutation.isPending ? 'Running…' : 'Run model'}
              </HudActionButton>
              {usablePreview < 30 && position && target && predictors.length > 0 && (
                <span className="text-[11px] text-ember flex items-center gap-1">
                  <AlertCircle size={14} />
                  Need ≥30 usable rows (non-null target + predictors). Currently {usablePreview}.
                </span>
              )}
              {usablePreview >= 30 && usablePreview < 50 && (
                <span className="text-[11px] text-amber-200/90">
                  Only {usablePreview} usable rows — metrics may be noisy.
                </span>
              )}
              <button
                type="button"
                onClick={copyShareLink}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-electric/25 text-[10px] uppercase tracking-[0.2em] text-electric/80 hover:bg-electric/10"
              >
                <Copy size={12} />
                Copy share link
              </button>
            </div>

            {fitError && (
              <HudFrame header="Fit Error" className="max-w-lg border-ember/40">
                <p className="p-3 text-[12px] text-ember">{fitError}</p>
              </HudFrame>
            )}

            {resultsStale && lastFit && (
              <div className="border border-amber-400/40 bg-amber-400/10 px-3 py-2 text-[11px] text-amber-100">
                Results are out of date — cohort, target, or predictors changed. Run again to refresh.
              </div>
            )}

            {lastFit && !resultsStale && (
              <div className="grid min-w-0 gap-4 xl:grid-cols-2">
                <HudFrame header="Fit summary // CV headline" className="min-w-0" bodyClassName="p-3">
                  <div className="grid grid-cols-2 gap-3 font-mono text-[12px]">
                    <FitSummaryStat
                      label="CV R²"
                      help={LAB_HELP.fitCvR2}
                      value={lastFit.fit.r2_cv.toFixed(3)}
                      valueClassName="text-2xl text-electric"
                    />
                    <div>
                      <div className="flex items-center gap-1 mb-1">
                        <p className="text-[9px] uppercase tracking-[0.2em] text-ink-muted">CV MAE</p>
                        <LabHelpHover label="Cross-validated MAE">
                          <p>{LAB_HELP.fitCvMae}</p>
                        </LabHelpHover>
                      </div>
                      <p className="text-lg text-ink tabular-nums">{lastFit.fit.mae_cv.toFixed(3)}</p>
                      <div className="flex items-center gap-1 mt-1 text-[9px] text-ink-muted">
                        <span>CV RMSE {lastFit.fit.rmse_cv.toFixed(3)}</span>
                        <LabHelpHover label="Cross-validated RMSE">
                          <p>{LAB_HELP.fitCvRmse}</p>
                        </LabHelpHover>
                      </div>
                    </div>
                    <FitSummaryStat
                      label="Train R²"
                      help={LAB_HELP.fitTrainR2}
                      value={lastFit.fit.r2_train.toFixed(3)}
                    />
                    <div>
                      <div className="flex items-center gap-1 mb-1">
                        <p className="text-[9px] uppercase tracking-[0.2em] text-ink-muted">Sample</p>
                        <LabHelpHover label="Sample sizes">
                          <p>{LAB_HELP.fitSample}</p>
                        </LabHelpHover>
                      </div>
                      <p className="text-ink tabular-nums">
                        {lastFit.sample.usable_rows} / {lastFit.sample.cohort_rows}
                      </p>
                      <p className="text-[9px] text-ink-muted">dropped {lastFit.sample.dropped_rows}</p>
                    </div>
                  </div>
                  <p className="mt-3 text-[10px] text-ink-muted font-mono">
                    Ridge α = {lastFit.alpha.toFixed(4)} · intercept {lastFit.intercept.toFixed(3)}
                  </p>
                  {lastFit.warnings.map((w, i) => (
                    <p key={i} className="mt-2 text-[10px] text-amber-200/90 leading-snug">
                      {w}
                    </p>
                  ))}
                </HudFrame>

                <HudFrame
                  header={
                    <>
                      <span className="truncate">Coefficients // standardized</span>
                      <LabHelpHover label="How to read coefficients">
                        <p>{LAB_HELP.coefficientsPanel}</p>
                      </LabHelpHover>
                    </>
                  }
                  className="min-w-0"
                  bodyClassName="p-0"
                >
                  <div className="max-h-56 overflow-x-auto overflow-y-auto">
                    <table className="w-full min-w-[420px] text-[11px] font-mono">
                      <thead className="sticky top-0 bg-mat/95 border-b border-electric/20 text-ink-muted uppercase tracking-wider text-[9px]">
                        <tr>
                          <th className="text-left px-2 py-1.5">Predictor</th>
                          <th className="text-right px-2 py-1.5">
                            <span className="inline-flex items-center justify-end gap-1">
                              <span>Coef (std X)</span>
                              <LabHelpHover label="Coefficient column">
                                <p>{LAB_HELP.coefColumn}</p>
                              </LabHelpHover>
                            </span>
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {lastFit.coefficients.map(c => {
                          const topPos = c.key === coefSpotlight.posKey && c.coefficient_std > 0
                          const topNeg = c.key === coefSpotlight.negKey && c.coefficient_std < 0
                          return (
                            <tr
                              key={c.key}
                              className={cn(
                                'border-b border-electric/10',
                                topPos && 'bg-emerald-500/10 text-emerald-200',
                                topNeg && 'bg-rose-500/10 text-rose-200',
                              )}
                            >
                              <td className="px-2 py-1 text-ink-dim">{c.label}</td>
                              <td className="px-2 py-1 text-right tabular-nums">
                                {c.coefficient_std >= 0 ? '+' : ''}
                                {c.coefficient_std.toFixed(3)}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </HudFrame>

                <HudFrame
                  header={
                    <>
                      <span className="truncate">Predicted vs actual // OOF</span>
                      <LabHelpHover label="What is OOF?">
                        <p>{LAB_HELP.oofScatter}</p>
                      </LabHelpHover>
                    </>
                  }
                  className="min-w-0 xl:col-span-2"
                  bodyClassName="p-2"
                >
                  <RegressionScatterPlot rows={lastFit.predictions} targetLabel={targetLabel} />
                </HudFrame>
              </div>
            )}

            {lastFit && !resultsStale && (
              <HudFrame header="Cohort // residuals" bodyClassName="p-0 overflow-x-auto">
                <table className="w-full min-w-[640px] text-[11px] font-mono">
                  <thead className="text-[9px] uppercase tracking-[0.2em] text-ink-muted border-b border-electric/20 bg-mat/90">
                    <tr>
                      <th className="text-left px-2 py-2 w-[28%]">
                        <div className="flex items-center gap-1">
                          <SortableTh
                            label="Player"
                            active={cohortSortCol === 'player'}
                            dir={cohortSortDir}
                            onClick={() => onCohortSortClick('player')}
                          />
                          <LabHelpHover label="Player column">
                            <p>{LAB_HELP.colPlayer}</p>
                          </LabHelpHover>
                        </div>
                      </th>
                      <th className="text-left px-2 py-2 w-[22%]">
                        <div className="flex items-center gap-1">
                          <SortableTh
                            label="Club"
                            active={cohortSortCol === 'club'}
                            dir={cohortSortDir}
                            onClick={() => onCohortSortClick('club')}
                          />
                          <LabHelpHover label="Club column">
                            <p>{LAB_HELP.colClub}</p>
                          </LabHelpHover>
                        </div>
                      </th>
                      <th className="text-right px-2 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <SortableTh
                            label="Actual"
                            active={cohortSortCol === 'actual'}
                            dir={cohortSortDir}
                            onClick={() => onCohortSortClick('actual')}
                            align="right"
                          />
                          <LabHelpHover label="Actual column">
                            <p>{LAB_HELP.colActual}</p>
                          </LabHelpHover>
                        </div>
                      </th>
                      <th className="text-right px-2 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <SortableTh
                            label="Pred OOF"
                            active={cohortSortCol === 'pred'}
                            dir={cohortSortDir}
                            onClick={() => onCohortSortClick('pred')}
                            align="right"
                          />
                          <LabHelpHover label="Predicted OOF column">
                            <p>{LAB_HELP.colPredOof}</p>
                          </LabHelpHover>
                        </div>
                      </th>
                      <th className="text-right px-2 py-2">
                        <div className="flex items-center justify-end gap-1">
                          <SortableTh
                            label="Residual"
                            active={cohortSortCol === 'residual'}
                            dir={cohortSortDir}
                            onClick={() => onCohortSortClick('residual')}
                            align="right"
                          />
                          <LabHelpHover label="Residual column">
                            <p>{LAB_HELP.colResidual}</p>
                          </LabHelpHover>
                        </div>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedCohortRows.map(r => (
                      <tr key={r.canonical_player_id} className="border-b border-electric/10 hover:bg-electric/5">
                        <td className="px-2 py-1.5 text-ink">{r.canonical_player_name}</td>
                        <td className="px-2 py-1.5 text-ink-dim">{r.canonical_team_name ?? '—'}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums">{r.actual.toFixed(3)}</td>
                        <td className="px-2 py-1.5 text-right tabular-nums text-electric/90">
                          {r.predicted_oof.toFixed(3)}
                        </td>
                        <td
                          className={cn(
                            'px-2 py-1.5 text-right tabular-nums',
                            r.residual >= 0 ? 'text-emerald-300/90' : 'text-rose-300/90',
                          )}
                        >
                          {r.residual >= 0 ? '+' : ''}
                          {r.residual.toFixed(3)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </HudFrame>
            )}
          </>
        )}
      </div>

      {pendingTarget && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-mat/80 backdrop-blur-sm px-4">
          <HudFrame header="Target changed" className="w-full max-w-md">
            <p className="p-4 text-[12px] text-ink-muted leading-relaxed">
              You customized predictors. Replace them with the recommended pack for{' '}
              <span className="text-electric">{pendingTarget}</span>, or keep your current set?
            </p>
            <div className="flex gap-2 px-4 pb-4">
              <HudActionButton
                type="button"
                onClick={() => {
                  if (!position || !pendingTarget) return
                  setTarget(pendingTarget)
                  setPredictors(recommendedPredictorsForTarget(pendingTarget, position))
                  setPredictorsCustomized(false)
                  setPendingTarget(null)
                }}
              >
                Use recommended
              </HudActionButton>
              <button
                type="button"
                className="px-4 py-3 border border-electric/25 text-[11px] uppercase tracking-[0.15em] text-ink-muted hover:text-electric"
                onClick={() => {
                  if (pendingTarget) setTarget(pendingTarget)
                  setPredictorsCustomized(true)
                  setPendingTarget(null)
                }}
              >
                Keep predictors
              </button>
            </div>
          </HudFrame>
        </div>
      )}
    </div>
  )
}

function FitSummaryStat({
  label,
  help,
  value,
  valueClassName,
}: {
  label: string
  help: string
  value: string
  valueClassName?: string
}) {
  return (
    <div>
      <div className="flex items-center gap-1 mb-1">
        <p className="text-[9px] uppercase tracking-[0.2em] text-ink-muted">{label}</p>
        <LabHelpHover label={label}>
          <p>{help}</p>
        </LabHelpHover>
      </div>
      <p className={cn('text-ink tabular-nums', valueClassName)}>{value}</p>
    </div>
  )
}

function SortableTh({
  label,
  active,
  dir,
  onClick,
  align = 'left',
}: {
  label: string
  active: boolean
  dir: 'asc' | 'desc'
  onClick: () => void
  align?: 'left' | 'right'
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1 uppercase tracking-[0.2em] hover:text-electric transition-colors text-left',
        align === 'right' && 'justify-end w-full text-right',
      )}
    >
      <span>{label}</span>
      {active ? (
        dir === 'desc' ? (
          <ChevronDown className="size-3.5 shrink-0 text-electric" aria-hidden />
        ) : (
          <ChevronUp className="size-3.5 shrink-0 text-electric" aria-hidden />
        )
      ) : (
        <span className="inline-block w-3.5 h-3.5 shrink-0 opacity-0" aria-hidden />
      )}
    </button>
  )
}

function MinStrip({
  value,
  onChange,
}: {
  value: number
  onChange: (n: number) => void
}) {
  const opts = [0, 450, 900, 1350, 1800]
  return (
    <div className="flex items-center gap-1">
      {opts.map(m => (
        <HudPill key={m} active={value === m} onClick={() => onChange(m)} className="font-mono">
          {m === 0 ? 'All' : `${m}'`}
        </HudPill>
      ))}
    </div>
  )
}

function TeamStrip({
  teams,
  selected,
  onChange,
}: {
  teams: string[]
  selected: string[]
  onChange: (teams: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    function h(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])
  const label =
    selected.length === 0 ? 'All Clubs' : selected.length === 1 ? selected[0] : `${selected.length} Clubs`
  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className={cn(
          'px-3 py-1 text-[11px] font-medium tracking-[0.15em] uppercase border transition-colors',
          selected.length
            ? 'border-electric bg-electric/15 text-electric'
            : 'border-electric/15 text-ink-muted hover:border-electric/40',
        )}
      >
        {label}
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 min-w-[200px] max-h-56 overflow-y-auto border border-electric/25 bg-panel/95 backdrop-blur-md shadow-xl p-1">
          {selected.length > 0 && (
            <button
              type="button"
              className="w-full text-left px-2 py-1 text-[10px] uppercase text-electric/70 hover:bg-electric/10"
              onClick={() => {
                onChange([])
                setOpen(false)
              }}
            >
              Clear clubs
            </button>
          )}
          {teams.map(t => {
            const on = selected.includes(t)
            return (
              <button
                key={t}
                type="button"
                className={cn(
                  'w-full text-left px-2 py-1.5 text-[12px]',
                  on ? 'text-electric bg-electric/10' : 'text-ink-dim hover:bg-electric/5',
                )}
                onClick={() => {
                  onChange(on ? selected.filter(x => x !== t) : [...selected, t])
                }}
              >
                {t}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
