import { ArrowDown, ArrowUp, GripVertical, Plus, Trash2 } from 'lucide-react'
import type { ReactElement } from 'react'
import type { ArticleBlock } from '../../lib/editorial'

const fieldClass = 'w-full resize-none bg-transparent text-ink placeholder:text-ink-muted focus:outline-none'
const metaInputClass = 'h-9 w-full border border-line bg-mat px-3 text-xs text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none'

export function BlockEditor({
  block,
  index,
  total,
  onChange,
  onMove,
  onRemove,
}: {
  block: ArticleBlock
  index: number
  total: number
  onChange: (block: ArticleBlock) => void
  onMove: (direction: -1 | 1) => void
  onRemove: () => void
}) {
  return (
    <section className="group relative -mx-4 border border-transparent px-4 py-2 transition-colors hover:border-line hover:bg-panel/45 focus-within:border-line-bright focus-within:bg-panel/65">
      <div className="absolute -left-11 top-2 hidden w-9 flex-col items-center border border-line bg-panel py-1 group-hover:flex group-focus-within:flex lg:flex lg:opacity-0 lg:group-hover:opacity-100 lg:group-focus-within:opacity-100">
        <GripVertical className="mb-1 size-3.5 text-ink-muted" />
        <BlockAction label="Move up" disabled={index === 0} onClick={() => onMove(-1)}><ArrowUp /></BlockAction>
        <BlockAction label="Move down" disabled={index === total - 1} onClick={() => onMove(1)}><ArrowDown /></BlockAction>
        <BlockAction label="Delete block" onClick={onRemove} destructive><Trash2 /></BlockAction>
      </div>
      <BlockFields block={block} onChange={onChange} />
    </section>
  )
}

