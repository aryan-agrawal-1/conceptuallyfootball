import { useEffect } from 'react'

const SITE_NAME = 'Conceptually Football'
const SITE_URL = 'https://www.conceptuallyfootball.com'
const DEFAULT_TITLE = `${SITE_NAME} | Football Data & Analysis`
const DEFAULT_DESCRIPTION =
  'Conceptually Football is a football data and analysis platform for player stats, team stats, percentiles, comparisons, visualisations and scouting workflows.'

export interface SeoMeta {
  title?: string
  description?: string
  canonicalPath?: string
  image?: string
  robots?: string
  type?: 'website' | 'article'
  publishedTime?: string
  authorName?: string
  keywords?: string[]
  headline?: string
}

export function absoluteUrl(path = '/'): string {
  if (/^https?:\/\//.test(path)) return path
  const normalized = path.startsWith('/') ? path : `/${path}`
  return `${SITE_URL}${normalized}`
}

function upsertMeta(selector: string, attributes: Record<string, string>) {
  let element = document.head.querySelector<HTMLMetaElement>(selector)
  if (!element) {
    element = document.createElement('meta')
    document.head.appendChild(element)
  }
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, value)
  }
}

function upsertLink(selector: string, attributes: Record<string, string>) {
  let element = document.head.querySelector<HTMLLinkElement>(selector)
  if (!element) {
    element = document.createElement('link')
    document.head.appendChild(element)
  }
  for (const [key, value] of Object.entries(attributes)) {
    element.setAttribute(key, value)
  }
}

export function applySeoMeta(meta: SeoMeta) {
  const title = meta.title ?? DEFAULT_TITLE
  const description = meta.description ?? DEFAULT_DESCRIPTION
  const canonicalUrl = absoluteUrl(meta.canonicalPath ?? '/')
  const imageUrl = absoluteUrl(meta.image ?? '/favicon.svg')

  document.title = title
  upsertMeta('meta[name="description"]', { name: 'description', content: description })
  upsertMeta('meta[name="robots"]', {
    name: 'robots',
    content: meta.robots ?? 'index,follow',
  })
  upsertLink('link[rel="canonical"]', { rel: 'canonical', href: canonicalUrl })

  upsertMeta('meta[property="og:site_name"]', { property: 'og:site_name', content: SITE_NAME })
  upsertMeta('meta[property="og:type"]', { property: 'og:type', content: meta.type ?? 'website' })
  upsertMeta('meta[property="og:title"]', { property: 'og:title', content: title })
  upsertMeta('meta[property="og:description"]', {
    property: 'og:description',
    content: description,
  })
  upsertMeta('meta[property="og:url"]', { property: 'og:url', content: canonicalUrl })
  upsertMeta('meta[property="og:image"]', { property: 'og:image', content: imageUrl })

  upsertMeta('meta[name="twitter:card"]', { name: 'twitter:card', content: meta.image ? 'summary_large_image' : 'summary' })
  upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: title })
  upsertMeta('meta[name="twitter:description"]', {
    name: 'twitter:description',
    content: description,
  })
  upsertMeta('meta[name="twitter:image"]', { name: 'twitter:image', content: imageUrl })

  updateOptionalMeta('meta[property="article:published_time"]', meta.publishedTime, {
    property: 'article:published_time',
  })
  updateOptionalMeta('meta[name="author"]', meta.authorName, { name: 'author' })
  updateOptionalMeta('meta[name="keywords"]', meta.keywords?.join(', '), { name: 'keywords' })
  updateStructuredArticle(meta, canonicalUrl, imageUrl, title, description)
}

function updateOptionalMeta(
  selector: string,
  value: string | undefined,
  attributes: Record<string, string>,
) {
  if (!value) {
    document.head.querySelector(selector)?.remove()
    return
  }
  upsertMeta(selector, { ...attributes, content: value })
}

function updateStructuredArticle(
  meta: SeoMeta,
  canonicalUrl: string,
  imageUrl: string,
  title: string,
  description: string,
) {
  const existing = document.head.querySelector<HTMLScriptElement>('script[data-cf-article-jsonld]')
  if (meta.type !== 'article' || !meta.publishedTime || !meta.authorName) {
    existing?.remove()
    return
  }
  const script = existing ?? document.createElement('script')
  script.type = 'application/ld+json'
  script.dataset.cfArticleJsonld = ''
  script.textContent = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'Article',
    headline: meta.headline ?? title,
    description,
    datePublished: meta.publishedTime,
    author: { '@type': 'Person', name: meta.authorName },
    publisher: { '@type': 'Organization', name: SITE_NAME },
    mainEntityOfPage: canonicalUrl,
    image: imageUrl,
    keywords: meta.keywords,
  })
  if (!existing) document.head.appendChild(script)
}

export function useSeoMeta({ title, description, canonicalPath, image, robots, type, publishedTime, authorName, keywords, headline }: SeoMeta) {
  const keywordKey = keywords?.join('|')
  useEffect(() => {
    applySeoMeta({ title, description, canonicalPath, image, robots, type, publishedTime, authorName, keywords: keywordKey ? keywordKey.split('|') : undefined, headline })
  }, [title, description, canonicalPath, image, robots, type, publishedTime, authorName, keywordKey, headline])
}

export const seoDefaults = {
  siteName: SITE_NAME,
  siteUrl: SITE_URL,
  title: DEFAULT_TITLE,
  description: DEFAULT_DESCRIPTION,
}
