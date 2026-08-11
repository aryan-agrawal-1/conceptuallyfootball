import { useQuery } from '@tanstack/react-query'
import { AtSign, Focus } from 'lucide-react'
import type { ReactNode } from 'react'
import { getRelatedAnalysis, type EditorialEntityKind, type RelatedAnalysisArticle } from '../../lib/editorial'

export function RelatedAnalysisSections({
  kind,
  entityId,
}: {
  kind: EditorialEntityKind
  entityId: number
}) {
  const query = useQuery({
    queryKey: ['related-analysis', kind, entityId],
    queryFn: () => getRelatedAnalysis(kind, entityId),
    enabled: Number.isFinite(entityId) && entityId > 0,
    staleTime: 60_000,
  })
  if (!query.data || (!query.data.subjects_of.length && !query.data.referenced_by.length)) return null
  return (
    <section className="mt-10 border-t border-line pt-8" aria-labelledby="related-analysis-heading">
      <div className="mb-5">
        <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-electric">Editorial analysis</p>
        <h2 id="related-analysis-heading" className="mt-2 text-2xl font-black tracking-[-0.035em] text-ink">Read with context.</h2>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <AnalysisGroup title="Subjects of" description="Analysis principally about this profile." icon={<Focus className="size-4" />} articles={query.data.subjects_of} />
        <AnalysisGroup title="Referenced by" description="Analysis where this profile appears as supporting context." icon={<AtSign className="size-4" />} articles={query.data.referenced_by} />
      </div>
    </section>
  )
}

function AnalysisGroup({
  title,
  description,
  icon,
  articles,
}: {
  title: string
  description: string
  icon: ReactNode
  articles: RelatedAnalysisArticle[]
}) {
  return (
    <div className="border border-line bg-panel/45 p-5">
      <div className="flex items-center gap-2 text-electric">{icon}<h3 className="font-mono text-[9px] font-bold uppercase tracking-[0.18em]">{title}</h3></div>
      <p className="mt-2 text-[11px] leading-5 text-ink-muted">{description}</p>
      {articles.length ? <div className="mt-5 space-y-4">{articles.map(article => <article key={article.id} className="border-l border-line-bright pl-3"><h4 className="text-sm font-bold leading-5 text-ink">{article.title}</h4>{article.subtitle ? <p className="mt-1 line-clamp-2 text-[11px] leading-5 text-ink-dim">{article.subtitle}</p> : null}<p className="mt-2 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">By {article.author}</p></article>)}</div> : <p className="mt-5 border border-dashed border-line px-3 py-5 text-center text-[10px] text-ink-muted">No published analysis yet.</p>}
    </div>
  )
}
