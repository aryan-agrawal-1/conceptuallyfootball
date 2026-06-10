import type { ReactNode } from 'react'
import { Download, Link2, Share2 } from 'lucide-react'
import { HudActionButton } from '../hud/Hud'
import { cn } from '../../lib/utils'

export type ShareActionBusy = 'share' | 'download' | 'copy' | null

interface ShareActionsProps {
  busy: ShareActionBusy
  disabled?: boolean
  disabledReason?: string | null
  onShare?: () => void
  onDownload?: () => void
  onCopyLink?: () => void
  className?: string
  compact?: boolean
}

export function ShareActions({
  busy,
  disabled = false,
  disabledReason,
  onShare,
  onDownload,
  onCopyLink,
  className,
  compact = false,
}: ShareActionsProps) {
  const isDisabled = disabled || busy != null
  const primaryLabel = busy === 'share' ? 'Preparing...' : 'Share'
  const downloadLabel = busy === 'download' ? 'Rendering...' : 'Download PNG'
  const copyLabel = busy === 'copy' ? 'Copying...' : 'Copy Link'
  const title = disabledReason ?? undefined

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      {onShare && (
        <HudActionButton
          onClick={onShare}
          disabled={isDisabled}
          title={title}
          className={cn(compact ? 'px-3 py-2 text-[11px]' : 'px-4 py-2.5')}
        >
          <Share2 className="size-3.5" />
          {primaryLabel}
        </HudActionButton>
      )}
      {onDownload && (
        <ShareSecondaryButton
          onClick={onDownload}
          disabled={isDisabled}
          title={title}
          compact={compact}
        >
          <Download className="size-3.5" />
          {downloadLabel}
        </ShareSecondaryButton>
      )}
      {onCopyLink && (
        <ShareSecondaryButton
          onClick={onCopyLink}
          disabled={isDisabled}
          title={title}
          compact={compact}
        >
          <Link2 className="size-3.5" />
          {copyLabel}
        </ShareSecondaryButton>
      )}
    </div>
  )
}

function ShareSecondaryButton({
  children,
  onClick,
  disabled,
  title,
  compact,
}: {
  children: ReactNode
  onClick: () => void
  disabled: boolean
  title?: string
  compact: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={cn(
        'relative flex items-center gap-1.5 border border-electric/15 text-[11px] font-medium uppercase tracking-[0.15em] text-ink-muted transition-colors hover:border-electric/40 hover:text-electric/80',
        compact ? 'px-3 py-2' : 'px-4 py-2.5',
        disabled && 'pointer-events-none opacity-40',
      )}
    >
      {children}
    </button>
  )
}
