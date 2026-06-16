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
  upsertMeta('meta[name="robots"]', { name: 'robots', content: 'index,follow' })
  upsertLink('link[rel="canonical"]', { rel: 'canonical', href: canonicalUrl })

  upsertMeta('meta[property="og:site_name"]', { property: 'og:site_name', content: SITE_NAME })
  upsertMeta('meta[property="og:type"]', { property: 'og:type', content: 'website' })
  upsertMeta('meta[property="og:title"]', { property: 'og:title', content: title })
  upsertMeta('meta[property="og:description"]', {
    property: 'og:description',
    content: description,
  })
  upsertMeta('meta[property="og:url"]', { property: 'og:url', content: canonicalUrl })
  upsertMeta('meta[property="og:image"]', { property: 'og:image', content: imageUrl })

  upsertMeta('meta[name="twitter:card"]', { name: 'twitter:card', content: 'summary' })
  upsertMeta('meta[name="twitter:title"]', { name: 'twitter:title', content: title })
  upsertMeta('meta[name="twitter:description"]', {
    name: 'twitter:description',
    content: description,
  })
  upsertMeta('meta[name="twitter:image"]', { name: 'twitter:image', content: imageUrl })
}

export function useSeoMeta({ title, description, canonicalPath, image }: SeoMeta) {
  useEffect(() => {
    applySeoMeta({ title, description, canonicalPath, image })
  }, [title, description, canonicalPath, image])
}

export const seoDefaults = {
  siteName: SITE_NAME,
  siteUrl: SITE_URL,
  title: DEFAULT_TITLE,
  description: DEFAULT_DESCRIPTION,
}
