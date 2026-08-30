import { Info } from 'lucide-react'
import type { SeasonRole } from '../../types/api'
import { HudTooltip } from '../hud/HudTooltip'

function score(value: number | null | undefined) {
  return value == null ? '—' : value.toFixed(2)
}

export function PlayerSeasonRole({ role }: { role: SeasonRole }) {
  if (!role.primary_role) {
    const reason = role.evidence_confidence === 'pending'
      ? 'The season role calculation has not been materialized yet.'
      : role.explanation || 'No archetype cleared the evidence and fit requirements.'
    return (
      <div className="mt-3 inline-flex items-center border border-line-bright bg-raised/45">
        <HudTooltip label="Why the season role is not established" title="Role not established" description={reason} className="px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim hover:bg-raised hover:text-ink">
          Role not established
        </HudTooltip>
      </div>
    )
  }

  const candidateByArchetype = new Map((role.candidates ?? []).map(candidate => [candidate.archetype, candidate]))
  const primary = candidateByArchetype.get(role.primary_role)
  const secondary = role.secondary_archetype
  return (
    <div className="mt-3 inline-flex max-w-full flex-wrap items-stretch border border-electric/35 bg-electric/10">
      <HudTooltip label={`Meaning of ${role.primary_role} archetype`} title={role.primary_role} description={role.meaning ?? role.explanation} className="px-2.5 py-1.5 text-[9px] font-bold uppercase tracking-[0.12em] text-electric hover:bg-electric/10 hover:text-ink">
        {role.primary_role}{secondary ? <span className="ml-1.5 text-ink-muted">/ {secondary}</span> : null}
      </HudTooltip>
      {role.traits.map(trait => (
        <HudTooltip key={trait.trait} label={`Meaning of ${trait.trait} trait`} title={trait.trait} description={trait.meaning} className="border-l border-electric/20 px-2 py-1.5 text-[8px] font-bold uppercase tracking-[0.1em] text-ink-muted hover:bg-electric/10 hover:text-ink">
          {trait.trait}
        </HudTooltip>
      ))}
      <HudTooltip
        label={`Calculation details for ${role.primary_role}`}
        title={`${role.primary_role} calculation`}
        tooltipClassName="max-w-[min(28rem,calc(100vw-1.5rem))]"
        description={<>
          <p>{role.explanation}</p>
          <p className="mt-2">Fit <span className="font-mono text-electric">{score(role.primary_fit)}</span> · {role.classification_shape} · {role.evidence_confidence} · {Math.floor((role.verified_exposure_seconds ?? 0) / 60)} verified minutes</p>
          {secondary ? <p className="mt-1">Hybrid with <span className="text-ink">{secondary}</span> at <span className="font-mono">{score(role.secondary_fit)}</span></p> : null}
          {primary ? <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 border-t border-electric/15 pt-2">
            {Object.entries(primary.components).map(([label, component]) => <div key={label} className="contents"><dt>{label.replaceAll('_', ' ')}</dt><dd className="text-right font-mono text-ink">{score(component.percentile)}</dd></div>)}
          </dl> : null}
          {role.calculated_through ? <p className="mt-2 text-ink-muted">{role.team?.name ? `${role.team.name} · ` : ''}calculated through {role.calculated_through}</p> : null}
        </>}
        className="flex items-center justify-center border-l border-electric/25 px-2 text-control-fg hover:bg-electric/10 hover:text-ink"
      >
        <Info size={12} aria-hidden="true" />
      </HudTooltip>
      </div>
  )
}
