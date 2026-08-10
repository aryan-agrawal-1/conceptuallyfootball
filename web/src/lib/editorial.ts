import type { SocialLinks } from './staffAuth'

export type ArticleStatus = 'draft'
export type CalloutTone = 'note' | 'insight' | 'warning'

interface BlockBase {
  id: string
}

export type ArticleBlock =
  | (BlockBase & { type: 'paragraph'; text: string })
  | (BlockBase & { type: 'heading'; level: 2 | 3; text: string })
  | (BlockBase & { type: 'quote'; text: string })
  | (BlockBase & { type: 'callout'; tone: CalloutTone; text: string })
  | (BlockBase & { type: 'bulleted_list' | 'numbered_list'; items: string[] })
  | (BlockBase & { type: 'link'; text: string; url: string })
  | (BlockBase & { type: 'image'; url: string; caption: string; alt: string })
  | (BlockBase & { type: 'divider' })

export interface ArticleDocument {
  version: 1
  blocks: ArticleBlock[]
}

export interface ArticleSummary {
  id: string
  title: string
  subtitle: string
  status: ArticleStatus
  revision: number
  preview_enabled: boolean
  created_at: string
  updated_at: string
}

export interface Article extends ArticleSummary {
  author: { id: number; display_name: string; social_links: SocialLinks }
  document: ArticleDocument
  preview_token: string | null
  revisions: { number: number; created_at: string }[]
}

export interface ArticleDraft {
  title: string
  subtitle: string
  document: ArticleDocument
}

export class EditorialApiError extends Error {
  code?: string
  errors: string[]
  article?: Article

  constructor(message: string, body: { code?: string; errors?: string[]; article?: Article } = {}) {
    super(message)
    this.name = 'EditorialApiError'
    this.code = body.code
    this.errors = body.errors ?? []
    this.article = body.article
  }
}

const PRIVATE_BASE = '/api/v1/private/editorial'
const PUBLIC_BASE = '/api/v1/analysis'

function cookieValue(name: string): string {
  const prefix = `${encodeURIComponent(name)}=`
  const cookie = document.cookie.split('; ').find(value => value.startsWith(prefix))
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : ''
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new EditorialApiError(
      body.detail ?? `Request failed with status ${response.status}.`,
      body,
    )
  }
  return body as T
}

async function csrfHeaders(): Promise<HeadersInit> {
  let token = cookieValue('csrftoken')
  if (!token) {
    const response = await fetch('/api/v1/auth/csrf', {
      credentials: 'same-origin',
      cache: 'no-store',
    })
    await responseJson(response)
    token = cookieValue('csrftoken')
  }
  return { 'Content-Type': 'application/json', 'X-CSRFToken': token }
}

async function privateRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = init.method ?? 'GET'
  const response = await fetch(`${PRIVATE_BASE}${path}`, {
    ...init,
    credentials: 'same-origin',
    cache: 'no-store',
    headers: method === 'GET' ? init.headers : await csrfHeaders(),
  })
  return responseJson<T>(response)
}

export async function listArticles(): Promise<ArticleSummary[]> {
  const body = await privateRequest<{ articles: ArticleSummary[] }>('/articles')
  return body.articles
}

export async function createArticle(): Promise<Article> {
  const body = await privateRequest<{ article: Article }>('/articles', {
    method: 'POST',
    body: JSON.stringify({ title: 'Untitled analysis' }),
  })
  return body.article
}

export async function getArticle(id: string): Promise<Article> {
  const body = await privateRequest<{ article: Article }>(`/articles/${id}`)
  return body.article
}

export async function saveArticle(id: string, draft: ArticleDraft, revision: number): Promise<Article> {
  const body = await privateRequest<{ article: Article }>(`/articles/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ ...draft, revision }),
  })
  return body.article
}

export async function deleteArticle(id: string): Promise<void> {
  await privateRequest(`/articles/${id}`, { method: 'DELETE' })
}

export async function setArticlePreview(
  id: string,
  enabled: boolean,
  rotate = false,
): Promise<Article> {
  const body = await privateRequest<{ article: Article }>(`/articles/${id}/preview`, {
    method: 'POST',
    body: JSON.stringify({ enabled, rotate }),
  })
  return body.article
}

export async function getSharedPreview(token: string): Promise<Article> {
  const response = await fetch(`${PUBLIC_BASE}/previews/${token}`, {
    cache: 'no-store',
    credentials: 'omit',
  })
  const body = await responseJson<{ article: Article }>(response)
  return body.article
}

export function newBlock(type: ArticleBlock['type']): ArticleBlock {
  const id = crypto.randomUUID()
  switch (type) {
    case 'heading':
      return { id, type, level: 2, text: '' }
    case 'quote':
    case 'paragraph':
      return { id, type, text: '' }
    case 'callout':
      return { id, type, tone: 'insight', text: '' }
    case 'bulleted_list':
    case 'numbered_list':
      return { id, type, items: ['', ''] }
    case 'link':
      return { id, type, text: '', url: '' }
    case 'image':
      return { id, type, url: '', caption: '', alt: '' }
    case 'divider':
      return { id, type }
  }
}

interface RecoveredDraft {
  schema: 1
  savedAt: string
  draft: ArticleDraft
}

function recoveryKey(articleId: string): string {
  return `cf-editorial-recovery-v1:${articleId}`
}

export function storeDraftRecovery(articleId: string, draft: ArticleDraft): void {
  const recovery: RecoveredDraft = { schema: 1, savedAt: new Date().toISOString(), draft }
  localStorage.setItem(recoveryKey(articleId), JSON.stringify(recovery))
}

export function loadDraftRecovery(articleId: string): RecoveredDraft | null {
  try {
    const recovery = JSON.parse(localStorage.getItem(recoveryKey(articleId)) ?? '') as RecoveredDraft
    if (recovery.schema !== 1 || !recovery.draft || recovery.draft.document.version !== 1) return null
    return recovery
  } catch {
    return null
  }
}

export function clearDraftRecovery(articleId: string): void {
  localStorage.removeItem(recoveryKey(articleId))
}
