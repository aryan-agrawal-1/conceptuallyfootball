import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, AtSign, Focus } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
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
  const data = query.data
  const articleCount = (data?.subjects_of.length ?? 0) + (data?.referenced_by.length ?? 0)
  if (!data || !articleCount) return null

  return (
    <section aria-labelledby={`${kind}-analysis-heading`} className="border-t border-line pt-8">
      <div className="grid gap-5 sm:grid-cols-[minmax(0,1fr)_minmax(180px,320px)] sm:items-end">
        <div>
          <p className="font-mono text-[8px] uppercase tracking-[0.2em] text-electric">Editorial coverage</p>
          <h2 id={`${kind}-analysis-heading`} className="mt-2 text-2xl font-black tracking-[-0.04em] text-ink">Analysis involving {data.entity.name}</h2>
        </div>
        <p className="text-[11px] leading-5 text-ink-muted">Primary subject coverage is kept separate from incidental references, so prominence reflects the article’s actual focus.</p>
      </div>
      <div className="mt-6 grid gap-px bg-line lg:grid-cols-2">
        <RelationshipColumn icon={<Focus className="size-3.5" />} label="Subjects of" description="Articles primarily about this profile" articles={data.subjects_of} />
        <RelationshipColumn icon={<AtSign className="size-3.5" />} label="Referenced by" description="Articles where this profile adds context" articles={data.referenced_by} />
      </div>
    </section>
  )
}

function RelationshipColumn({ icon, label, description, articles }: { icon: ReactNode; label: string; description: string; articles: RelatedAnalysisArticle[] }) {
  return (
    <div className="bg-mat p-5 sm:p-6">
      <div className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.17em] text-electric">{icon}{label}<span className="text-ink-muted">{articles.length}</span></div>
      <p className="mt-2 text-[10px] text-ink-muted">{description}</p>
      {articles.length ? (
        <div className="mt-5 divide-y divide-line border-y border-line">
          {articles.map(article => (
            <Link key={article.id} to={article.canonical_path} className="group flex items-start justify-between gap-4 py-4">
              <div className="min-w-0">
                <h3 className="text-sm font-black leading-5 tracking-[-0.02em] text-ink group-hover:text-electric">{article.title}</h3>
                <p className="mt-2 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">By {article.author} · {formatArticleDate(article.published_at)} · {article.reading_minutes} min</p>
              </div>
              <ArrowUpRight className="mt-0.5 size-4 shrink-0 text-electric transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
            </Link>
          ))}
        </div>
      ) : <p className="mt-5 border border-dashed border-line px-4 py-7 text-center text-[10px] text-ink-muted">No published articles in this relationship.</p>}
    </div>
  )
}

function formatArticleDate(value: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}
