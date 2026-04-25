import { useRef, useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Search, ChevronDown, X, Loader2 } from 'lucide-react'
import { cn } from '../../lib/utils'
import type { MatrixFilters, PositionGroup } from '../../types/api'
import { SCORE_GROUP_ID, type ColGroupDef } from '../../lib/columns'
import type { MatrixRateMode } from '../../lib/matrixRateMode'
import { HudCornerMarks, HudPill, HudVSep } from '../hud/Hud'

const POSITIONS: { value: PositionGroup | ''; label: string }[] = [
  { value: '',    label: 'All' },
  { value: 'FWD', label: 'FWD' },
  { value: 'MID', label: 'MID' },
  { value: 'DEF', label: 'DEF' },
  { value: 'GK',  label: 'GK'  },
]

const MIN_MINUTES_OPTIONS = [0, 450, 900, 1350, 1800]

interface FilterBarProps {
  filters: MatrixFilters
  teams: string[]
  heatmapEnabled: boolean
  rateMode: MatrixRateMode
  columnGroups: ColGroupDef[]
  visibleCols: Record<string, boolean>
  onFiltersChange: (partial: Partial<MatrixFilters>) => void
  onHeatmapToggle: () => void
  onRateModeChange: (mode: MatrixRateMode) => void
  onColGroupToggle: (groupId: string) => void
  playerCount: number
  totalCount: number
  /** True while a new matrix request is in flight but stale rows are still shown. */
  refetching?: boolean
  /** Hand off current cohort to Regression Lab (outfield position only). */
  regressionLabHref?: string | null
}

