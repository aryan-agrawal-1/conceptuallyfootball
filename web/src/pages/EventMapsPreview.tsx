import { useState } from 'react'
import { FlaskConical, UserRound, UsersRound } from 'lucide-react'
import { PlayerEventMaps } from '../components/eventMaps/PlayerEventMaps'
import { TeamEventMaps } from '../components/eventMaps/TeamEventMaps'
import {
  eventPassFixture,
  playerEventProfileFixture,
  playerPassMapFixture,
  teamEventProfileFixture,
} from '../lib/eventMaps/fixtures'
import type { PlayerPassFilter } from '../types/eventMaps'
import { cn } from '../lib/utils'

type PreviewProfile = 'player' | 'team'

const previewTeams = [
  { id: 101, name: 'Fixture City' },
  { id: 102, name: 'Fixture Athletic' },
]

function filterPasses(filter: PlayerPassFilter) {
  if (filter === 'completed') return eventPassFixture.filter(pass => pass.outcome === 'successful')
  if (filter === 'progressive') return eventPassFixture.filter(pass => pass.progressive)
  if (filter === 'final_third_entry') return eventPassFixture.filter(pass => pass.finalThirdEntry)
  if (filter === 'box_entry') return eventPassFixture.filter(pass => pass.boxEntry)
  if (filter === 'key_pass') return eventPassFixture.filter(pass => pass.keyPass)
  if (filter === 'cross') return eventPassFixture.filter(pass => pass.cross)
  if (filter === 'long_ball') return eventPassFixture.filter(pass => pass.longBall)
  return eventPassFixture.filter(pass => pass.outcome === 'unsuccessful')
}

export function EventMapsPreview() {
  const [profile, setProfile] = useState<PreviewProfile>('player')

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-5 pb-24 sm:px-6 sm:py-8 lg:px-10">
      <header className="mb-6 border border-gold/35 bg-[linear-gradient(135deg,rgba(240,168,50,0.12),rgba(13,15,26,0.92)_55%)] px-4 py-4 sm:px-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center border border-gold/40 bg-gold/10 text-gold">
              <FlaskConical size={17} />
            </span>
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-gold">
                Development fixture
              </p>
              <h1 className="mt-1 text-[20px] font-black tracking-tight text-ink sm:text-[24px]">
                WhoScored Event Maps preview
              </h1>
              <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-ink-dim">
                Uses representative local events and the production Batch 6 components. Nothing on this page writes to the database or exposes pilot data.
              </p>
            </div>
          </div>
          <div className="flex border border-line-bright bg-line" role="group" aria-label="Preview profile">
            {([
              { value: 'player' as const, label: 'Player', icon: UserRound },
              { value: 'team' as const, label: 'Team', icon: UsersRound },
            ]).map(option => {
              const Icon = option.icon
              return (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setProfile(option.value)}
                  className={cn(
                    'flex h-9 items-center gap-2 bg-panel px-4 text-[9px] font-bold uppercase tracking-[0.14em]',
                    profile === option.value ? 'bg-electric/15 text-electric' : 'text-control-fg hover:text-ink',
                  )}
                >
                  <Icon size={13} /> {option.label}
                </button>
              )
            })}
          </div>
        </div>
      </header>

      {profile === 'player' ? (
        <PlayerEventMaps
          playerId={playerEventProfileFixture.playerId}
          competition={playerEventProfileFixture.competition}
          season={playerEventProfileFixture.season}
          teams={previewTeams}
          loadProfile={async (_playerId, _competition, _season, teamId) => ({
            ...playerEventProfileFixture,
            teamId: teamId ?? null,
            teamName: teamId == null ? null : previewTeams.find(team => team.id === teamId)?.name ?? null,
            splitType: teamId == null ? 'season_total' : 'team',
          })}
          loadPasses={async (_playerId, _competition, _season, filter) => {
            const passes = filterPasses(filter)
            return {
              ...playerPassMapFixture,
              filter,
              totalMatching: passes.length,
              passes,
            }
          }}
        />
      ) : (
        <TeamEventMaps
          teamId={teamEventProfileFixture.teamId}
          competition={teamEventProfileFixture.competition}
          season={teamEventProfileFixture.season}
          loadProfile={async () => teamEventProfileFixture}
        />
      )}
    </div>
  )
}
