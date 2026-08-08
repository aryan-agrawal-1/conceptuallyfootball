import { Activity, Map } from 'lucide-react'
import { cn } from '../../lib/utils'

export type ProfileContentTab = 'overview' | 'event-maps'

export function ProfileContentTabs({
  value,
  eventMapsAvailable,
  onChange,
}: {
  value: ProfileContentTab
  eventMapsAvailable: boolean
  onChange: (value: ProfileContentTab) => void
}) {
  return (
    <div className="mb-6 flex border-b border-line-bright" role="tablist" aria-label="Profile view">
      <button
        type="button"
        role="tab"
        aria-selected={value === 'overview'}
        onClick={() => onChange('overview')}
        className={cn(
          'relative flex min-h-11 items-center gap-2 px-4 text-[10px] font-bold uppercase tracking-[0.16em] transition-colors sm:px-5',
          value === 'overview' ? 'text-electric' : 'text-control-fg hover:text-ink',
        )}
      >
        <Activity size={14} /> Overview
        {value === 'overview' ? <span className="absolute inset-x-0 bottom-[-1px] h-0.5 bg-electric" /> : null}
      </button>
      {eventMapsAvailable ? (
        <button
          type="button"
          role="tab"
          aria-selected={value === 'event-maps'}
          onClick={() => onChange('event-maps')}
          className={cn(
            'relative flex min-h-11 items-center gap-2 px-4 text-[10px] font-bold uppercase tracking-[0.16em] transition-colors sm:px-5',
            value === 'event-maps' ? 'text-electric' : 'text-control-fg hover:text-ink',
          )}
        >
          <Map size={14} /> Event Maps
          {value === 'event-maps' ? <span className="absolute inset-x-0 bottom-[-1px] h-0.5 bg-electric" /> : null}
        </button>
      ) : null}
    </div>
  )
}
