const STATE_LENS_FIELDS = [
  'state', 'goal_difference', 'phase', 'draw_provenance',
  'minimum_state_age_seconds', 'maximum_state_age_seconds',
] as const

export function stateLensRequest(searchParams: URLSearchParams) {
  const request: Record<string, string> = {}
  STATE_LENS_FIELDS.forEach(field => {
    const value = searchParams.get(field)
    if (value != null) request[field] = value
    const baseline = searchParams.get(`baseline_${field}`)
    if (baseline != null) request[`baseline_${field}`] = baseline
  })
  return request
}
