import type { SocialLinks } from './staffAuth'

export type ArticleStatus = 'draft'
export type CalloutTone = 'note' | 'insight' | 'warning'

interface BlockBase {
  id: string
}

export interface InlineRun {
  text: string
  link?: string
}

export type InlineContent = InlineRun[]

export type VisualBlockType =
  | 'similar_players'
  | 'player_radar'
  | 'stat_card'
  | 'player_comparison'
  | 'custom_chart'

export type VisualEntityKind = 'player' | 'team'
export type VisualChartType = 'scatter' | 'bar' | 'radar' | 'dumbbell' | 'table'
export type VisualScopeKind = 'competition' | 'league' | 'big5' | 'all'

export interface VisualEntityReference {
  kind: VisualEntityKind
  id: number
  name: string
  source_competition: string
  season_label: string
  competition_season_id: number
  position_group?: 'FWD' | 'MID' | 'DEF' | 'GK' | 'UNK'
  team_name?: string
}

export interface VisualBlockConfig {
  entity_kind: VisualEntityKind
  entities: VisualEntityReference[]
  context: {
    scope_kind: VisualScopeKind
    scope_code: string
    scope_label: string
    season_label: string
  }
  chart_type: VisualChartType
  metric_keys: string[]
  rate_mode: 'per90' | 'full'
  filters: {
    position_group: 'ALL' | 'FWD' | 'MID' | 'DEF' | 'GK'
    team_names: string[]
    minimum_minutes: number
    labels: boolean
    trendline: boolean
    bar_window: 'top' | 'bottom' | 'all'
    bar_count: number
  }
}

export interface VisualArticleBlock extends BlockBase {
  type: 'visual'
  visual_type: VisualBlockType
  title: string
  caption: string
  alt: string
  source_note: string
  data_as_of: string
  update_policy: 'live_draft_freeze_on_publish' | 'frozen'
  config: VisualBlockConfig
}

export type ArticleBlock =
  | (BlockBase & { type: 'paragraph'; content: InlineContent })
  | (BlockBase & { type: 'heading'; level: 2 | 3; content: InlineContent })
  | (BlockBase & { type: 'quote'; content: InlineContent })
  | (BlockBase & { type: 'callout'; tone: CalloutTone; content: InlineContent })
  | (BlockBase & { type: 'bulleted_list' | 'numbered_list'; items: InlineContent[] })
  | (BlockBase & { type: 'image'; url: string; caption: string; alt: string })
  | VisualArticleBlock
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

export interface ArticleRevision {
  number: number
  title: string
  subtitle: string
  document: ArticleDocument
  created_at: string
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

export async function getArticleRevision(id: string, revision: number): Promise<ArticleRevision> {
  const body = await privateRequest<{ revision: ArticleRevision }>(`/articles/${id}/revisions/${revision}`)
  return body.revision
}

export async function saveArticle(id: string, draft: ArticleDraft, revision: number, createRevision = false): Promise<Article> {
  const body = await privateRequest<{ article: Article }>(`/articles/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ ...draft, revision, create_revision: createRevision }),
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
      return { id, type, level: 2, content: inlineText('') }
    case 'quote':
    case 'paragraph':
      return { id, type, content: inlineText('') }
    case 'callout':
      return { id, type, tone: 'insight', content: inlineText('') }
    case 'bulleted_list':
    case 'numbered_list':
      return { id, type, items: [inlineText('')] }
    case 'image':
      return { id, type, url: '', caption: '', alt: '' }
    case 'visual':
      return { ...newVisualBlock('custom_chart'), id }
    case 'divider':
      return { id, type }
  }
}

export function newVisualBlock(visualType: VisualBlockType): VisualArticleBlock {
  return {
    id: crypto.randomUUID(),
    type: 'visual',
    visual_type: visualType,
    title: '',
    caption: '',
    alt: '',
    source_note: 'Conceptually Football',
    data_as_of: new Date().toISOString().slice(0, 10),
    update_policy: 'live_draft_freeze_on_publish',
    config: {
      entity_kind: 'player',
      entities: [],
      context: { scope_kind: 'league', scope_code: '', scope_label: '', season_label: '' },
      chart_type: visualType === 'custom_chart' ? 'scatter' : 'radar',
      metric_keys: [],
      rate_mode: 'per90',
      filters: { position_group: 'ALL', team_names: [], minimum_minutes: 450, labels: true, trendline: false, bar_window: 'top', bar_count: 12 },
    },
  }
}

export function inlineText(text: string): InlineContent {
  return [{ text }]
}

export function plainText(content: InlineContent): string {
  return content.map(run => run.text).join('')
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
    return { ...recovery, draft: { ...recovery.draft, document: upgradeDocument(recovery.draft.document) } }
  } catch {
    return null
  }
}

function upgradeDocument(document: ArticleDocument): ArticleDocument {
  const legacyBlocks = document.blocks as Array<ArticleBlock & { text?: string; url?: string; items?: Array<string | InlineContent> }>
  return {
    version: 1,
    blocks: legacyBlocks.map(block => {
      if (block.type === 'heading' || block.type === 'paragraph' || block.type === 'quote' || block.type === 'callout') {
        return { ...block, content: block.content ?? inlineText(block.text ?? '') }
      }
      if (block.type === 'bulleted_list' || block.type === 'numbered_list') {
        return { ...block, items: (block.items ?? []).map(item => typeof item === 'string' ? inlineText(item) : item) }
      }
      if ((block as { type: string }).type === 'link') {
        const legacy = block as unknown as { id: string; text?: string; url?: string }
        return { id: legacy.id, type: 'paragraph', content: [{ text: legacy.text || legacy.url || '', ...(legacy.url ? { link: legacy.url } : {}) }] }
      }
      return block
    }),
  }
}

export function clearDraftRecovery(articleId: string): void {
  localStorage.removeItem(recoveryKey(articleId))
}
