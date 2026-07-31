import { LAB_HELP } from './regressionLabHelp'

export const REGRESSION_LAB_WALKTHROUGH_VERSION = 1
export const REGRESSION_LAB_WALKTHROUGH_STORAGE_KEY =
  'conceptually-football:regression-lab-walkthrough'

export type RegressionLabWalkthroughStatus = 'skipped' | 'completed'

interface StoredRegressionLabWalkthrough {
  version: number
  status: RegressionLabWalkthroughStatus
}

export interface RegressionLabWalkthroughStep {
  id: string
  title: string
  body: string
  anchor: string
  unavailable: string
}

export const REGRESSION_LAB_WALKTHROUGH_STEPS: readonly RegressionLabWalkthroughStep[] = [
  {
    id: 'cohort',
    title: 'Define the cohort',
    body: LAB_HELP.cohortPanel,
    anchor: '[data-regression-walkthrough="cohort"]',
    unavailable: 'The cohort controls are not available yet. You can continue and return later.',
  },
  {
    id: 'target',
    title: 'Choose the target',
    body: LAB_HELP.targetPanel,
    anchor: '[data-regression-walkthrough="target"]',
    unavailable: 'Choose a position to reveal target metrics. You can continue without changing it now.',
  },
  {
    id: 'predictors',
    title: 'Choose predictors',
    body: `${LAB_HELP.predictorsWalkthrough} ${LAB_HELP.predictorLeakage}`,
    anchor: '[data-regression-walkthrough="predictors"]',
    unavailable: 'Choose a position and target to reveal predictor choices. You can still continue.',
  },
  {
    id: 'readiness',
    title: 'Check model readiness',
    body: LAB_HELP.readinessPanel,
    anchor: '[data-regression-walkthrough="readiness"]',
    unavailable: 'Readiness appears after a target and predictors are selected. You can still continue.',
  },
  {
    id: 'run',
    title: 'Run the model',
    body: LAB_HELP.runModel,
    anchor: '[data-regression-walkthrough="run"]',
    unavailable: 'The run control is not available in the current lab state. You can still continue.',
  },
  {
    id: 'fit',
    title: 'Read fit results',
    body: LAB_HELP.fitSummary,
    anchor: '[data-regression-walkthrough="fit"]',
    unavailable: 'Run a model to reveal fit results. You can continue without running one now.',
  },
  {
    id: 'coefficients',
    title: 'Interpret coefficients',
    body: LAB_HELP.coefficientsPanel,
    anchor: '[data-regression-walkthrough="coefficients"]',
    unavailable: 'Run a model to reveal standardized coefficients. You can continue without them.',
  },
  {
    id: 'errors',
    title: 'Inspect prediction errors',
    body: LAB_HELP.predictionErrors,
    anchor: '[data-regression-walkthrough="errors"]',
    unavailable: 'Run a model to reveal the prediction chart and residual table. You can still finish.',
  },
] as const

function isStoredWalkthrough(value: unknown): value is StoredRegressionLabWalkthrough {
  if (!value || typeof value !== 'object') return false
  const record = value as Record<string, unknown>
  return (
    typeof record.version === 'number' &&
    (record.status === 'skipped' || record.status === 'completed')
  )
}

function browserStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

export function readRegressionLabWalkthrough(
  storage: Storage | null = browserStorage(),
): StoredRegressionLabWalkthrough | null {
  if (!storage) return null
  try {
    const raw = storage.getItem(REGRESSION_LAB_WALKTHROUGH_STORAGE_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    return isStoredWalkthrough(parsed) ? parsed : null
  } catch {
    return null
  }
}

export function shouldOfferRegressionLabWalkthrough(
  version = REGRESSION_LAB_WALKTHROUGH_VERSION,
  storage: Storage | null = browserStorage(),
): boolean {
  const stored = readRegressionLabWalkthrough(storage)
  return !stored || stored.version !== version
}

export function saveRegressionLabWalkthroughStatus(
  status: RegressionLabWalkthroughStatus,
  version = REGRESSION_LAB_WALKTHROUGH_VERSION,
  storage: Storage | null = browserStorage(),
): boolean {
  if (!storage) return false
  try {
    storage.setItem(
      REGRESSION_LAB_WALKTHROUGH_STORAGE_KEY,
      JSON.stringify({ version, status } satisfies StoredRegressionLabWalkthrough),
    )
    return true
  } catch {
    return false
  }
}