export function FilterBar({
  filters,
  teams,
  heatmapEnabled,
  rateMode,
  columnGroups,
  visibleCols,
  onFiltersChange,
  onHeatmapToggle,
  onRateModeChange,
  onColGroupToggle,
  playerCount,
  totalCount,
  refetching = false,
  regressionLabHref = null,
}: FilterBarProps) {
  const [teamOpen, setTeamOpen] = useState(false)
  const [colPickerOpen, setColPickerOpen] = useState(false)
  const [teamSearch, setTeamSearch] = useState('')
  const teamRef = useRef<HTMLDivElement>(null)
  const colRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handler(e: MouseEvent) {
      if (teamRef.current && !teamRef.current.contains(e.target as Node)) setTeamOpen(false)
      if (colRef.current && !colRef.current.contains(e.target as Node)) setColPickerOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const selectedTeams = filters.teams ?? []
  const selectedCount = selectedTeams.length

  function toggleTeam(team: string) {
    const next = selectedTeams.includes(team)
      ? selectedTeams.filter(t => t !== team)
      : [...selectedTeams, team]
    onFiltersChange({ teams: next.length ? next : undefined })
  }

  function clearTeams() {
    onFiltersChange({ teams: undefined })
    setTeamOpen(false)
  }

  return (
    <div className="sticky top-[52px] z-40 flex items-center gap-3 px-6 h-[54px] bg-panel/80 border-b border-electric/25 backdrop-blur-md shrink-0 shadow-[0_8px_28px_-14px_rgba(74,158,245,0.45)]">
      <MatrixReadout
        playerCount={playerCount}
        totalCount={totalCount}
        refetching={refetching}
      />

      <HudVSep />

      <PositionGroupPicker
        value={filters.position_group}
        onChange={pos => onFiltersChange({ position_group: pos || undefined })}
      />

      <HudVSep />

      <TeamPicker
        containerRef={teamRef}
        open={teamOpen}
        onOpenChange={setTeamOpen}
        teams={teams}
        selectedTeams={selectedTeams}
        selectedCount={selectedCount}
        search={teamSearch}
        onSearchChange={setTeamSearch}
        onToggle={toggleTeam}
        onClear={clearTeams}
      />

      <HudVSep />

      <MinMinutesPicker
        value={filters.min_minutes}
        onChange={mins => onFiltersChange({ min_minutes: mins })}
      />

      {regressionLabHref && (
        <>
          <HudVSep />
          <Link
            to={regressionLabHref}
            className={cn(
              'relative shrink-0 px-2.5 py-1 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border',
              'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
            )}
          >
            Lab
          </Link>
        </>
      )}

      <div className="flex-1" />

      <RateModeToggle value={rateMode} onChange={onRateModeChange} />

      <HudVSep />

      <HeatmapToggle enabled={heatmapEnabled} onToggle={onHeatmapToggle} />

      <ColumnsDropdown
        containerRef={colRef}
        open={colPickerOpen}
        onOpenChange={setColPickerOpen}
        columnGroups={columnGroups}
        visibleCols={visibleCols}
        scoresLocked={!filters.position_group}
        onGroupToggle={onColGroupToggle}
      />
    </div>
  )
}

// ─── Readout ─────────────────────────────────────────────────────────────────

function MatrixReadout({
  playerCount,
  totalCount,
  refetching,
}: {
  playerCount: number
  totalCount: number
  refetching: boolean
}) {
  return (
    <span className="flex items-center gap-2 shrink-0">
      <span className="size-1 rounded-full bg-electric animate-pulse" />
      <span className="text-[10px] uppercase tracking-[0.25em] text-electric/80 font-medium">
        Matrix
      </span>
      <span className="flex items-center gap-1 text-[11px] font-mono tabular-nums">
        {refetching && (
          <Loader2 size={12} className="text-electric animate-spin" aria-hidden />
        )}
        <span className="text-electric">{playerCount.toLocaleString()}</span>
        <span className="text-electric/30">/</span>
        <span className="text-ink-dim">{totalCount.toLocaleString()}</span>
      </span>
    </span>
  )
}

// ─── Position filter ─────────────────────────────────────────────────────────

function PositionGroupPicker({
  value,
  onChange,
}: {
  value: string | undefined
  onChange: (value: PositionGroup | '') => void
}) {
  return (
    <div className="flex items-center gap-1">
      {POSITIONS.map(({ value: optValue, label }) => {
        const active = value === optValue || (!value && optValue === '')
        return (
          <HudPill
            key={label}
            active={active}
            onClick={() => onChange(optValue)}
          >
            {label}
          </HudPill>
        )
      })}
    </div>
  )
}

// ─── Min minutes filter ──────────────────────────────────────────────────────

function MinMinutesPicker({
  value,
  onChange,
}: {
  value: number | null | undefined
  onChange: (mins: number) => void
}) {
  return (
    <div className="flex items-center gap-1">
      {MIN_MINUTES_OPTIONS.map(mins => (
        <HudPill
          key={mins}
          active={value === mins}
          onClick={() => onChange(mins)}
          className="font-mono"
        >
          {mins === 0 ? 'All' : `${mins}'`}
        </HudPill>
      ))}
    </div>
  )
}

// ─── Rate mode toggle ────────────────────────────────────────────────────────

function RateModeToggle({
  value,
  onChange,
}: {
  value: MatrixRateMode
  onChange: (mode: MatrixRateMode) => void
}) {
  return (
    <div
      className="relative flex items-center border border-electric/30 bg-mat/60 overflow-hidden shrink-0"
      role="group"
      aria-label="Stat rate display"
    >
      <RateModeButton
        active={value === 'per90'}
        onClick={() => onChange('per90')}
      >
        /90
      </RateModeButton>
      <span className="w-px h-full bg-electric/25" />
      <RateModeButton
        active={value === 'full'}
        onClick={() => onChange('full')}
      >
        Season
      </RateModeButton>
    </div>
  )
}

function RateModeButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'px-2.5 py-1 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors',
        active
          ? 'bg-electric/15 text-electric shadow-[inset_0_0_12px_-4px_rgba(74,158,245,0.6)]'
          : 'text-ink-muted hover:text-electric/80',
      )}
    >
      {children}
    </button>
  )
}

// ─── Heatmap toggle ──────────────────────────────────────────────────────────

function HeatmapToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean
  onToggle: () => void
}) {
  return (
    <button
      onClick={onToggle}
      className={cn(
        'relative flex items-center gap-2 px-3 py-1.5 border text-[11px] font-medium tracking-[0.15em] uppercase transition-colors',
        enabled
          ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
          : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
      )}
    >
      {enabled && <HudCornerMarks size="size-1" />}
      <span
        className={cn(
          'size-1.5 rounded-full transition-colors',
          enabled ? 'bg-electric animate-pulse' : 'bg-electric/20',
        )}
      />
      Heatmap
    </button>
  )
}

// ─── Team picker ─────────────────────────────────────────────────────────────

interface TeamPickerProps {
  containerRef: React.RefObject<HTMLDivElement | null>
  open: boolean
  onOpenChange: (open: boolean) => void
  teams: string[]
  selectedTeams: string[]
  selectedCount: number
  search: string
  onSearchChange: (value: string) => void
  onToggle: (team: string) => void
  onClear: () => void
}

