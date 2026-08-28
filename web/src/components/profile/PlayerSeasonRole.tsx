import { Info } from 'lucide-react'
import type { SeasonRole } from '../../types/api'
import { HudTooltip } from '../hud/HudTooltip'

function score(value: number | null | undefined) {
  return value == null ? '—' : value.toFixed(2)
}

export function PlayerSeasonRole({ role }: { role: SeasonRole }) {
  if (!role.primary_role) {
    const reason = role.confidence === 'pending'
      ? 'The season role calculation has not been materialized yet.'
      : 'Insufficient verified evidence to establish a season role.'
    return (
      <div className="mt-3 inline-flex items-center border border-line-bright bg-raised/45">
        <HudTooltip label="Why the season role is not established" title="Role not established" description={reason} className="px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim hover:bg-raised hover:text-ink">
          Role not established
        </HudTooltip>
      </div>
    )
  }

  const coverage = Object.entries(role.state_coverage ?? {})
  const primary = role.role_scores?.find(item => item.role === role.primary_role)
  return (
    <div className="mt-3 inline-flex max-w-full items-stretch border border-electric/35 bg-electric/10">
      <HudTooltip label={`Meaning of ${role.primary_role} season role`} title={role.primary_role} description={role.meaning ?? role.explanation} className="px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-electric hover:bg-electric/10 hover:text-ink">
        {role.primary_role}
      </HudTooltip>
      <HudTooltip
        label={`Calculation details for ${role.primary_role}`}
        title={`${role.primary_role} calculation`}
        tooltipClassName="max-w-[min(28rem,calc(100vw-1.5rem))]"
        description={<>
          <p>{role.explanation}</p>
          <p className="mt-2">Score <span className="font-mono text-electric">{score(role.primary_score)}</span> · {role.confidence} · {Math.floor((role.verified_exposure_seconds ?? 0) / 60)} verified minutes</p>
          {role.runner_up_role ? <p className="mt-1">Runner-up <span className="text-ink">{role.runner_up_role}</span> at <span className="font-mono">{score(role.runner_up_score)}</span></p> : null}
          {coverage.length ? <p className="mt-1 text-ink-muted">{coverage.map(([state, item]) => `${state} ${item.minutes.toFixed(0)} min`).join(' · ')}</p> : null}
          {primary ? <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-electric/15 pt-2">
            {Object.entries(primary.components).map(([label, value]) => <div key={label} className="contents"><dt>{label.replaceAll('_', ' ')}</dt><dd className="text-right font-mono text-ink">{value.toFixed(2)}</dd></div>)}
          </dl> : null}
          {role.calculated_through ? <p className="mt-2 text-ink-muted">Calculated through {role.calculated_through} · {role.team_context_quality?.replaceAll('_', ' ')}</p> : null}
        </>}
        className="flex items-center justify-center border-l border-electric/25 px-2 text-control-fg hover:bg-electric/10 hover:text-ink"
      >
        <Info size={12} aria-hidden="true" />
      </HudTooltip>
      </div>
  )
}
