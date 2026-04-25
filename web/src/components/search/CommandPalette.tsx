import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Command } from 'cmdk'
import { Loader2 } from 'lucide-react'
import { useSearchPaletteIndex } from '../../hooks/useSearchPaletteIndex'
import { foldForSearch } from '../../lib/foldAccents'
import { cn } from '../../lib/utils'
import type { PlayerRow } from '../../types/api'
import type { SearchTeamRow } from '../../hooks/useSearchPaletteIndex'
import { HudCornerMarks } from '../hud/Hud'

const DEFAULT_VISIBLE = 5

function filterPlayers(rows: PlayerRow[], q: string): PlayerRow[] {
  const trimmed = q.trim()
  if (!trimmed) {
    return rows.slice(0, DEFAULT_VISIBLE)
  }
  const needle = foldForSearch(trimmed)
  return rows.filter((p) => foldForSearch(p.canonical_player_name).includes(needle))
}

function filterTeams(rows: SearchTeamRow[], q: string): SearchTeamRow[] {
  const trimmed = q.trim()
  if (!trimmed) {
    return rows.slice(0, DEFAULT_VISIBLE)
  }
  const needle = foldForSearch(trimmed)
  return rows.filter((t) => foldForSearch(t.canonical_team_name).includes(needle))
}

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()
  const [search, setSearch] = useState('')
  const { playersSorted, teamsSorted, isLoading, isError } = useSearchPaletteIndex(open)

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setSearch('')
    }
    onOpenChange(next)
  }

  const visiblePlayers = useMemo(
    () => filterPlayers(playersSorted, search),
    [playersSorted, search],
  )
  const visibleTeams = useMemo(() => filterTeams(teamsSorted, search), [teamsSorted, search])

  const showEmpty =
    !isLoading &&
    !isError &&
    visiblePlayers.length === 0 &&
    visibleTeams.length === 0 &&
    search.trim() !== '' &&
    playersSorted.length + teamsSorted.length > 0

  const handleSelectPlayer = (id: number) => {
    handleOpenChange(false)
    navigate(`/player/${id}`)
  }

  const handleSelectTeam = (id: number) => {
    handleOpenChange(false)
    navigate(`/team/${id}`)
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={handleOpenChange}
      label="Search players and teams"
      shouldFilter={false}
      loop
      className="rounded-none border border-electric/25 bg-panel/95 text-ink shadow-[0_0_48px_-12px_rgba(74,158,245,0.35)] backdrop-blur-md outline-none overflow-hidden"
      overlayClassName="fixed inset-0 z-[100] bg-mat/75 backdrop-blur-[2px] data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
      contentClassName={cn(
        'fixed left-1/2 top-[min(18vh,120px)] z-[101] w-[min(100%,480px)] -translate-x-1/2',
        'p-0 data-[state=open]:animate-in data-[state=closed]:animate-out',
        'data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0',
        'data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95',
      )}
    >
      <div className="relative">
        <HudCornerMarks size="size-1.5" className="opacity-80" />
        <div className="flex items-center gap-2 border-b border-electric/20 bg-electric/5 px-3 py-2">
          <span className="size-1 shrink-0 rounded-full bg-electric animate-pulse" />
          <span className="text-[10px] uppercase tracking-[0.22em] text-electric font-mono">
            Search
          </span>
        </div>

        <Command.Input
          value={search}
          onValueChange={setSearch}
          placeholder="Player or team name…"
          className={cn(
            'w-full bg-transparent px-4 py-3 text-[13px] text-ink placeholder:text-ink-muted',
            'outline-none border-none',
            'font-sans',
          )}
        />

        <Command.List className="max-h-[min(55vh,420px)] overflow-y-auto px-1 pb-2 outline-none">
          {isLoading && (
            <Command.Loading
              className="flex items-center justify-center gap-2 py-10 text-ink-muted"
              aria-label="Loading search index"
            >
              <Loader2 className="size-4 animate-spin text-electric" />
              <span className="text-[11px] font-mono uppercase tracking-wider">Loading index…</span>
            </Command.Loading>
          )}

          {isError && !isLoading && (
            <div className="px-4 py-8 text-center text-[12px] text-ember">
              Could not load players and teams. Try again.
            </div>
          )}

          {!isLoading && !isError && (
            <>
              {visiblePlayers.length > 0 && (
                <Command.Group
                  heading="Players"
                  className="px-2 pt-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.2em] [&_[cmdk-group-heading]]:text-electric/80"
                >
                  {visiblePlayers.map((p) => (
                    <Command.Item
                      key={`p-${p.canonical_player_id}`}
                      value={`player-${p.canonical_player_id}`}
                      keywords={[p.canonical_player_name]}
                      onSelect={() => handleSelectPlayer(p.canonical_player_id)}
                      className={cn(
                        'flex cursor-pointer items-center gap-2 rounded-none border border-transparent px-3 py-2 text-[13px]',
                        'text-ink aria-selected:bg-electric/15 aria-selected:border-electric/30 aria-selected:text-electric',
                        'data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-40',
                      )}
                    >
                      <span className="truncate">{p.canonical_player_name}</span>
                      {p.canonical_team_name && (
                        <span className="ml-auto shrink-0 truncate text-[11px] text-ink-muted">
                          {p.canonical_team_name}
                        </span>
                      )}
                    </Command.Item>
                  ))}
                </Command.Group>
              )}

              {visibleTeams.length > 0 && (
                <Command.Group
                  heading="Teams"
                  className="px-2 pt-3 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.2em] [&_[cmdk-group-heading]]:text-electric/80"
                >
                  {visibleTeams.map((t) => (
                    <Command.Item
                      key={`t-${t.canonical_team_id}`}
                      value={`team-${t.canonical_team_id}`}
                      keywords={[t.canonical_team_name]}
                      onSelect={() => handleSelectTeam(t.canonical_team_id)}
                      className={cn(
                        'flex cursor-pointer items-center gap-2 rounded-none border border-transparent px-3 py-2 text-[13px]',
                        'text-ink aria-selected:bg-electric/15 aria-selected:border-electric/30 aria-selected:text-electric',
                      )}
                    >
                      <span className="truncate">{t.canonical_team_name}</span>
                    </Command.Item>
                  ))}
                </Command.Group>
              )}

              {showEmpty && (
                <Command.Empty className="py-8 text-center text-[12px] text-ink-muted">
                  No matching players or teams.
                </Command.Empty>
              )}
            </>
          )}
        </Command.List>

        <div className="flex items-center justify-between border-t border-electric/15 bg-electric/[0.04] px-3 py-1.5 text-[9px] font-mono uppercase tracking-widest text-ink-muted">
          <span>Enter to open</span>
          <span>Esc to close</span>
        </div>
      </div>
    </Command.Dialog>
  )
}
