import { useQuery } from '@tanstack/react-query'
import { AtSign, Focus, Newspaper, X } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { getRelatedAnalysis, type EditorialEntityKind, type RelatedAnalysisArticle } from '../../lib/editorial'


export function RelatedAnalysisButton({
  kind,
  entityId,
}: {
  kind: EditorialEntityKind
  entityId: number
}) {
  const [open, setOpen] = useState(false)
  const query = useQuery({
    queryKey: ['related-analysis', kind, entityId],
    queryFn: () => getRelatedAnalysis(kind, entityId),
    enabled: Number.isFinite(entityId) && entityId > 0,
    staleTime: 60_000,
  })
  const articleCount = (query.data?.subjects_of.length ?? 0) + (query.data?.referenced_by.length ?? 0)
  if (!articleCount || !query.data) return null

  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="ml-auto inline-flex h-8 items-center gap-2 whitespace-nowrap border border-electric/45 bg-electric/10 px-3 text-[10px] font-bold uppercase tracking-[0.14em] text-electric transition-colors hover:bg-electric/20 hover:text-ink">
        <Newspaper className="size-3.5" /> Analytical Articles <span className="font-mono text-[8px] opacity-70">{articleCount}</span>
      </button>
      {open ? <RelatedAnalysisModal entityName={query.data.entity.name} subjects={query.data.subjects_of} references={query.data.referenced_by} onClose={() => setOpen(false)} /> : null}
    </>
  )
}

function RelatedAnalysisModal({
  entityName,
  subjects,
  references,
  onClose,
}: {
  entityName: string
  subjects: RelatedAnalysisArticle[]
  references: RelatedAnalysisArticle[]
  onClose: () => void
}) {
  const [tab, setTab] = useState<'subjects' | 'references'>(subjects.length ? 'subjects' : 'references')
  const articles = tab === 'subjects' ? subjects : references

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-mat/90 p-4 backdrop-blur-sm" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <section role="dialog" aria-modal="true" aria-labelledby="analysis-modal-title" className="flex max-h-[min(760px,90svh)] w-full max-w-3xl flex-col border border-line-bright bg-panel shadow-2xl">
        <header className="flex items-start justify-between gap-6 border-b border-line px-5 py-5 sm:px-7">
          <div>
            <p className="font-mono text-[8px] uppercase tracking-[0.22em] text-electric">Analytical articles</p>
            <h2 id="analysis-modal-title" className="mt-2 text-2xl font-black tracking-[-0.035em] text-ink">{entityName}</h2>
          </div>
          <button type="button" onClick={onClose} className="grid size-9 shrink-0 place-items-center border border-line text-ink-muted hover:border-electric hover:text-electric" aria-label="Close analytical articles"><X className="size-4" /></button>
        </header>
        <div className="grid grid-cols-2 border-b border-line" role="tablist" aria-label="Article relationship">
          <TabButton active={tab === 'subjects'} icon={<Focus className="size-3.5" />} label="Subject of" count={subjects.length} onClick={() => setTab('subjects')} />
          <TabButton active={tab === 'references'} icon={<AtSign className="size-3.5" />} label="Referenced by" count={references.length} onClick={() => setTab('references')} />
        </div>
        <div className="overflow-y-auto p-5 sm:p-7">
          {articles.length ? (
            <div className="divide-y divide-line border-y border-line">
              {articles.map(article => (
                <Link key={article.id} to={`/articles/${article.id}`} onClick={onClose} className="group grid gap-3 py-5 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
                  <div>
                    <h3 className="text-lg font-black leading-tight tracking-[-0.025em] text-ink group-hover:text-electric">{article.title}</h3>
                    {article.subtitle ? <p className="mt-2 max-w-2xl text-xs leading-5 text-ink-dim">{article.subtitle}</p> : null}
                  </div>
                  <p className="font-mono text-[8px] uppercase tracking-[0.13em] text-ink-muted">By {article.author}{article.published_at ? ` · ${formatArticleDate(article.published_at)}` : ''}</p>
                </Link>
              ))}
            </div>
          ) : <p className="border border-dashed border-line px-5 py-12 text-center text-xs text-ink-muted">No published articles in this relationship.</p>}
        </div>
      </section>
    </div>
  )
}

function TabButton({ active, icon, label, count, onClick }: { active: boolean; icon: ReactNode; label: string; count: number; onClick: () => void }) {
  return <button type="button" role="tab" aria-selected={active} onClick={onClick} className={`flex h-12 items-center justify-center gap-2 border-b-2 font-mono text-[9px] font-bold uppercase tracking-[0.15em] ${active ? 'border-electric bg-electric/10 text-electric' : 'border-transparent text-ink-muted hover:text-ink'}`}>{icon}{label}<span className="opacity-60">{count}</span></button>
}

function formatArticleDate(value: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}