function BlockFields({ block, onChange }: { block: ArticleBlock; onChange: (block: ArticleBlock) => void }) {
  switch (block.type) {
    case 'heading':
      return (
        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="font-mono text-[8px] uppercase tracking-[0.18em] text-ink-muted">Heading</span>
            <select
              value={block.level}
              onChange={event => onChange({ ...block, level: Number(event.target.value) as 2 | 3 })}
              className="bg-transparent font-mono text-[8px] uppercase text-electric focus:outline-none"
              aria-label="Heading level"
            >
              <option value={2}>H2</option>
              <option value={3}>H3</option>
            </select>
          </div>
          <textarea
            value={block.text}
            onChange={event => onChange({ ...block, text: event.target.value })}
            rows={block.level === 2 ? 2 : 1}
            placeholder={block.level === 2 ? 'Section heading' : 'Subheading'}
            className={`${fieldClass} ${block.level === 2 ? 'text-2xl font-black leading-tight tracking-[-0.035em] sm:text-3xl' : 'text-xl font-bold tracking-[-0.025em]'}`}
          />
        </div>
      )
    case 'paragraph':
      return <textarea value={block.text} onChange={event => onChange({ ...block, text: event.target.value })} rows={4} placeholder="Write the next thought…" className={`${fieldClass} text-[15px] leading-8 text-ink-dim`} />
    case 'quote':
      return (
        <div className="border-l-2 border-electric py-2 pl-6">
          <textarea value={block.text} onChange={event => onChange({ ...block, text: event.target.value })} rows={3} placeholder="A telling line or key conclusion…" className={`${fieldClass} text-xl font-semibold leading-8 tracking-[-0.02em]`} />
        </div>
      )
    case 'callout':
      return (
        <div className={`border p-5 ${block.tone === 'warning' ? 'border-gold/40 bg-gold-dim/35' : 'border-electric/35 bg-electric-dim/35'}`}>
          <select value={block.tone} onChange={event => onChange({ ...block, tone: event.target.value as typeof block.tone })} className="mb-3 bg-transparent font-mono text-[8px] uppercase tracking-[0.18em] text-electric focus:outline-none" aria-label="Callout tone">
            <option value="insight">Key insight</option>
            <option value="note">Note</option>
            <option value="warning">Caveat</option>
          </select>
          <textarea value={block.text} onChange={event => onChange({ ...block, text: event.target.value })} rows={3} placeholder="Give this observation extra weight…" className={`${fieldClass} text-sm leading-6`} />
        </div>
      )
    case 'bulleted_list':
    case 'numbered_list':
      return (
        <div className="space-y-3">
          {block.items.map((item, itemIndex) => (
            <div key={`${block.id}-${itemIndex}`} className="flex items-start gap-3">
              <span className="mt-2.5 w-4 shrink-0 text-right font-mono text-[9px] text-electric">{block.type === 'numbered_list' ? `${itemIndex + 1}.` : '•'}</span>
              <textarea
                value={item}
                onChange={event => {
                  const items = [...block.items]
                  items[itemIndex] = event.target.value
                  onChange({ ...block, items })
                }}
                rows={2}
                placeholder="List item"
                className={`${fieldClass} text-[15px] leading-7 text-ink-dim`}
              />
              {block.items.length > 1 ? (
                <button type="button" onClick={() => onChange({ ...block, items: block.items.filter((_, index) => index !== itemIndex) })} className="mt-1 p-1.5 text-ink-muted hover:text-ember" aria-label={`Delete list item ${itemIndex + 1}`}><Trash2 className="size-3.5" /></button>
              ) : null}
            </div>
          ))}
          <button type="button" onClick={() => onChange({ ...block, items: [...block.items, ''] })} className="ml-7 inline-flex items-center gap-2 text-[9px] font-bold uppercase tracking-[0.15em] text-ink-muted hover:text-electric"><Plus className="size-3.5" /> Add item</button>
        </div>
      )
    case 'link':
      return (
        <div className="grid gap-3 sm:grid-cols-[1fr_1.3fr]">
          <label className="space-y-1.5"><FieldLabel>Link label</FieldLabel><input value={block.text} onChange={event => onChange({ ...block, text: event.target.value })} placeholder="Further reading" className={metaInputClass} /></label>
          <label className="space-y-1.5"><FieldLabel>HTTPS URL</FieldLabel><input type="url" value={block.url} onChange={event => onChange({ ...block, url: event.target.value })} placeholder="https://…" className={metaInputClass} /></label>
        </div>
      )
    case 'image':
      return (
        <div className="space-y-3 border border-line bg-mat p-4">
          {block.url ? <img src={block.url} alt={block.alt} className="max-h-96 w-full object-contain" /> : <div className="grid aspect-[16/7] place-items-center border border-dashed border-line-bright text-[10px] uppercase tracking-[0.16em] text-ink-muted">Paste a public image URL below</div>}
          <label className="block space-y-1.5"><FieldLabel>Image URL</FieldLabel><input type="url" value={block.url} onChange={event => onChange({ ...block, url: event.target.value })} placeholder="https://…" className={metaInputClass} /></label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5"><FieldLabel>Caption</FieldLabel><input value={block.caption} onChange={event => onChange({ ...block, caption: event.target.value })} placeholder="Source or context" className={metaInputClass} /></label>
            <label className="space-y-1.5"><FieldLabel>Alt text</FieldLabel><input value={block.alt} onChange={event => onChange({ ...block, alt: event.target.value })} placeholder="Describe the image" className={metaInputClass} /></label>
          </div>
        </div>
      )
    case 'divider':
      return <div className="py-7"><hr className="border-0 border-t border-line" /></div>
  }
}

function FieldLabel({ children }: { children: string }) {
  return <span className="block font-mono text-[8px] uppercase tracking-[0.16em] text-ink-muted">{children}</span>
}

function BlockAction({ children, label, onClick, disabled = false, destructive = false }: { children: ReactElement<{ className?: string }>; label: string; onClick: () => void; disabled?: boolean; destructive?: boolean }) {
  return <button type="button" onClick={onClick} disabled={disabled} className={`p-1.5 disabled:opacity-25 ${destructive ? 'text-ink-muted hover:text-ember' : 'text-ink-muted hover:text-electric'}`} aria-label={label}>{children && <span className="[&>svg]:size-3.5">{children}</span>}</button>
}
