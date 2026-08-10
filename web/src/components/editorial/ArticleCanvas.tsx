import { ImageIcon, Lightbulb, TriangleAlert } from 'lucide-react'
import type { Article, ArticleBlock, ArticleDocument, InlineContent } from '../../lib/editorial'
import type { SocialPlatform } from '../../lib/staffAuth'
import { SocialBrandIcon } from '../social/SocialBrandIcon'

export function ArticleCanvas({
  title,
  subtitle,
  document,
  author,
  updatedAt,
  preview = false,
}: {
  title: string
  subtitle: string
  document: ArticleDocument
  author?: Article['author']
  updatedAt?: string
  preview?: boolean
}) {
  return (
    <article className="mx-auto w-full max-w-[1180px] px-6 py-14 sm:px-10 sm:py-20 lg:px-16">
      <header className="border-b border-line pb-10">
        <p className="font-mono text-[9px] uppercase tracking-[0.25em] text-electric">
          {preview ? 'Private editorial preview' : 'Analysis draft'}
        </p>
        <h1 className="mt-5 text-4xl font-black leading-[1.04] tracking-[-0.05em] text-ink sm:text-6xl">
          {title.trim() || 'Untitled analysis'}
        </h1>
        {subtitle ? (
          <p className="mt-6 text-base leading-7 text-ink-dim sm:text-lg">{subtitle}</p>
        ) : null}
        {author ? <AuthorByline author={author} updatedAt={updatedAt} /> : null}
      </header>
      <div className="space-y-7 pt-10">
        {document.blocks.map(block => (
          <RenderedBlock key={block.id} block={block} />
        ))}
      </div>
    </article>
  )
}

const SOCIAL_LABELS: Record<SocialPlatform, string> = {
  x: 'X',
  instagram: 'Instagram',
  discord: 'Discord',
  bluesky: 'Bluesky',
  youtube: 'YouTube',
  website: 'Website',
}

function AuthorByline({ author, updatedAt }: { author: Article['author']; updatedAt?: string }) {
  const socialEntries = Object.entries(author.social_links) as Array<[SocialPlatform, string]>
  return (
    <div className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[9px] uppercase tracking-[0.18em] text-ink-muted">
      <span>By {author.display_name}</span>
      {socialEntries.length ? <div className="flex overflow-hidden border border-line-bright bg-panel/60">{socialEntries.map(([platform, url]) => <a key={platform} href={url} target="_blank" rel="me noreferrer" title={SOCIAL_LABELS[platform]} aria-label={`${author.display_name} on ${SOCIAL_LABELS[platform]}`} className="grid size-7 place-items-center border-r border-line-bright text-ink-muted transition-colors last:border-r-0 hover:bg-electric hover:text-mat focus-visible:bg-electric focus-visible:text-mat focus-visible:outline-none"><SocialBrandIcon platform={platform} className="size-3.5" /></a>)}</div> : null}
      {updatedAt ? <><span aria-hidden="true" className="text-line-bright">·</span><span>Updated {formatPreviewDate(updatedAt)}</span></> : null}
    </div>
  )
}

function RenderedBlock({ block }: { block: ArticleBlock }) {
  switch (block.type) {
    case 'heading':
      return block.level === 2 ? (
        <h2 className="pt-5 text-2xl font-black leading-tight tracking-[-0.035em] text-ink sm:text-3xl">
          <InlineText content={block.content} fallback="Section heading" />
        </h2>
      ) : (
        <h3 className="pt-3 text-xl font-bold tracking-[-0.025em] text-ink">
          <InlineText content={block.content} fallback="Subheading" />
        </h3>
      )
    case 'paragraph':
      return <p className="whitespace-pre-wrap text-[15px] leading-8 text-ink-dim"><InlineText content={block.content} /></p>
    case 'quote':
      return (
        <blockquote className="border-l-2 border-electric py-2 pl-6 text-xl font-semibold leading-8 tracking-[-0.02em] text-ink">
          <InlineText content={block.content} />
        </blockquote>
      )
    case 'callout': {
      const warning = block.tone === 'warning'
      return (
        <aside className={`border p-5 ${warning ? 'border-gold/40 bg-gold-dim/35' : 'border-electric/35 bg-electric-dim/35'}`}>
          <div className="flex items-start gap-3">
            {warning ? <TriangleAlert className="mt-0.5 size-4 shrink-0 text-gold" /> : <Lightbulb className="mt-0.5 size-4 shrink-0 text-electric" />}
            <p className="whitespace-pre-wrap text-sm leading-6 text-ink"><InlineText content={block.content} /></p>
          </div>
        </aside>
      )
    }
    case 'bulleted_list':
    case 'numbered_list': {
      const List = block.type === 'numbered_list' ? 'ol' : 'ul'
      return (
        <List className={`space-y-3 pl-6 text-[15px] leading-7 text-ink-dim ${block.type === 'numbered_list' ? 'list-decimal' : 'list-disc marker:text-electric'}`}>
          {block.items.map((item, index) => <li key={`${block.id}-${index}`}><InlineText content={item} /></li>)}
        </List>
      )
    }
    case 'image':
      return (
        <figure>
          {safeExternalUrl(block.url) ? (
            <img src={safeExternalUrl(block.url)} alt={block.alt} className="max-h-[560px] w-full border border-line object-contain" loading="lazy" />
          ) : (
            <div className="grid aspect-[16/9] place-items-center border border-dashed border-line-bright bg-panel text-ink-muted">
              <span className="flex items-center gap-2 text-xs uppercase tracking-[0.15em]"><ImageIcon className="size-4" /> Image URL not set</span>
            </div>
          )}
          {block.caption ? <figcaption className="mt-3 text-center font-mono text-[9px] leading-5 text-ink-muted">{block.caption}</figcaption> : null}
        </figure>
      )
    case 'divider':
      return <hr className="my-12 border-0 border-t border-line" />
  }
}

function InlineText({ content, fallback = '' }: { content: InlineContent; fallback?: string }) {
  if (!content.some(run => run.text)) return fallback
  return content.map((run, index) => {
    const url = run.link ? safeExternalUrl(run.link) : ''
    return url ? <a key={index} href={url} target="_blank" rel="noreferrer" className="border-b border-electric/60 text-electric hover:text-ink">{run.text}</a> : <span key={index}>{run.text}</span>
  })
}

function formatPreviewDate(value: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}

function safeExternalUrl(value: string): string {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}