function TeamPicker({
  containerRef,
  open,
  onOpenChange,
  teams,
  selectedTeams,
  selectedCount,
  search,
  onSearchChange,
  onToggle,
  onClear,
}: TeamPickerProps) {
  const filteredTeams = teams.filter(t =>
    t.toLowerCase().includes(search.toLowerCase()),
  )

  const label =
    selectedCount === 0
      ? 'All Clubs'
      : selectedCount === 1
        ? selectedTeams[0]
        : `${selectedCount} Clubs`

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => onOpenChange(!open)}
        className={cn(
          'relative flex items-center gap-1.5 px-3 py-1 text-[11px] font-medium tracking-[0.15em] uppercase transition-colors border',
          selectedCount > 0
            ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
            : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
        )}
      >
        {selectedCount > 0 && <HudCornerMarks size="size-1" />}
        {label}
        {selectedCount > 0 ? (
          <X
            size={11}
            className="opacity-70"
            onClick={(e) => {
              e.stopPropagation()
              onClear()
            }}
          />
        ) : (
          <ChevronDown size={11} className={cn('transition-transform', open && 'rotate-180')} />
        )}
      </button>
      {open && (
        <HudPopover className="w-60">
          <div className="p-2 border-b border-electric/20">
            <div className="flex items-center gap-2 px-2 py-1.5 border border-electric/20 bg-mat/60">
              <Search size={12} className="text-electric/60 shrink-0" />
              <input
                autoFocus
                value={search}
                onChange={e => onSearchChange(e.target.value)}
                placeholder="Search club..."
                className="flex-1 text-[11px] bg-transparent outline-none text-ink placeholder:text-electric/30 tracking-wide"
              />
              {search && (
                <button
                  onClick={() => onSearchChange('')}
                  className="text-electric/50 hover:text-electric"
                >
                  <X size={10} />
                </button>
              )}
            </div>
          </div>
          <div className="max-h-56 overflow-y-auto p-1">
            {selectedCount > 0 && (
              <button
                onClick={onClear}
                className="w-full text-left px-3 py-1.5 text-[10px] uppercase tracking-[0.2em] text-electric/70 hover:bg-electric/10 hover:text-electric transition-colors mb-0.5"
              >
                Clear selection
              </button>
            )}
            {filteredTeams.map(team => {
              const checked = selectedTeams.includes(team)
              return (
                <button
                  key={team}
                  onClick={() => onToggle(team)}
                  className={cn(
                    'w-full flex items-center gap-2.5 px-3 py-1.5 text-[12px] transition-colors',
                    checked
                      ? 'text-electric bg-electric/10'
                      : 'text-ink-dim hover:bg-electric/5 hover:text-ink',
                  )}
                >
                  <span
                    className={cn(
                      'flex items-center justify-center w-3.5 h-3.5 border shrink-0 transition-colors',
                      checked ? 'border-electric bg-electric/30' : 'border-electric/30',
                    )}
                  >
                    {checked && (
                      <svg width="8" height="6" viewBox="0 0 8 6" fill="none">
                        <path
                          d="M1 3L3 5L7 1"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="text-electric"
                        />
                      </svg>
                    )}
                  </span>
                  {team}
                </button>
              )
            })}
            {filteredTeams.length === 0 && (
              <p className="px-3 py-3 text-[11px] text-electric/40 text-center uppercase tracking-[0.2em]">
                No clubs found
              </p>
            )}
          </div>
        </HudPopover>
      )}
    </div>
  )
}

// ─── Columns dropdown ────────────────────────────────────────────────────────

interface ColumnsDropdownProps {
  containerRef: React.RefObject<HTMLDivElement | null>
  open: boolean
  onOpenChange: (open: boolean) => void
  columnGroups: ColGroupDef[]
  visibleCols: Record<string, boolean>
  scoresLocked: boolean
  onGroupToggle: (groupId: string) => void
}

function ColumnsDropdown({
  containerRef,
  open,
  onOpenChange,
  columnGroups,
  visibleCols,
  scoresLocked,
  onGroupToggle,
}: ColumnsDropdownProps) {
  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => onOpenChange(!open)}
        className={cn(
          'relative flex items-center gap-1.5 px-3 py-1.5 border text-[11px] font-medium tracking-[0.15em] uppercase transition-colors',
          open
            ? 'border-electric bg-electric/15 text-electric shadow-[0_0_16px_-6px_rgba(74,158,245,0.8)]'
            : 'border-electric/15 text-ink-muted hover:border-electric/40 hover:text-electric/80',
        )}
      >
        {open && <HudCornerMarks size="size-1" />}
        Columns
        <ChevronDown size={11} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <ColumnPicker
          groups={columnGroups}
          visibleCols={visibleCols}
          scoresLocked={scoresLocked}
          onGroupToggle={onGroupToggle}
        />
      )}
    </div>
  )
}

