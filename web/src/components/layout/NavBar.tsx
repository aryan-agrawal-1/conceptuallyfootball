import { useEffect, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { Search } from 'lucide-react'
import { useScope } from '../../context/ScopeContext'
import { cn } from '../../lib/utils'
import { HudCornerMarks } from '../hud/Hud'
import { CommandPalette } from '../search/CommandPalette'

const NAV_LINKS = [
  { to: '/', label: 'Matrix' },
  { to: '/galaxy', label: 'Galaxy' },
  { to: '/data-visualiser', label: 'Visualiser' },
  { to: '/comparisons', label: 'Comparisons' },
  { to: '/regression-lab', label: 'Lab' },
]

const IS_MAC =
  typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform)

export function NavBar() {
  const [searchOpen, setSearchOpen] = useState(false)
  const {
    scope,
    setScope,
    competitions,
    seasonOptions,
    currentCompetition,
    buildScopedPath,
    isError,
  } = useScope()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault()
        setSearchOpen((o) => !o)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-[52px] flex items-center px-6 border-b border-electric/25 bg-mat/90 backdrop-blur-md">
      {/* Wordmark */}
      <NavLink to={buildScopedPath('/')} className="flex items-baseline gap-0 mr-10 shrink-0">
        <span
          className="text-electric font-black tracking-[0.06em] text-[17px] leading-none"
          style={{ fontWeight: 900 }}
        >
          STAT
        </span>
        <span
          className="text-ink font-black tracking-[0.06em] text-[17px] leading-none"
          style={{ fontWeight: 900 }}
        >
          BALLER
        </span>
      </NavLink>

      {/* Nav links */}
      <div className="flex items-center gap-2">
        {NAV_LINKS.map(({ to, label }) => (
          <NavLink key={to} to={buildScopedPath(to)} end={to === '/'}>
            {({ isActive }) => <HudNavButton active={isActive}>{label}</HudNavButton>}
          </NavLink>
        ))}
      </div>

      <div className="ml-auto flex items-center gap-3">
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className={cn(
            'relative flex items-center gap-2 border px-2.5 py-1.5 transition-colors',
            'border-electric/20 bg-panel/50 text-ink-muted hover:border-electric/40 hover:text-electric/90',
            'focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-electric/50',
          )}
          aria-label="Open search"
        >
          <Search className="size-4 shrink-0 text-electric/80" strokeWidth={2} />
          <span className="hidden sm:inline text-[10px] font-medium tracking-[0.18em] uppercase font-mono">
            Search
          </span>
          <kbd
            className={cn(
              'hidden md:inline-flex items-center gap-0.5 rounded border border-electric/25 bg-mat/80 px-1.5 py-0.5',
              'text-[9px] font-mono tracking-wide text-ink-muted',
            )}
          >
            {IS_MAC ? '⌘' : 'Ctrl'}K
          </kbd>
        </button>

        <div className="flex items-center gap-1.5 border border-electric/20 px-2 py-1 bg-panel/50">
          <label htmlFor="global-competition" className="sr-only">
            Competition
          </label>
          <select
            id="global-competition"
            value={scope.competition}
            disabled={!competitions.length}
            onChange={event => {
              const competition = event.target.value
              const nextCompetition = competitions.find(c => c.code === competition)
              setScope({
                competition,
                season: nextCompetition?.seasons[0]?.label ?? scope.season,
              })
            }}
            className="max-w-[5.5rem] bg-transparent text-[10px] font-mono uppercase tracking-[0.12em] text-electric/90 outline-none disabled:opacity-50"
          >
            {competitions.length ? (
              competitions.map(c => (
                <option key={c.code} value={c.code}>
                  {c.code}
                </option>
              ))
            ) : (
              <option value={scope.competition}>{scope.competition}</option>
            )}
          </select>
          <span className="h-3 w-px bg-electric/20" />
          <label htmlFor="global-season" className="sr-only">
            Season
          </label>
          <select
            id="global-season"
            value={scope.season}
            disabled={!currentCompetition || !seasonOptions.length}
            onChange={event => setScope({ competition: scope.competition, season: event.target.value })}
            className="w-[5rem] bg-transparent text-[10px] font-mono uppercase tracking-[0.08em] text-electric/90 outline-none disabled:opacity-50"
          >
            {seasonOptions.length ? (
              seasonOptions.map(s => (
                <option key={s.label} value={s.label}>
                  {s.label}
                </option>
              ))
            ) : (
              <option value={scope.season}>{scope.season}</option>
            )}
          </select>
          {isError && <span className="w-1 h-1 rounded-full bg-ember" title="Catalog failed" />}
        </div>
      </div>

      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </nav>
  )
}

/**
 * Nav-link visual shell. Matches `HudPill` from the shared HUD module but
 * stays inline here because the active state comes from react-router's
 * `NavLink` render-prop rather than a handler.
 */
function HudNavButton({
  active,
  children,
}: {
  active: boolean
  children: React.ReactNode
}) {
  return (
    <span
      className={cn(
        'relative px-3 py-1 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border',
        active
          ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
          : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
      )}
    >
      {active && <HudCornerMarks size="size-1" />}
      {children}
    </span>
  )
}
