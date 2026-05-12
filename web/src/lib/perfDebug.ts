const PERF_QUERY_PARAM = 'matrixPerf'
const PERF_STORAGE_KEY = 'statMatrixPerf'

/**
 * Enable perf logs by either:
 * - adding ?matrixPerf=1 to the URL, or
 * - running localStorage.setItem('statMatrixPerf', '1') in devtools.
 */
function isMatrixPerfLoggingEnabled(): boolean {
  if (typeof window === 'undefined') return false
  const params = new URLSearchParams(window.location.search)
  if (params.get(PERF_QUERY_PARAM) === '1') return true
  return window.localStorage.getItem(PERF_STORAGE_KEY) === '1'
}

/** Coarse sync phase timing (script + layout) vs paint; only when perf logging is on. */
export function logMatrixPerfPhases(label: string, t0: number) {
  if (!isMatrixPerfLoggingEnabled()) return
  const afterSync = performance.now() - t0
  requestAnimationFrame(() => {
    const afterPaint = performance.now() - t0
    console.info(
      `[StatMatrix] ${label}: sync+layout ~${afterSync.toFixed(2)}ms, after next paint ~${afterPaint.toFixed(2)}ms`,
    )
  })
}
