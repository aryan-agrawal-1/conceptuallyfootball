import { Link } from 'react-router-dom'
import { cn } from '../../lib/utils'
import { useScope } from '../../context/ScopeContext'

interface ProfileBreadcrumbProps {
  playerName: string
  className?: string
}

export function ProfileBreadcrumb({ playerName, className }: ProfileBreadcrumbProps) {
  const { buildScopedPath } = useScope()
  return (
    <nav
      className={cn(
        'mb-6 flex min-w-0 items-center gap-2 overflow-hidden text-[10px] font-mono uppercase tracking-[0.2em] text-electric/75 sm:mb-8 sm:tracking-[0.28em]',
        className,
      )}
      aria-label="Breadcrumb"
    >
      <Link to={buildScopedPath('/')} className="hover:text-electric transition-colors">
        Matrix
      </Link>
      <span className="text-electric/25">//</span>
      <span className="text-ink-dim truncate max-w-[min(560px,60vw)]" title={playerName}>
        {playerName}
      </span>
    </nav>
  )
}
