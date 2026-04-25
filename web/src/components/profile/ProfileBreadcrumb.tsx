import { Link } from 'react-router-dom'
import { cn } from '../../lib/utils'

interface ProfileBreadcrumbProps {
  playerName: string
  className?: string
}

export function ProfileBreadcrumb({ playerName, className }: ProfileBreadcrumbProps) {
  return (
    <nav
      className={cn(
        'flex items-center gap-2 text-[10px] font-mono uppercase tracking-[0.28em] text-electric/75 mb-8',
        className,
      )}
      aria-label="Breadcrumb"
    >
      <Link to="/" className="hover:text-electric transition-colors">
        Matrix
      </Link>
      <span className="text-electric/25">//</span>
      <span className="text-ink-dim truncate max-w-[min(560px,60vw)]" title={playerName}>
        {playerName}
      </span>
    </nav>
  )
}
