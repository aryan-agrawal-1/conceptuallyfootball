import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, ArrowRight, FileText } from 'lucide-react'
import { Link, Navigate, useParams } from 'react-router-dom'
import { ArticleCanvas } from '../components/editorial/ArticleCanvas'
import { getPublishedArticle } from '../lib/editorial'
import { useSeoMeta } from '../lib/seo'


export function PublishedArticle() {
  const { slug = '' } = useParams()
  const articleQuery = useQuery({
    queryKey: ['published-article', slug],
    queryFn: () => getPublishedArticle(slug),
    enabled: Boolean(slug),
    retry: false,
  })
  const article = articleQuery.data

  useSeoMeta({
    title: article ? `${article.title} | Conceptually Football` : 'Analysis | Conceptually Football',
    description: article?.subtitle || 'Football analysis from Conceptually Football.',
    canonicalPath: article?.canonical_path ?? `/articles/${slug}`,
    image: article?.social_image ?? undefined,
    robots: article ? 'index,follow' : 'noindex,nofollow',
    type: article ? 'article' : 'website',
    publishedTime: article?.published_at,
    authorName: article?.author.display_name,
    keywords: article?.topics,
    headline: article?.title,
  })

  if (articleQuery.isLoading) {
    return <ArticleMessage>Loading analysis…</ArticleMessage>
  }
  if (articleQuery.isError || !article) {
    return <ArticleMessage unavailable>This analysis is unavailable or no longer published.</ArticleMessage>
  }
  if (slug !== article.slug) return <Navigate to={article.canonical_path} replace />

  return (
    <div className="min-h-svh bg-mat">
      <div className="mx-auto flex w-full max-w-[1440px] items-center justify-between gap-4 px-6 pt-8">
        <Link to="/articles" className="inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-muted hover:text-electric"><ArrowLeft className="size-3.5" /> All analysis</Link>
        <Link to="/" className="hidden items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-muted hover:text-electric sm:inline-flex">Explore the data <ArrowRight className="size-3.5" /></Link>
      </div>
      <ArticleCanvas title={article.title} subtitle={article.subtitle} document={article.document} author={article.author} updatedAt={article.published_at} subjects={article.subjects} references={article.references} topics={article.topics} sourceNotes={article.source_notes} readingMinutes={article.reading_minutes} published />
      <aside className="mx-auto mb-16 grid w-[calc(100%-3rem)] max-w-[1050px] gap-6 border-y border-line py-8 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <div><p className="font-mono text-[8px] uppercase tracking-[0.18em] text-electric">Keep exploring</p><p className="mt-2 text-sm leading-6 text-ink-dim">Follow the tagged players and teams into their statistical profiles, or browse another line of analysis.</p></div>
        <Link to="/articles" className="inline-flex h-10 items-center justify-center gap-2 border border-electric/45 px-4 font-mono text-[8px] uppercase tracking-[0.15em] text-electric hover:bg-electric hover:text-mat">Browse analysis <ArrowRight className="size-3.5" /></Link>
      </aside>
    </div>
  )
}

function ArticleMessage({ children, unavailable = false }: { children: string; unavailable?: boolean }) {
  return <div className="grid min-h-[70svh] place-items-center px-6 text-center"><div><FileText className={`mx-auto size-7 ${unavailable ? 'text-ember' : 'animate-pulse text-electric'}`} /><p className="mt-4 text-sm text-ink-dim">{children}</p>{unavailable ? <Link to="/articles" className="mt-5 inline-block text-xs font-bold text-electric">Back to all analysis</Link> : null}</div></div>
}