const SCORES_LOCKED_TOOLTIP =
  'Scores are percentile ranks within each position (FWD, MID, DEF). Choose a position to compare players on the same scale.'

interface ColumnPickerProps {
  groups: ColGroupDef[]
  visibleCols: Record<string, boolean>
  scoresLocked: boolean
  onGroupToggle: (groupId: string) => void
}

function ColumnPicker({ groups, visibleCols, scoresLocked, onGroupToggle }: ColumnPickerProps) {
  const statGroups = groups.filter(g => g.id !== 'meta')

  return (
    <HudPopover className="w-64" align="end">
      <div className="p-3">
        <p className="flex items-center gap-1.5 text-[10px] font-medium tracking-[0.25em] uppercase text-electric mb-2.5">
          <span className="size-1 rounded-full bg-electric animate-pulse" />
          Column Groups
        </p>
        <div className="flex flex-col gap-1">
          {statGroups.map(group => {
            const allVisible = group.cols.every(c => visibleCols[c.id])
            const someVisible = group.cols.some(c => visibleCols[c.id])
            const locked = scoresLocked && group.id === SCORE_GROUP_ID

            if (locked) {
              return (
                <ScoresLockedRow
                  key={group.id}
                  label={group.label}
                  colCount={group.cols.length}
                />
              )
            }

            return (
              <button
                key={group.id}
                type="button"
                onClick={() => onGroupToggle(group.id)}
                className={cn(
                  'flex items-center justify-between px-3 py-2 text-[12px] font-medium transition-colors border',
                  allVisible
                    ? 'border-electric/40 bg-electric/10 text-electric'
                    : someVisible
                      ? 'border-electric/20 bg-electric/5 text-ink-dim'
                      : 'border-transparent text-ink-muted hover:bg-electric/5 hover:text-ink-dim',
                )}
              >
                <span>{group.label}</span>
                <span className="text-[10px] text-electric/60 font-mono tracking-wider">
                  {group.cols.length} cols
                </span>
              </button>
            )
          })}
        </div>
      </div>
    </HudPopover>
  )
}

function ScoresLockedRow({ label, colCount }: { label: string; colCount: number }) {
  const [open, setOpen] = useState(false)

  return (
    <div
      className="relative"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <div
        className="flex items-center justify-between px-3 py-2 text-[12px] font-medium cursor-help opacity-50 text-ink-muted border border-dashed border-electric/15"
        aria-describedby={open ? 'scores-locked-tooltip' : undefined}
      >
        <span>{label}</span>
        <span className="text-[10px] text-ink-muted font-mono tracking-wider">
          {colCount} cols
        </span>
      </div>
      {open && (
        <div
          id="scores-locked-tooltip"
          role="tooltip"
          className="absolute left-0 right-0 top-full z-[60] mt-1.5 border border-electric/25 bg-panel/95 backdrop-blur-md px-2.5 py-2 text-[11px] leading-snug text-ink-dim shadow-[0_8px_28px_-8px_rgba(74,158,245,0.4)] pointer-events-none"
        >
          {SCORES_LOCKED_TOOLTIP}
        </div>
      )}
    </div>
  )
}

// ─── Popover chrome ──────────────────────────────────────────────────────────
// A shared dropdown surface with the same look as HudFrame, but positioned
// below a trigger button. `align` decides which edge of the trigger the
// popover snaps to — use `end` when the trigger sits near the right edge
// of the viewport so the popover opens inward and doesn't clip.
function HudPopover({
  children,
  className,
  align = 'start',
}: {
  children: React.ReactNode
  className?: string
  align?: 'start' | 'end'
}) {
  return (
    <div
      className={cn(
        'absolute top-full mt-1.5 border border-electric/25 bg-panel/95 backdrop-blur-md shadow-[0_12px_40px_-8px_rgba(74,158,245,0.45)] z-50',
        align === 'start' ? 'left-0' : 'right-0',
        className,
      )}
    >
      <HudCornerMarks />
      {children}
    </div>
  )
}
