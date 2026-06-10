import { useDeferredValue, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Command } from 'cmdk'
import { BarChart3, GitCompare, Loader2, Microscope, Orbit, type LucideIcon } from 'lucide-react'
import { useSearchPaletteIndex } from '../../hooks/useSearchPaletteIndex'
import { resolveEntityMembership, resolveEntityScope } from '../../hooks/useSearchPaletteIndex'
import { foldForSearch } from '../../lib/foldAccents'
import { CREATE_CHARTS_PATH } from '../../lib/createChartsUrl'
import { cn } from '../../lib/utils'
import { useScope, type Scope } from '../../context/ScopeContext'
import type { SearchPlayerEntity, SearchTeamEntity } from '../../types/api'
import { HudCornerMarks } from '../hud/Hud'
import { membershipPriority } from '../../lib/scopeMembership'

const DEFAULT_VISIBLE = 5
const SEARCH_VISIBLE_LIMIT = 12

type SearchAction = {
  id: string
  label: string
  description: string
  href: string
  icon: LucideIcon
  aliases: string[]
}

const SEARCH_ACTIONS: SearchAction[] = [
  {
    id: 'create-charts',
    label: 'Create chart',
    description: 'Build scatter, bar, and radar graphics',
    href: CREATE_CHARTS_PATH,
    icon: BarChart3,
    aliases: ['charts', 'visualiser', 'visualizer', 'scatter', 'bar', 'radar', 'share', 'export', 'png'],
  },
  {
    id: 'compare-players',
    label: 'Compare players',
    description: 'Open the same-position radar comparison tool',
    href: '/comparisons',
    icon: GitCompare,
    aliases: ['compare', 'comparison', 'radar', 'players', 'versus', 'vs'],
  },
  {
    id: 'regression-lab',
    label: 'Open Regression Lab',
    description: 'Explore metric relationships and model fit',
    href: '/regression-lab',
    icon: Microscope,
    aliases: ['lab', 'regression', 'model', 'predict', 'coefficients', 'fit'],
  },
  {
    id: 'galaxy',
    label: 'Open Galaxy',
    description: 'Explore similarity maps and archetypes',
    href: '/galaxy',
    icon: Orbit,
    aliases: ['similar', 'similarity', 'archetypes', 'network', 'map'],
  },
]

type SearchIndexEntry<T> = {
  entity: T
  foldedName: string
  priority: number
}

function buildPlayerIndex(
  rows: SearchPlayerEntity[],
  scope: Scope,
): Array<SearchIndexEntry<SearchPlayerEntity>> {
  return rows
    .map(entity => ({
      entity,
      foldedName: foldForSearch(entity.canonical_player_name),
      priority: membershipPriority(entity.memberships, scope),
    }))
    .sort((a, b) => {
      const priorityDelta = a.priority - b.priority
      if (priorityDelta !== 0) return priorityDelta
      return b.entity.total_minutes - a.entity.total_minutes
    })
}

function buildTeamIndex(
  rows: SearchTeamEntity[],
  scope: Scope,
): Array<SearchIndexEntry<SearchTeamEntity>> {
  return rows
    .map(entity => ({
      entity,
      foldedName: foldForSearch(entity.canonical_team_name),
      priority: membershipPriority(entity.memberships, scope),
    }))
    .sort((a, b) => {
      const priorityDelta = a.priority - b.priority
      if (priorityDelta !== 0) return priorityDelta
      return a.entity.canonical_team_name.localeCompare(b.entity.canonical_team_name)
    })
}

function pickMatches<T>(index: Array<SearchIndexEntry<T>>, q: string, limit: number): T[] {
  const trimmed = q.trim()
  const visibleLimit = trimmed ? limit : DEFAULT_VISIBLE
  if (!trimmed) return index.slice(0, visibleLimit).map(item => item.entity)

  const needle = foldForSearch(trimmed)
  const matches: T[] = []
  for (const item of index) {
    if (!item.foldedName.includes(needle)) continue
    matches.push(item.entity)
    if (matches.length >= visibleLimit) break
  }
  return matches
}

