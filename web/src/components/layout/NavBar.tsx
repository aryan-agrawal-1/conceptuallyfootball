import { useEffect, useRef, useState } from 'react'
import { NavLink } from 'react-router-dom'
import { ChevronDown, Search } from 'lucide-react'
import { useScope } from '../../context/ScopeContext'
import { BRAND_LOGO_URL, BRAND_NAME } from '../../lib/brand'
import { cn } from '../../lib/utils'
import { HudCornerMarks, HudPopover } from '../hud/Hud'
import { CommandPalette } from '../search/CommandPalette'
import type { CompetitionCatalogEntry } from '../../types/api'

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
  const [competitionOpen, setCompetitionOpen] = useState(false)
  const [seasonOpen, setSeasonOpen] = useState(false)
  const scopePickerRef = useRef<HTMLDivElement>(null)
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

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      if (!scopePickerRef.current?.contains(e.target as Node)) {
        setCompetitionOpen(false)
        setSeasonOpen(false)
      }
    }
    document.addEventListener('mousedown', onMouseDown)
    return () => document.removeEventListener('mousedown', onMouseDown)
  }, [])

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 h-[52px] flex items-center px-6 border-b border-electric/25 bg-mat/90 backdrop-blur-md">
      {/* Wordmark */}
      <NavLink to={buildScopedPath('/')} className="mr-10 flex shrink-0 items-center gap-2">
        <img src={BRAND_LOGO_URL} alt="" className="size-7 object-contain" />
        <span className="text-[13px] font-black uppercase leading-none tracking-[0.08em] text-ink">
          {BRAND_NAME}
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

        <div ref={scopePickerRef} className="flex items-center gap-1.5 border border-electric/20 px-2 py-1 bg-panel/50">
          <ScopeDropdown
            label="Competition"
            value={competitionDisplay(scope.competition, currentCompetition)}
            open={competitionOpen}
            disabled={!competitions.length}
            onOpenChange={(open) => {
              setCompetitionOpen(open)
              if (open) setSeasonOpen(false)
            }}
            widthClassName="w-40"
          >
            {competitions.length ? (
              competitions.map(c => (
                <ScopeOption
                  key={c.code}
                  active={c.code === scope.competition}
                  primary={competitionDisplay(c.code, c)}
                  secondary={c.code === 'BIG5' || c.code === 'ALL' ? undefined : c.name}
                  onSelect={() => {
                    setScope({
                      competition: c.code,
                      season: c.seasons[0]?.label ?? scope.season,
                    })
                    setCompetitionOpen(false)
                  }}
                />
              ))
            ) : (
              <ScopeOption active primary={scope.competition} onSelect={() => setCompetitionOpen(false)} />
            )}
          </ScopeDropdown>
          <span className="h-3 w-px bg-electric/20" />
          <ScopeDropdown
            label="Season"
            value={scope.season}
            open={seasonOpen}
            disabled={!currentCompetition || !seasonOptions.length}
            onOpenChange={(open) => {
              setSeasonOpen(open)
              if (open) setCompetitionOpen(false)
            }}
            widthClassName="w-28"
          >
            {seasonOptions.length ? (
              seasonOptions.map(s => (
                <ScopeOption
                  key={s.label}
                  active={s.label === scope.season}
                  primary={s.label}
                  onSelect={() => {
                    setScope({ competition: scope.competition, season: s.label })
                    setSeasonOpen(false)
                  }}
                />
              ))
            ) : (
              <ScopeOption active primary={scope.season} onSelect={() => setSeasonOpen(false)} />
            )}
          </ScopeDropdown>
          {isError && <span className="w-1 h-1 rounded-full bg-ember" title="Catalog failed" />}
        </div>
      </div>

      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </nav>
  )
}

function competitionDisplay(code: string, competition: CompetitionCatalogEntry | undefined): string {
  if (code === 'BIG5') return 'Big 5'
  if (code === 'ALL') return 'All'
  return competition?.code ?? code
}

function ScopeDropdown({
  label,
  value,
  open,
  disabled,
  onOpenChange,
  widthClassName,
  children,
}: {
  label: string
  value: string
  open: boolean
  disabled?: boolean
  onOpenChange: (open: boolean) => void
  widthClassName: string
  children: React.ReactNode
}) {
  return (
    <div className="relative">
      <button
        type="button"
        aria-label={label}
        aria-haspopup="listbox"
        aria-expanded={open}
        disabled={disabled}
        onClick={() => onOpenChange(!open)}
        className={cn(
          'relative flex items-center justify-between gap-1.5 px-2 py-1 text-[10px] font-mono uppercase tracking-[0.12em] transition-colors border',
          widthClassName,
          open
            ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
            : 'border-transparent text-electric/90 hover:border-electric/30 hover:bg-electric/5',
          disabled && 'opacity-50 pointer-events-none',
        )}
      >
        {open && <HudCornerMarks size="size-1" />}
        <span className="truncate">{value}</span>
        <ChevronDown size={11} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <HudPopover align="end" className={cn(widthClassName, 'max-h-72 overflow-y-auto p-1')}>
          <div role="listbox" aria-label={label} className="flex flex-col gap-0.5">
            {children}
          </div>
        </HudPopover>
      )}
    </div>
  )
}

function ScopeOption({
  active,
  primary,
  secondary,
  onSelect,
}: {
  active: boolean
  primary: string
  secondary?: string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={active}
      onClick={onSelect}
      className={cn(
        'w-full flex items-center justify-between gap-2 px-2.5 py-1.5 text-left transition-colors border',
        active
          ? 'border-electric/40 bg-electric/10 text-electric'
          : 'border-transparent text-ink-dim hover:bg-electric/5 hover:text-ink',
      )}
    >
      <span className="min-w-0">
        <span className="block truncate text-[11px] font-mono uppercase tracking-[0.14em]">
          {primary}
        </span>
        {secondary && (
          <span className="block truncate text-[9px] uppercase tracking-[0.14em] text-electric/45">
            {secondary}
          </span>
        )}
      </span>
      {active && <span className="size-1.5 shrink-0 bg-electric" />}
    </button>
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
