import { useQuery } from '@tanstack/react-query'
import { EyeOff, LockKeyhole } from 'lucide-react'
import type { ReactNode } from 'react'
import { useParams } from 'react-router-dom'
import { ArticleCanvas } from '../components/editorial/ArticleCanvas'
import { BRAND_LOGO_URL, BRAND_NAME } from '../lib/brand'
import { getSharedPreview } from '../lib/editorial'

export function ArticlePreview() {
  const { token = '' } = useParams()
  const previewQuery = useQuery({
    queryKey: ['editorial-preview', token],
    queryFn: () => getSharedPreview(token),
    enabled: Boolean(token),
    retry: false,
  })

  if (previewQuery.isLoading) {
    return <PreviewMessage icon={<LockKeyhole className="size-5 animate-pulse text-electric" />} title="Opening private preview" copy="Checking the review link…" />
  }
  if (previewQuery.isError || !previewQuery.data) {
    return <PreviewMessage icon={<EyeOff className="size-5 text-ember" />} title="This preview is unavailable" copy="The link may have been revoked or replaced by the writer." />
  }

  const article = previewQuery.data
  return (
    <main className="min-h-svh bg-mat">
      <div className="border-b border-gold/30 bg-gold-dim/35 px-5 py-2 text-center font-mono text-[8px] uppercase tracking-[0.18em] text-gold">Private draft · Not published · Do not index</div>
      <header className="border-b border-line px-6 py-5">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3"><img src={BRAND_LOGO_URL} alt="" className="size-7 object-contain" /><span className="text-[10px] font-black uppercase tracking-[0.16em] text-ink">{BRAND_NAME}</span></div>
          <span className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.17em] text-ink-muted"><LockKeyhole className="size-3.5" /> Review copy</span>
        </div>
      </header>
      <ArticleCanvas title={article.title} subtitle={article.subtitle} document={article.document} author={article.author} updatedAt={article.updated_at} preview />
    </main>
  )
}

function PreviewMessage({ icon, title, copy }: { icon: ReactNode; title: string; copy: string }) {
  return <main className="grid min-h-svh place-items-center bg-mat px-6 text-center"><div>{icon && <div className="flex justify-center">{icon}</div>}<h1 className="mt-5 text-2xl font-black tracking-[-0.035em] text-ink">{title}</h1><p className="mt-2 text-sm text-ink-dim">{copy}</p></div></main>
}