function pickActionMatches(q: string): SearchAction[] {
  const trimmed = q.trim()
  if (!trimmed) return SEARCH_ACTIONS
  const needle = foldForSearch(trimmed)
  return SEARCH_ACTIONS.filter(action => {
    const haystack = [
      action.label,
      action.description,
      ...action.aliases,
    ].map(foldForSearch)
    return haystack.some(value => value.includes(needle))
  })
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
  const deferredSearch = useDeferredValue(search)
  const { scope, buildScopedPath } = useScope()
  const { globalPlayers, globalTeams, isLoading, isError } = useSearchPaletteIndex(open)

  const handleOpenChange = (next: boolean) => {
    if (!next) {
      setSearch('')
    }
    onOpenChange(next)
  }

  const playerIndex = useMemo(
    () => buildPlayerIndex(globalPlayers, scope),
    [globalPlayers, scope],
  )
  const teamIndex = useMemo(
    () => buildTeamIndex(globalTeams, scope),
    [globalTeams, scope],
  )
  const visiblePlayers = useMemo(
    () => pickMatches(playerIndex, deferredSearch, SEARCH_VISIBLE_LIMIT),
    [deferredSearch, playerIndex],
  )
  const visibleTeams = useMemo(
    () => pickMatches(teamIndex, deferredSearch, SEARCH_VISIBLE_LIMIT),
    [deferredSearch, teamIndex],
  )
  const visibleActions = useMemo(
    () => pickActionMatches(deferredSearch),
    [deferredSearch],
  )

  const showEmpty =
    !isLoading &&
    !isError &&
    visibleActions.length === 0 &&
    visiblePlayers.length === 0 &&
    visibleTeams.length === 0 &&
    deferredSearch.trim() !== '' &&
    globalPlayers.length + globalTeams.length > 0

  const handleSelectPlayer = (entity: SearchPlayerEntity) => {
    const nextScope = resolveEntityScope(entity.memberships, scope)
    handleOpenChange(false)
    navigate(buildScopedPath(`/player/${entity.canonical_player_id}`, nextScope ?? undefined))
  }

  const handleSelectTeam = (entity: SearchTeamEntity) => {
    const nextScope = resolveEntityScope(entity.memberships, scope)
    handleOpenChange(false)
    navigate(buildScopedPath(`/team/${entity.canonical_team_id}`, nextScope ?? undefined))
  }

  const handleSelectAction = (action: SearchAction) => {
    handleOpenChange(false)
    navigate(buildScopedPath(action.href))
  }

  return (
    <Command.Dialog
      open={open}
      onOpenChange={handleOpenChange}
      label="Search actions, players, and teams"
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
          placeholder="Action, player, or team name..."
          className={cn(
            'w-full bg-transparent px-4 py-3 text-[13px] text-ink placeholder:text-ink-muted',
            'outline-none border-none',
            'font-sans',
          )}
        />

        <Command.List className="max-h-[min(55vh,420px)] overflow-y-auto px-1 pb-2 outline-none">
          {visibleActions.length > 0 && (
            <Command.Group
              heading="Actions"
              className="px-2 pt-2 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.2em] [&_[cmdk-group-heading]]:text-electric/80"
            >
              {visibleActions.map(action => (
                <SearchActionItem
                  key={action.id}
                  action={action}
                  onSelect={() => handleSelectAction(action)}
                />
              ))}
            </Command.Group>
          )}

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
                  className="px-2 pt-3 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.2em] [&_[cmdk-group-heading]]:text-electric/80"
                >
                  {visiblePlayers.map((p) => (
                    <SearchPlayerItem
                      key={`p-${p.canonical_player_id}`}
                      player={p}
                      scope={scope}
                      onSelect={() => handleSelectPlayer(p)}
                    />
                  ))}
                </Command.Group>
              )}

              {visibleTeams.length > 0 && (
                <Command.Group
                  heading="Teams"
                  className="px-2 pt-3 [&_[cmdk-group-heading]]:px-2 [&_[cmdk-group-heading]]:pb-1.5 [&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-mono [&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-[0.2em] [&_[cmdk-group-heading]]:text-electric/80"
                >
                  {visibleTeams.map((t) => (
                    <SearchTeamItem
                      key={`t-${t.canonical_team_id}`}
                      team={t}
                      scope={scope}
                      onSelect={() => handleSelectTeam(t)}
                    />
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

function SearchActionItem({
  action,
  onSelect,
}: {
  action: SearchAction
  onSelect: () => void
}) {
  const Icon = action.icon
  return (
    <Command.Item
      value={`action-${action.id}`}
      keywords={[action.label, action.description, ...action.aliases]}
      onSelect={onSelect}
      className={cn(
        'flex cursor-pointer items-center gap-3 rounded-none border border-transparent px-3 py-2 text-[13px]',
        'text-ink aria-selected:bg-electric/15 aria-selected:border-electric/30 aria-selected:text-electric',
      )}
    >
      <span className="flex size-7 shrink-0 items-center justify-center border border-electric/20 bg-electric/5 text-electric/80">
        <Icon size={15} strokeWidth={2} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{action.label}</span>
        <span className="block truncate text-[11px] text-ink-muted">{action.description}</span>
      </span>
    </Command.Item>
  )
}

function SearchPlayerItem({
  player,
  scope,
  onSelect,
}: {
  player: SearchPlayerEntity
  scope: Scope
  onSelect: () => void
}) {
  const membership = resolveEntityMembership(player.memberships, scope)
  return (
    <Command.Item
      value={`player-${player.canonical_player_id}`}
      keywords={[player.canonical_player_name]}
      onSelect={onSelect}
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-none border border-transparent px-3 py-2 text-[13px]',
        'text-ink aria-selected:bg-electric/15 aria-selected:border-electric/30 aria-selected:text-electric',
        'data-[disabled=true]:pointer-events-none data-[disabled=true]:opacity-40',
      )}
    >
      <span className="min-w-0 flex-1 truncate">{player.canonical_player_name}</span>
      {membership && (
        <span className="ml-auto flex max-w-[55%] shrink-0 items-center gap-2 overflow-hidden text-[11px] text-ink-muted">
          {membership.canonical_team_name && (
            <span className="truncate">{membership.canonical_team_name}</span>
          )}
          <span className="shrink-0 font-mono text-[10px] text-electric/70">
            {membership.competition} {membership.season}
          </span>
        </span>
      )}
    </Command.Item>
  )
}

function SearchTeamItem({
  team,
  scope,
  onSelect,
}: {
  team: SearchTeamEntity
  scope: Scope
  onSelect: () => void
}) {
  const membership = resolveEntityMembership(team.memberships, scope)
  return (
    <Command.Item
      value={`team-${team.canonical_team_id}`}
      keywords={[team.canonical_team_name]}
      onSelect={onSelect}
      className={cn(
        'flex cursor-pointer items-center gap-2 rounded-none border border-transparent px-3 py-2 text-[13px]',
        'text-ink aria-selected:bg-electric/15 aria-selected:border-electric/30 aria-selected:text-electric',
      )}
    >
      <span className="min-w-0 flex-1 truncate">{team.canonical_team_name}</span>
      {membership && (
        <span className="ml-auto shrink-0 font-mono text-[10px] text-electric/70">
          {membership.competition} {membership.season}
        </span>
      )}
    </Command.Item>
  )
}
