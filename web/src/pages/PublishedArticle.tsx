import { useQuery } from '@tanstack/react-query'
import { ArrowLeft, FileText } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { ArticleCanvas } from '../components/editorial/ArticleCanvas'
import { getPublishedArticle } from '../lib/editorial'
import { useSeoMeta } from '../lib/seo'


export function PublishedArticle() {
  const { articleId = '' } = useParams()
  const articleQuery = useQuery({
    queryKey: ['published-article', articleId],
    queryFn: () => getPublishedArticle(articleId),
    enabled: Boolean(articleId),
    retry: false,
  })
  const article = articleQuery.data

  useSeoMeta({
    title: article ? `${article.title} | Conceptually Football` : 'Analysis | Conceptually Football',
    description: article?.subtitle || 'Football analysis from Conceptually Football.',
    canonicalPath: `/articles/${articleId}`,
    robots: 'index,follow',
  })

  if (articleQuery.isLoading) {
    return <ArticleMessage>Loading analysis…</ArticleMessage>
  }
  if (articleQuery.isError || !article) {
    return <ArticleMessage unavailable>This analysis is unavailable or no longer published.</ArticleMessage>
  }

  return (
    <div className="min-h-svh bg-mat">
      <div className="mx-auto flex w-full max-w-[1440px] px-6 pt-8">
        <Link to="/" className="inline-flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.16em] text-ink-muted hover:text-electric"><ArrowLeft className="size-3.5" /> Explore football data</Link>
      </div>
      <ArticleCanvas title={article.title} subtitle={article.subtitle} document={article.document} author={article.author} updatedAt={article.published_at} subjects={article.subjects} references={article.references} />
    </div>
  )
}

function ArticleMessage({ children, unavailable = false }: { children: string; unavailable?: boolean }) {
  return <div className="grid min-h-[70svh] place-items-center px-6 text-center"><div><FileText className={`mx-auto size-7 ${unavailable ? 'text-ember' : 'animate-pulse text-electric'}`} /><p className="mt-4 text-sm text-ink-dim">{children}</p>{unavailable ? <Link to="/" className="mt-5 inline-block text-xs font-bold text-electric">Back to the data matrix</Link> : null}</div></div>
}
