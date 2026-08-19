import { useEffect, useMemo, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Archive,
  CalendarClock,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  ExternalLink,
  FilePlus2,
  LogOut,
  MoreHorizontal,
  RefreshCw,
  RotateCcw,
  Save,
  Search,
  Share2,
  ShieldCheck,
  Send,
  Trash2,
  Unlink,
  UserRound,
  X,
} from 'lucide-react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router-dom'
import { ArticleCanvas } from '../components/editorial/ArticleCanvas'
import { ArticleExportPanel } from '../components/editorial/ArticleExportPanel'
import { ArticleRelationshipsPanel } from '../components/editorial/ArticleRelationshipsPanel'
import { BlockEditor } from '../components/editorial/BlockEditor'
import type { BlockEditorHandle } from '../components/editorial/BlockEditor'
import { BlockInsertionControl, EditorStarter, EditorToolbar } from '../components/editorial/EditorToolbar'
import { convertBlock, createBlockFromChoice, isVisualChoice, visualTypeFromChoice, type BlockTypeChoice, type EditorCommandChoice } from '../components/editorial/editorCommands'
import { VisualBlockPicker } from '../components/editorial/VisualBlockPicker'
import { StaffFrame } from '../components/staff/StaffFrame'
import { StaffRoute } from '../components/staff/StaffRoute'
import { useStaffAuth } from '../context/StaffAuthContext'
import { fetchSearchEntities } from '../lib/api'
import { ARTICLE_TOPICS } from '../lib/articleTopics'
import type { SearchEntitiesResponse } from '../types/api'
import {
  clearDraftRecovery,
  createArticle,
  deleteArticle,
  EditorialApiError,
  getArticle,
  getArticleRevision,
  listArticles,
  loadDraftRecovery,
  newBlock,
  plainText,
  referencesFromDocument,
  saveArticle,
  setArticlePreview,
  storeDraftRecovery,
  transitionArticle,
  type Article,
  type ArticleBlock,
  type ArticleDraft,
  type ArticleRevision,
  type ArticleSummary,
  type ArticleStatus,
  type ArticleWorkflowAction,
  type VisualArticleBlock,
  type VisualBlockType,
} from '../lib/editorial'

const ARTICLE_LIST_KEY = ['editorial-articles'] as const
const PAGE_LOADED_AT = Date.now()
const REVISION_CHECKPOINT_INTERVAL_MS = 5 * 60 * 1_000
const USER_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone

export function EditorialWorkspace() {
  return (
    <StaffRoute>
      <WorkspaceDashboard />
    </StaffRoute>
  )
}

export function EditorialArticleEditor() {
  return (
    <StaffRoute>
      <ArticleEditor />
    </StaffRoute>
  )
}

function WorkspaceDashboard() {
  const { user, logout } = useStaffAuth()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<'all' | 'shared' | 'recent' | 'review'>('all')
  const articlesQuery = useQuery({ queryKey: ARTICLE_LIST_KEY, queryFn: listArticles })
  const createMutation = useMutation({
    mutationFn: createArticle,
    onSuccess: article => {
      queryClient.setQueryData<ArticleSummary[]>(ARTICLE_LIST_KEY, current => [article, ...(current ?? [])])
      navigate(`/analysis/${article.id}`)
    },
  })
  const deleteMutation = useMutation({
    mutationFn: deleteArticle,
    onSuccess: (_, articleId) => {
      queryClient.setQueryData<ArticleSummary[]>(ARTICLE_LIST_KEY, current => current?.filter(article => article.id !== articleId) ?? [])
      clearDraftRecovery(articleId)
    },
  })

  const visibleArticles = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const recentBoundary = PAGE_LOADED_AT - 7 * 24 * 60 * 60 * 1000
    return (articlesQuery.data ?? []).filter(article => {
      const matchesQuery = !needle || `${article.title} ${article.subtitle}`.toLowerCase().includes(needle)
      const matchesFilter = filter === 'all'
        || (filter === 'shared' && article.preview_enabled)
        || (filter === 'recent' && new Date(article.updated_at).getTime() >= recentBoundary)
        || (filter === 'review' && ['submitted', 'approved', 'scheduled'].includes(article.status))
      return matchesQuery && matchesFilter
    })
  }, [articlesQuery.data, filter, query])

  if (!user) return null
  if (!user.can_access_editorial) return <NoEditorialAccess />

  async function handleLogout() {
    await logout()
    navigate('/staff/login', { replace: true })
  }

  return (
    <StaffFrame eyebrow="The writer's desk">
      <div className="flex flex-1 flex-col py-8 sm:py-12">
        <div className="flex flex-col gap-7 border-b border-line pb-8 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="font-mono text-[9px] uppercase tracking-[0.23em] text-electric">Private workspace · {user.role?.replace('_', ' ')}</p>
            <h1 className="mt-4 text-4xl font-black tracking-[-0.05em] text-ink sm:text-5xl">The analysis desk.</h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-dim">Draft, shape and privately share football ideas before they enter the publishing workflow.</p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Link to="/staff/onboarding" className="inline-flex h-11 items-center gap-2 border border-line-bright px-4 text-[9px] font-bold uppercase tracking-[0.15em] text-ink-dim hover:border-electric hover:text-ink"><UserRound className="size-4" /> Profile</Link>
            <button type="button" onClick={handleLogout} className="inline-flex h-11 items-center gap-2 border border-line-bright px-4 text-[9px] font-bold uppercase tracking-[0.15em] text-ink-dim hover:border-electric hover:text-ink"><LogOut className="size-4" /> Sign out</button>
            <button type="button" onClick={() => createMutation.mutate()} disabled={createMutation.isPending} className="inline-flex h-11 items-center gap-2 bg-electric px-5 text-[9px] font-black uppercase tracking-[0.16em] text-mat hover:bg-ink disabled:opacity-60"><FilePlus2 className="size-4" /> {createMutation.isPending ? 'Opening…' : 'New analysis'}</button>
          </div>
        </div>

        <div className="mt-7 grid gap-3 md:grid-cols-[minmax(0,1fr)_auto]">
          <label className="flex h-11 items-center gap-3 border border-line bg-panel px-4 focus-within:border-electric">
            <Search className="size-4 text-ink-muted" />
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder="Search your drafts" className="w-full bg-transparent text-sm text-ink placeholder:text-ink-muted focus:outline-none" />
          </label>
          <div className="flex border border-line bg-panel p-1" aria-label="Draft filters">
            {(['all', 'recent', 'shared', ...(user.can_approve_editorial ? ['review' as const] : [])] as const).map(value => (
              <button key={value} type="button" onClick={() => setFilter(value)} className={`px-4 py-2 text-[8px] font-bold uppercase tracking-[0.16em] ${filter === value ? 'bg-electric-dim text-electric' : 'text-ink-muted hover:text-ink'}`}>{value}</button>
            ))}
          </div>
        </div>

        {articlesQuery.isLoading ? <DeskMessage><RefreshCw className="size-4 animate-spin" /> Loading your desk</DeskMessage> : null}
        {articlesQuery.isError ? <DeskMessage tone="error">The desk could not be loaded. Refresh to try again.</DeskMessage> : null}
        {!articlesQuery.isLoading && !articlesQuery.isError && visibleArticles.length === 0 ? (
          <div className="mt-6 grid min-h-72 place-items-center border border-dashed border-line-bright bg-panel/35 px-6 text-center">
            <div><FilePlus2 className="mx-auto size-6 text-electric" /><h2 className="mt-4 text-xl font-bold text-ink">{articlesQuery.data?.length ? 'No drafts match this view.' : 'Start with a blank page.'}</h2><p className="mt-2 text-xs leading-5 text-ink-dim">{articlesQuery.data?.length ? 'Try another search or filter.' : 'Your work autosaves and keeps a durable revision trail.'}</p></div>
          </div>
        ) : null}

        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {visibleArticles.map(article => (
            <DraftCard key={article.id} article={article} isOwner={article.author.id === user.id} canDelete={article.author.id === user.id && article.status === 'draft'} deleting={deleteMutation.isPending && deleteMutation.variables === article.id} onDelete={() => {
              if (window.confirm(`Delete “${article.title}”? This removes its saved revision history.`)) deleteMutation.mutate(article.id)
            }} />
          ))}
        </div>
      </div>
    </StaffFrame>
  )
}

function DraftCard({ article, isOwner, canDelete, deleting, onDelete }: { article: ArticleSummary; isOwner: boolean; canDelete: boolean; deleting: boolean; onDelete: () => void }) {
  return (
    <article className="group relative flex min-h-56 flex-col border border-line bg-panel/70 p-5 transition-colors hover:border-electric/50 hover:bg-raised/80">
      <div className="flex items-center justify-between">
        <span className={`border px-2 py-1 font-mono text-[7px] uppercase tracking-[0.18em] ${cardStatusTone(article.status)}`}>{cardStatusLabel(article, isOwner)}</span>
        {canDelete ? <button type="button" onClick={onDelete} disabled={deleting} className="p-2 text-ink-muted opacity-70 hover:text-ember group-hover:opacity-100" aria-label={`Delete ${article.title}`}><Trash2 className="size-4" /></button> : null}
      </div>
      <Link to={`/analysis/${article.id}`} className="mt-8 flex flex-1 flex-col">
        <h2 className="text-xl font-black leading-tight tracking-[-0.035em] text-ink">{article.title}</h2>
        <p className="mt-2 font-mono text-[8px] uppercase tracking-[0.13em] text-ink-muted">By {article.author.display_name}</p>
        <p className="mt-3 line-clamp-2 text-xs leading-5 text-ink-dim">{article.subtitle || 'No standfirst yet - open the article to continue.'}</p>
        <div className="mt-auto flex items-center justify-between pt-8 font-mono text-[8px] uppercase tracking-[0.14em] text-ink-muted">
          <span>{relativeDate(article.updated_at)}</span>
          <span className={article.status === 'scheduled' ? 'text-gold' : article.preview_enabled ? 'text-mint' : ''}>{article.status === 'scheduled' && article.scheduled_for ? `Due ${shortDate(article.scheduled_for)}` : article.preview_enabled ? 'Preview shared' : 'Private'}</span>
        </div>
      </Link>
    </article>
  )
}

type SaveState = 'saved' | 'unsaved' | 'saving' | 'recovered' | 'error'
type SubmissionStep = 'subjects' | 'topics' | 'sources'

function ArticleEditor() {
  const { articleId = '' } = useParams()
  const { user } = useStaffAuth()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const articleQuery = useQuery({ queryKey: ['editorial-article', articleId], queryFn: () => getArticle(articleId), enabled: Boolean(articleId), retry: false })
  const entitiesQuery = useQuery({ queryKey: ['search-entities'], queryFn: fetchSearchEntities, staleTime: 10 * 60 * 1_000 })
  const [selectedRevisionNumber, setSelectedRevisionNumber] = useState<number | null>(null)
  const revisionQuery = useQuery({
    queryKey: ['editorial-article-revision', articleId, selectedRevisionNumber],
    queryFn: () => getArticleRevision(articleId, selectedRevisionNumber as number),
    enabled: selectedRevisionNumber !== null,
    retry: false,
  })
  const [article, setArticle] = useState<Article | null>(null)
  const [draft, setDraft] = useState<ArticleDraft | null>(null)
  const [saveState, setSaveState] = useState<SaveState>('saved')
  const [workflowPending, setWorkflowPending] = useState(false)
  const [saveError, setSaveError] = useState('')
  const [mode, setMode] = useState<'write' | 'reader'>('write')
  const [activeBlockId, setActiveBlockId] = useState('')
  const [activeBlockHandle, setActiveBlockHandle] = useState<BlockEditorHandle | null>(null)
  const [inspectorOpen, setInspectorOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const [submissionSteps, setSubmissionSteps] = useState<SubmissionStep[]>([])
  const [submissionStepIndex, setSubmissionStepIndex] = useState(0)
  const [visualPicker, setVisualPicker] = useState<{
    replaceBlockId?: string
    insertAfterIndex?: number
    initialType?: VisualBlockType
    initialBlock?: VisualArticleBlock
  } | null>(null)
  const initializedIdRef = useRef('')
  const draftRef = useRef<ArticleDraft | null>(null)
  const revisionRef = useRef(1)
  const editSerialRef = useRef(0)
  const savedSerialRef = useRef(0)
  const savingRef = useRef(false)
  const workflowPendingRef = useRef(false)
  const pendingSaveRef = useRef(false)
  const pendingCheckpointRef = useRef(false)
  const lastCheckpointAtRef = useRef(Date.now())
  const performSaveRef = useRef<(createRevision?: boolean) => Promise<boolean>>(async () => false)
  const checkpointingNavigationRef = useRef(false)
  const canEdit = Boolean(
    article
      && user
      && article.author.id === user.id
      && ['draft', 'changes_requested'].includes(article.status),
  )
  const navigationBlocker = useBlocker(canEdit)
  const draftReferences = useMemo(
    () => draft ? referencesFromDocument(draft.document) : { players: [], teams: [] },
    [draft],
  )

  useEffect(() => {
    const serverArticle = articleQuery.data
    if (!serverArticle || initializedIdRef.current === serverArticle.id) return
    const recovery = loadDraftRecovery(serverArticle.id)
    const hasNewerRecovery = ['draft', 'changes_requested'].includes(serverArticle.status)
      && recovery
      && new Date(recovery.savedAt) > new Date(serverArticle.updated_at)
    const initialDraft = hasNewerRecovery ? recovery.draft : articleToDraft(serverArticle)
    initializedIdRef.current = serverArticle.id
    revisionRef.current = serverArticle.revision
    lastCheckpointAtRef.current = serverArticle.revisions[0]
      ? new Date(serverArticle.revisions[0].created_at).getTime()
      : Date.now()
    editSerialRef.current = hasNewerRecovery ? 1 : 0
    savedSerialRef.current = 0
    draftRef.current = initialDraft
    setArticle(serverArticle)
    setDraft(initialDraft)
    setActiveBlockId(initialDraft.document.blocks[0]?.id ?? '')
    if (!['draft', 'changes_requested'].includes(serverArticle.status)) setMode('reader')
    setSaveState(hasNewerRecovery ? 'recovered' : 'saved')
  }, [articleQuery.data])

  function editDraft(update: (current: ArticleDraft) => ArticleDraft) {
    setDraft(current => {
      if (!current) return current
      const next = update(current)
      editSerialRef.current += 1
      draftRef.current = next
      storeDraftRecovery(articleId, next)
      setSaveState('unsaved')
      setSaveError('')
      return next
    })
  }

  async function performSave(createRevision = false): Promise<boolean> {
    if (!canEdit) return true
    const currentDraft = draftRef.current
    const serial = editSerialRef.current
    const checkpointRequested = createRevision
      || Date.now() - lastCheckpointAtRef.current >= REVISION_CHECKPOINT_INTERVAL_MS
    if (!currentDraft || (serial === savedSerialRef.current && !checkpointRequested)) return true
    if (savingRef.current) {
      pendingSaveRef.current = true
      pendingCheckpointRef.current = pendingCheckpointRef.current || checkpointRequested
      return false
    }
    savingRef.current = true
    setSaveState('saving')
    setSaveError('')
    try {
      const savedArticle = await saveArticle(articleId, currentDraft, revisionRef.current, checkpointRequested)
      revisionRef.current = savedArticle.revision
      if (checkpointRequested) {
        lastCheckpointAtRef.current = savedArticle.revisions[0]
          ? new Date(savedArticle.revisions[0].created_at).getTime()
          : Date.now()
      }
      savedSerialRef.current = serial
      setArticle(savedArticle)
      queryClient.setQueryData(['editorial-article', articleId], savedArticle)
      queryClient.invalidateQueries({ queryKey: ARTICLE_LIST_KEY })
      if (editSerialRef.current === serial) {
        clearDraftRecovery(articleId)
        setSaveState('saved')
      } else {
        setSaveState('unsaved')
        pendingSaveRef.current = true
      }
      return true
    } catch (error) {
      const message = error instanceof EditorialApiError ? error.message : 'The draft could not be saved.'
      setSaveError(message)
      setSaveState('error')
      return false
    } finally {
      savingRef.current = false
      if (pendingSaveRef.current) {
        pendingSaveRef.current = false
        const pendingCheckpoint = pendingCheckpointRef.current
        pendingCheckpointRef.current = false
        window.setTimeout(() => void performSaveRef.current(pendingCheckpoint), 0)
      }
    }
  }
  performSaveRef.current = performSave

  useEffect(() => {
    if (!draft || editSerialRef.current === savedSerialRef.current) return
    const timeout = window.setTimeout(() => void performSaveRef.current(), 1_000)
    return () => window.clearTimeout(timeout)
  }, [draft])

  useEffect(() => {
    const saveAfterReconnect = () => void performSaveRef.current()
    window.addEventListener('online', saveAfterReconnect)
    return () => window.removeEventListener('online', saveAfterReconnect)
  }, [])

  useEffect(() => {
    if (navigationBlocker.state !== 'blocked' || checkpointingNavigationRef.current) return
    checkpointingNavigationRef.current = true
    void performSaveRef.current(true).then(saved => {
      checkpointingNavigationRef.current = false
      if (saved) navigationBlocker.proceed()
      else navigationBlocker.reset()
    })
  }, [navigationBlocker])

  if (articleQuery.isLoading || !draft || !article) return <EditorMessage>Loading the draft…</EditorMessage>
  if (articleQuery.isError) return <EditorMessage error>This draft is unavailable or belongs to another writer.</EditorMessage>

  function updateBlock(blockId: string, nextBlock: ArticleBlock) {
    editDraft(current => ({ ...current, document: { ...current.document, blocks: current.document.blocks.map(block => block.id === blockId ? nextBlock : block) } }))
  }

  function moveBlock(index: number, direction: -1 | 1) {
    editDraft(current => {
      const blocks = [...current.document.blocks]
      const destination = index + direction
      if (destination < 0 || destination >= blocks.length) return current
      const [block] = blocks.splice(index, 1)
      blocks.splice(destination, 0, block)
      return { ...current, document: { ...current.document, blocks } }
    })
  }

  function insertBlockAfter(index: number, block: ArticleBlock) {
    editDraft(current => {
      const blocks = [...current.document.blocks]
      blocks.splice(index + 1, 0, block)
      return { ...current, document: { ...current.document, blocks } }
    })
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${block.id}"]`)?.focus())
  }

  function insertEditorCommand(choice: EditorCommandChoice, afterIndex: number) {
    if (!draft) return
    const insertionIndex = Math.max(-1, Math.min(afterIndex, draft.document.blocks.length - 1))
    if (isVisualChoice(choice)) {
      setVisualPicker({ insertAfterIndex: insertionIndex, initialType: visualTypeFromChoice(choice) })
      return
    }
    const block = createBlockFromChoice(choice)
    const continuation = choice === 'image' || choice === 'divider' ? newBlock('paragraph') : null
    editDraft(current => {
      const blocks = [...current.document.blocks]
      blocks.splice(insertionIndex + 1, 0, block, ...(continuation ? [continuation] : []))
      return { ...current, document: { ...current.document, blocks } }
    })
    const focusTarget = continuation ?? block
    setActiveBlockId(focusTarget.id)
    setActiveBlockHandle(null)
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${focusTarget.id}"]`)?.focus())
  }

  function changeActiveBlockType(choice: BlockTypeChoice) {
    if (!draft || !activeBlockId) return
    const currentBlock = draft.document.blocks.find(block => block.id === activeBlockId)
    if (!currentBlock || currentBlock.type === 'visual') return
    updateBlock(activeBlockId, convertBlock(currentBlock, choice))
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${activeBlockId}"], [data-editor-block-id^="${activeBlockId}-"]`)?.focus())
  }

  function chooseStarter(choice: 'paragraph' | 'heading:2' | 'callout' | 'visual:custom_chart') {
    if (!draft) return
    const firstBlock = draft.document.blocks[0]
    if (!firstBlock) return
    setActiveBlockId(firstBlock.id)
    if (isVisualChoice(choice)) {
      setVisualPicker({ replaceBlockId: firstBlock.id, initialType: visualTypeFromChoice(choice) })
      return
    }
    updateBlock(firstBlock.id, convertBlock(firstBlock, choice))
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${firstBlock.id}"], [data-editor-block-id^="${firstBlock.id}-"]`)?.focus())
  }

  function insertVisual(block: VisualArticleBlock) {
    const target = visualPicker
    if (!target) return
    const continuation = target.initialBlock ? null : newBlock('paragraph')
    editDraft(current => {
      const blocks = [...current.document.blocks]
      if (target.replaceBlockId) {
        const index = blocks.findIndex(item => item.id === target.replaceBlockId)
        if (index < 0) return current
        blocks.splice(index, 1, block, ...(continuation ? [continuation] : []))
      } else {
        const index = target.insertAfterIndex ?? blocks.length - 1
        blocks.splice(index + 1, 0, block, ...(continuation ? [continuation] : []))
      }
      return { ...current, document: { ...current.document, blocks } }
    })
    setVisualPicker(null)
    if (continuation) requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${continuation.id}"]`)?.focus())
  }

  function removeBlock(index: number) {
    if (!draft) return
    const replacement = draft.document.blocks.length === 1 ? newBlock('paragraph') : null
    const nextActiveBlock = replacement ?? draft.document.blocks[index + 1] ?? draft.document.blocks[index - 1]
    editDraft(current => {
      const blocks = current.document.blocks.filter((_, blockIndex) => blockIndex !== index)
      return { ...current, document: { ...current.document, blocks: blocks.length ? blocks : replacement ? [replacement] : [newBlock('paragraph')] } }
    })
    if (nextActiveBlock) {
      setActiveBlockId(nextActiveBlock.id)
      setActiveBlockHandle(null)
      requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${nextActiveBlock.id}"], [data-editor-block-id^="${nextActiveBlock.id}-"]`)?.focus())
    }
  }

  function duplicateBlock(index: number) {
    if (!draft) return
    const source = draft.document.blocks[index]
    if (!source) return
    const duplicate = { ...structuredClone(source), id: crypto.randomUUID() } as ArticleBlock
    editDraft(current => {
      const blocks = [...current.document.blocks]
      blocks.splice(index + 1, 0, duplicate)
      return { ...current, document: { ...current.document, blocks } }
    })
    setActiveBlockId(duplicate.id)
    setActiveBlockHandle(null)
    requestAnimationFrame(() => document.querySelector<HTMLElement>(`[data-editor-block-id="${duplicate.id}"], [data-editor-block-id^="${duplicate.id}-"]`)?.focus())
  }

  function removeEmptyBlock(index: number): boolean {
    if (!draft || index === 0) return false
    const precedingBlockIds = draft.document.blocks.slice(0, index).map(block => block.id).reverse()
    editDraft(current => ({
      ...current,
      document: {
        ...current.document,
        blocks: current.document.blocks.filter((_, blockIndex) => blockIndex !== index),
      },
    }))
    requestAnimationFrame(() => focusLastEditableBlock(precedingBlockIds))
    return true
  }

  function navigateFromBlock(index: number, direction: -1 | 1): boolean {
    if (!draft) return true
    const blockIds = direction === 1
      ? draft.document.blocks.slice(index + 1).map(block => block.id)
      : draft.document.blocks.slice(0, index).map(block => block.id).reverse()
    focusAdjacentEditableBlock(blockIds, direction)
    return true
  }

  async function togglePreview(enabled: boolean, rotate = false) {
    const saved = await performSaveRef.current(true)
    if (!saved && editSerialRef.current !== savedSerialRef.current) return
    try {
      const updated = await setArticlePreview(articleId, enabled, rotate)
      setArticle(updated)
      queryClient.invalidateQueries({ queryKey: ARTICLE_LIST_KEY })
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'The preview link could not be updated.')
    }
  }

  async function runWorkflow(action: ArticleWorkflowAction, options: { note?: string; publishAt?: string } = {}): Promise<boolean> {
    if (workflowPendingRef.current) return false
    workflowPendingRef.current = true
    setWorkflowPending(true)
    try {
      if (canEdit) {
        const saved = await performSaveRef.current(true)
        if (!saved) return false
      }
      setSaveError('')
      const updated = await transitionArticle(articleId, action, options)
      setArticle(updated)
      setDraft(articleToDraft(updated))
      draftRef.current = articleToDraft(updated)
      revisionRef.current = updated.revision
      clearDraftRecovery(articleId)
      setSaveState('saved')
      if (!['draft', 'changes_requested'].includes(updated.status)) setMode('reader')
      queryClient.setQueryData(['editorial-article', articleId], updated)
      queryClient.invalidateQueries({ queryKey: ARTICLE_LIST_KEY })
      return true
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'The workflow action could not be completed.')
      return false
    } finally {
      workflowPendingRef.current = false
      setWorkflowPending(false)
    }
  }

  function requestSubmission() {
    if (!draft) return
    const missing: SubmissionStep[] = []
    if (!draft.subjects.players.length && !draft.subjects.teams.length) missing.push('subjects')
    if (!draft.topics.length) missing.push('topics')
    if (!draft.source_notes.trim()) missing.push('sources')
    if (!missing.length) {
      void runWorkflow('submit')
      return
    }
    setSubmissionSteps(missing)
    setSubmissionStepIndex(0)
  }

  async function submitFromPreflight() {
    const submitted = await runWorkflow('submit')
    if (submitted) setSubmissionSteps([])
  }

  const previewUrl = article.preview_token ? `${window.location.origin}/analysis/preview/${article.preview_token}` : ''
  const activeBlockIndex = Math.max(0, draft.document.blocks.findIndex(block => block.id === activeBlockId))
  const activeBlock = draft.document.blocks[activeBlockIndex]
  const showStarter = draft.document.blocks.length === 1
    && draft.document.blocks[0]?.type === 'paragraph'
    && !plainText(draft.document.blocks[0].content).trim()

  async function copyPreview() {
    await navigator.clipboard.writeText(previewUrl)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1_500)
  }

  async function continueFromRevision(revision: ArticleRevision) {
    const currentCheckpointSaved = await performSaveRef.current(true)
    if (!currentCheckpointSaved) return
    const restoredDraft = articleToDraft(revision)
    editSerialRef.current += 1
    draftRef.current = restoredDraft
    setDraft(restoredDraft)
    storeDraftRecovery(articleId, restoredDraft)
    setSaveState('unsaved')
    setSaveError('')
    const restored = await performSaveRef.current(true)
    if (restored) {
      setSelectedRevisionNumber(null)
      setMode('write')
    }
  }

  async function selectMode(nextMode: 'write' | 'reader') {
    if (nextMode === mode) return
    if (nextMode === 'reader') {
      const checkpointSaved = await performSaveRef.current(true)
      if (!checkpointSaved) return
    }
    setMode(nextMode)
  }

  return (
    <main className="min-h-svh bg-mat">
      <header className="sticky top-0 z-30 border-b border-line bg-mat/95 px-4 backdrop-blur sm:px-6">
        <div className="mx-auto flex h-16 max-w-[1500px] items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-4">
            <button type="button" onClick={() => navigate('/analysis')} disabled={saveState === 'saving'} className="p-2 text-ink-muted hover:text-electric disabled:opacity-50" aria-label="Back to analysis desk"><ArrowLeft className="size-4" /></button>
            <div className="min-w-0"><p className="truncate text-xs font-bold text-ink">{draft.title || 'Untitled analysis'}</p><SaveStatus state={saveState} /></div>
          </div>
          <div className="flex items-center gap-2">
            <div className="hidden border border-line p-1 sm:flex">
              {canEdit ? <button type="button" onClick={() => void selectMode('write')} className={`px-3 py-1.5 text-[8px] font-bold uppercase tracking-[0.15em] ${mode === 'write' ? 'bg-electric-dim text-electric' : 'text-ink-muted'}`}>Write</button> : null}
              <button type="button" onClick={() => void selectMode('reader')} disabled={saveState === 'saving'} className={`px-3 py-1.5 text-[8px] font-bold uppercase tracking-[0.15em] disabled:opacity-50 ${mode === 'reader' ? 'bg-electric-dim text-electric' : 'text-ink-muted'}`}>Reader view</button>
            </div>
            <span className={`hidden border px-2 py-1 font-mono text-[7px] uppercase tracking-[0.16em] sm:inline ${statusTone(article.status)}`}>{statusLabel(article.status)}</span>
            {canEdit ? <button type="button" onClick={() => void performSaveRef.current(true)} disabled={saveState === 'saving'} className="inline-flex h-9 items-center gap-2 border border-line-bright px-3 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-dim hover:border-electric hover:text-ink"><Save className="size-3.5" /> Save</button> : null}
            {article.preview_enabled && previewUrl ? <a href={previewUrl} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-2 bg-electric px-3 text-[8px] font-black uppercase tracking-[0.14em] text-mat"><ExternalLink className="size-3.5" /> Preview</a> : null}
          </div>
        </div>
      </header>

      {saveError ? <div className="border-b border-ember/35 bg-ember-dim/55 px-6 py-2 text-center text-xs text-ink">{saveError}</div> : null}

      <div className={`mx-auto ${mode === 'write' || !canEdit ? `grid max-w-[1500px] ${inspectorOpen ? 'lg:grid-cols-[minmax(0,1fr)_300px]' : ''}` : 'w-full'}`}>
        <section className="min-h-[calc(100svh-4rem)] bg-panel/30">
          {mode === 'reader' ? (
            <ArticleCanvas title={draft.title} subtitle={draft.subtitle} document={draft.document} author={article.author} updatedAt={article.updated_at} subjects={draft.subjects} references={draftReferences} topics={draft.topics} sourceNotes={draft.source_notes} />
          ) : (
            <>
            <EditorToolbar
              activeBlock={activeBlock}
              activeIndex={activeBlockIndex}
              total={draft.document.blocks.length}
              activeHandle={activeBlockHandle ?? undefined}
              inspectorOpen={inspectorOpen}
              onInsert={insertEditorCommand}
              onChangeType={changeActiveBlockType}
              onMove={direction => moveBlock(activeBlockIndex, direction)}
              onDuplicate={() => duplicateBlock(activeBlockIndex)}
              onRemove={() => removeBlock(activeBlockIndex)}
              onToggleInspector={() => setInspectorOpen(current => !current)}
            />
            <div className="mx-auto max-w-[760px] px-7 py-12 sm:px-12 sm:py-16">
              <p className="font-mono text-[8px] uppercase tracking-[0.22em] text-electric">{statusLabel(article.status)} · Revision {article.revision}</p>
              <textarea value={draft.title} onChange={event => editDraft(current => ({ ...current, title: event.target.value }))} rows={2} maxLength={180} placeholder="Untitled analysis" className="mt-5 w-full resize-none bg-transparent text-4xl font-black leading-[1.05] tracking-[-0.05em] text-ink placeholder:text-ink-muted focus:outline-none sm:text-5xl" />
              <textarea value={draft.subtitle} onChange={event => editDraft(current => ({ ...current, subtitle: event.target.value }))} rows={3} maxLength={280} placeholder="A clear standfirst that tells readers why this matters…" className="mt-4 w-full resize-none bg-transparent text-base leading-7 text-ink-dim placeholder:text-ink-muted focus:outline-none" />
              <div className="mt-8 border-t border-line pt-10">
                {showStarter ? <EditorStarter onChoose={chooseStarter} /> : null}
                <div>
                  {draft.document.blocks.map((block, index) => <div key={block.id}>
                    <BlockEditor block={block} index={index} total={draft.document.blocks.length} entities={entitiesQuery.data} active={block.id === activeBlockId} onActivate={(blockId, handle) => { setActiveBlockId(blockId); setActiveBlockHandle(handle) }} onChange={next => updateBlock(block.id, next)} onMove={direction => moveBlock(index, direction)} onRemove={() => removeBlock(index)} onInsertAfter={next => insertBlockAfter(index, next)} onBackspaceEmpty={() => removeEmptyBlock(index)} onRequestVisual={(initialType, initialBlock) => setVisualPicker({ replaceBlockId: block.id, initialType, initialBlock })} onNavigateBlock={direction => navigateFromBlock(index, direction)} />
                    <BlockInsertionControl afterIndex={index} onInsert={insertEditorCommand} />
                  </div>)}
                </div>
              </div>
            </div>
            </>
          )}
        </section>

        {(mode === 'write' || !canEdit) && inspectorOpen ? <aside className="border-t border-line p-5 lg:sticky lg:top-16 lg:max-h-[calc(100svh-4rem)] lg:self-start lg:overflow-y-auto lg:border-l lg:border-t-0">
          <InspectorSection title="Publishing workflow" defaultOpen>
            <WorkflowPanel article={article} canApprove={Boolean(user?.can_approve_editorial)} canEdit={canEdit} pending={workflowPending} onSubmit={requestSubmission} onTransition={runWorkflow} />
          </InspectorSection>
          <InspectorSection title="Discovery relationships" defaultOpen>
            <ArticleRelationshipsPanel subjects={draft.subjects} references={draftReferences} entities={entitiesQuery.data} loading={entitiesQuery.isLoading} readOnly={!canEdit} onChange={subjects => editDraft(current => ({ ...current, subjects }))} />
          </InspectorSection>
          <InspectorSection title="Public discovery">
            <p className="font-mono text-[7px] uppercase tracking-[0.15em] text-ink-muted">Topics</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {ARTICLE_TOPICS.map(topic => {
                const selected = draft.topics.includes(topic)
                return <button key={topic} type="button" aria-pressed={selected} disabled={!canEdit} onClick={() => editDraft(current => ({ ...current, topics: selected ? current.topics.filter(value => value !== topic) : [...current.topics, topic] }))} className={`border px-2 py-1.5 font-mono text-[7px] uppercase tracking-[0.1em] transition-colors disabled:opacity-50 ${selected ? 'border-electric bg-electric/15 text-electric' : 'border-line text-ink-muted hover:border-electric hover:text-ink'}`}>{topic}</button>
              })}
            </div>
            <p className="mt-2 text-[9px] leading-4 text-ink-muted">Choose the editorial themes that best describe the article. Competition and season are derived separately from published visual context.</p>
            <label className="mt-5 block font-mono text-[7px] uppercase tracking-[0.15em] text-ink-muted" htmlFor="article-source-notes">Source notes</label>
            <textarea id="article-source-notes" value={draft.source_notes} onChange={event => editDraft(current => ({ ...current, source_notes: event.target.value }))} disabled={!canEdit} rows={4} maxLength={2000} placeholder="Data sources, methodology and caveats readers should know…" className="mt-2 w-full resize-none border border-line bg-mat p-3 text-xs leading-5 text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none disabled:opacity-60" />
          </InspectorSection>

          {canEdit || user?.can_approve_editorial ? <InspectorSection title="Private preview">
            <p className="text-xs leading-5 text-ink-dim">Anyone with the active link can review this saved draft.</p>
            {article.preview_enabled ? (
              <div className="mt-4 space-y-2">
                <button type="button" onClick={() => void copyPreview()} className="flex h-10 w-full items-center justify-center gap-2 bg-electric text-[8px] font-black uppercase tracking-[0.15em] text-mat"><Copy className="size-3.5" /> {copied ? 'Copied' : 'Copy preview link'}</button>
                <button type="button" onClick={() => void togglePreview(true, true)} className="flex h-9 w-full items-center justify-center gap-2 border border-line text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted hover:text-ink"><RefreshCw className="size-3.5" /> Rotate link</button>
                <button type="button" onClick={() => void togglePreview(false)} className="flex h-9 w-full items-center justify-center gap-2 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted hover:text-ember"><Unlink className="size-3.5" /> Revoke access</button>
              </div>
            ) : <button type="button" onClick={() => void togglePreview(true)} className="mt-4 flex h-10 w-full items-center justify-center gap-2 border border-electric/50 bg-electric-dim/45 text-[8px] font-black uppercase tracking-[0.15em] text-electric"><Share2 className="size-3.5" /> Create 7-day preview</button>}
            {article.preview_expires_at ? <p className="mt-3 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">Expires {shortDate(article.preview_expires_at)}</p> : null}
          </InspectorSection> : null}

          <InspectorSection title="Export & republish">
            <ArticleExportPanel articleId={article.id} document={draft.document} />
          </InspectorSection>

          <InspectorSection title="Revision trail">
            <div className="space-y-3">
              {article.revisions.slice(0, 8).map(revision => (
                <button key={revision.number} type="button" onClick={() => setSelectedRevisionNumber(revision.number)} className="group/revision flex w-full items-center justify-between border-b border-line pb-3 text-left font-mono text-[8px] uppercase tracking-[0.12em] transition-colors hover:border-electric focus-visible:border-electric focus-visible:outline-none">
                  <span className="text-ink-dim group-hover/revision:text-electric">Revision {revision.number}</span>
                  <span className="flex items-center gap-2 text-ink-muted"><span>{shortDate(revision.created_at)}</span><ChevronRight className="size-3 transition-transform group-hover/revision:translate-x-0.5 group-hover/revision:text-electric" /></span>
                </button>
              ))}
            </div>
          </InspectorSection>
          <InspectorSection title="Audit trail">
            <WorkflowTimeline article={article} />
          </InspectorSection>
        </aside> : null}
      </div>

      {selectedRevisionNumber !== null ? (
        <RevisionViewer
          article={article}
          revisionNumber={selectedRevisionNumber}
          revision={revisionQuery.data}
          loading={revisionQuery.isLoading}
          error={revisionQuery.isError}
          restoring={saveState === 'saving'}
          onClose={() => setSelectedRevisionNumber(null)}
          onContinue={canEdit ? continueFromRevision : undefined}
        />
      ) : null}
      {visualPicker ? <VisualBlockPicker initialType={visualPicker.initialType} initialBlock={visualPicker.initialBlock} onClose={() => setVisualPicker(null)} onInsert={insertVisual} /> : null}
      {submissionSteps.length ? <SubmissionPreflight
        step={submissionSteps[submissionStepIndex]}
        stepNumber={submissionStepIndex + 1}
        stepCount={submissionSteps.length}
        draft={draft}
        entities={entitiesQuery.data}
        loadingEntities={entitiesQuery.isLoading}
        pending={workflowPending}
        onChange={editDraft}
        onClose={() => setSubmissionSteps([])}
        onContinue={() => setSubmissionStepIndex(index => Math.min(index + 1, submissionSteps.length - 1))}
        onSubmit={() => void submitFromPreflight()}
      /> : null}
    </main>
  )
}

function SubmissionPreflight({ step, stepNumber, stepCount, draft, entities, loadingEntities, pending, onChange, onClose, onContinue, onSubmit }: {
  step: SubmissionStep
  stepNumber: number
  stepCount: number
  draft: ArticleDraft
  entities?: SearchEntitiesResponse
  loadingEntities: boolean
  pending: boolean
  onChange: (update: (current: ArticleDraft) => ArticleDraft) => void
  onClose: () => void
  onContinue: () => void
  onSubmit: () => void
}) {
  const isLast = stepNumber === stepCount
  const copy = {
    subjects: {title: 'Who or what is this analysis about?', description: 'Add primary player or team subjects so the article appears on the right profiles.' },
    topics: {title: 'Which themes fit this piece?', description: 'Choose any editorial topics that will help readers discover it.' },
    sources: {title: 'Any source notes to share?', description: 'Add data sources, methodology or caveats that readers should know.' },
  }[step]

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !pending) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose, pending])

  return (
    <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-mat/90 p-4 backdrop-blur-sm" role="presentation" onMouseDown={event => {
      if (event.target === event.currentTarget && !pending) onClose()
    }}>
      <section role="dialog" aria-modal="true" aria-labelledby="submission-preflight-title" className="w-full max-w-2xl border border-line-bright bg-panel shadow-2xl">
        <header className="flex items-start justify-between gap-6 border-b border-line px-5 py-5 sm:px-7">
          <div>
            <p className="font-mono text-[8px] uppercase tracking-[0.22em] text-electric">Submit for review · {stepNumber}/{stepCount}</p>
            <h2 id="submission-preflight-title" className="mt-2 text-2xl font-black tracking-[-0.035em] text-ink">{copy.title}</h2>
            <p className="mt-2 max-w-xl text-xs leading-5 text-ink-dim">{copy.description} This is optional, you can continue without adding anything.</p>
          </div>
          <button type="button" onClick={onClose} disabled={pending} className="grid size-9 shrink-0 place-items-center border border-line text-ink-muted hover:border-electric hover:text-electric disabled:opacity-50" aria-label="Close submission checklist"><X className="size-4" /></button>
        </header>
        <div className="max-h-[60svh] overflow-y-auto p-5 sm:p-7">
          {step === 'subjects' ? <ArticleRelationshipsPanel subjects={draft.subjects} references={{ players: [], teams: [] }} entities={entities} loading={loadingEntities} onChange={subjects => onChange(current => ({ ...current, subjects }))} showReferences={false} /> : null}
          {step === 'topics' ? <div className="flex flex-wrap gap-2">{ARTICLE_TOPICS.map(topic => {
            const selected = draft.topics.includes(topic)
            return <button key={topic} type="button" aria-pressed={selected} onClick={() => onChange(current => ({ ...current, topics: selected ? current.topics.filter(value => value !== topic) : [...current.topics, topic] }))} className={`border px-3 py-2.5 font-mono text-[8px] uppercase tracking-[0.12em] transition-colors ${selected ? 'border-electric bg-electric/15 text-electric' : 'border-line-bright text-ink-muted hover:border-electric hover:text-ink'}`}>{topic}</button>
          })}</div> : null}
          {step === 'sources' ? <textarea autoFocus value={draft.source_notes} onChange={event => onChange(current => ({ ...current, source_notes: event.target.value }))} rows={7} maxLength={2000} placeholder="Data sources, methodology and caveats readers should know…" className="w-full resize-none border border-line bg-mat p-4 text-sm leading-6 text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none" /> : null}
        </div>
        <footer className="flex flex-col-reverse gap-3 border-t border-line px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-7">
          <button type="button" onClick={onClose} disabled={pending} className="h-10 px-3 font-mono text-[8px] uppercase tracking-[0.15em] text-ink-muted hover:text-ink disabled:opacity-50">Return to draft</button>
          <button type="button" onKeyDown={preventEnterActivation} onClick={isLast ? onSubmit : onContinue} disabled={pending} className="inline-flex h-11 items-center justify-center gap-2 bg-electric px-5 font-mono text-[8px] font-black uppercase tracking-[0.15em] text-mat disabled:opacity-50">{pending ? 'Saving…' : isLast ? 'Submit for review' : 'Continue'} <ChevronRight className="size-3.5" /></button>
        </footer>
      </section>
    </div>
  )
}

function WorkflowPanel({ article, canApprove, canEdit, pending, onSubmit, onTransition }: { article: Article; canApprove: boolean; canEdit: boolean; pending: boolean; onSubmit: () => void; onTransition: (action: ArticleWorkflowAction, options?: { note?: string; publishAt?: string }) => Promise<boolean> }) {
  const [note, setNote] = useState('')
  const [scheduleAt, setScheduleAt] = useState(() => localDateTimeValue(new Date()))
  const status = article.status
  const canReview = canApprove && ['submitted', 'approved', 'scheduled'].includes(status)

  async function requestChanges() {
    if (!note.trim()) return
    await onTransition('request_changes', { note: note.trim() })
    setNote('')
  }

  async function schedulePublication() {
    if (!scheduleAt) return
    await onTransition('publish', { publishAt: new Date(scheduleAt).toISOString() })
  }

  return (
    <div>
      <div className={`border p-3 ${statusTone(status)}`}>
        <p className="font-mono text-[8px] uppercase tracking-[0.18em]">{statusLabel(status)}</p>
        <p className="mt-2 text-[11px] leading-5 opacity-80">{workflowDescription(article)}</p>
      </div>
      {status === 'changes_requested' && article.workflow_events.find(event => event.action === 'changes_requested')?.note ? (
        <div className="mt-3 border-l-2 border-gold bg-gold/5 px-3 py-2 text-[11px] leading-5 text-ink-dim">{article.workflow_events.find(event => event.action === 'changes_requested')?.note}</div>
      ) : null}
      {canEdit ? <button type="button" onKeyDown={preventEnterActivation} onClick={onSubmit} disabled={pending} className="mt-4 flex h-10 w-full items-center justify-center gap-2 bg-electric text-[8px] font-black uppercase tracking-[0.15em] text-mat disabled:opacity-50"><Send className="size-3.5" /> Submit for review</button> : null}
      {canReview ? (
        <div className="mt-4 space-y-3">
          <textarea value={note} onChange={event => setNote(event.target.value)} rows={3} maxLength={2000} placeholder="Explain the requested changes…" className="w-full resize-none border border-line bg-mat p-3 text-xs leading-5 text-ink placeholder:text-ink-muted focus:border-gold focus:outline-none" />
          <button type="button" onClick={() => void requestChanges()} disabled={pending || !note.trim()} className="flex h-9 w-full items-center justify-center border border-gold/50 text-[8px] font-bold uppercase tracking-[0.14em] text-gold disabled:opacity-40">Request changes</button>
          {status === 'submitted' ? <button type="button" onClick={() => void onTransition('approve')} disabled={pending} className="flex h-9 w-full items-center justify-center gap-2 border border-mint/50 text-[8px] font-bold uppercase tracking-[0.14em] text-mint disabled:opacity-40"><CheckCircle2 className="size-3.5" /> Approve only</button> : null}
          {status !== 'scheduled' ? (
            <>
              <button type="button" onClick={() => void onTransition('publish')} disabled={pending} className="flex h-10 w-full items-center justify-center gap-2 bg-mint text-[8px] font-black uppercase tracking-[0.14em] text-mat disabled:opacity-40"><CheckCircle2 className="size-3.5" /> Publish now</button>
              <div className="border border-line p-3">
                <label className="font-mono text-[7px] uppercase tracking-[0.15em] text-ink-muted">Scheduled publication</label>
                <input type="datetime-local" value={scheduleAt} min={localDateTimeMinimum()} onChange={event => setScheduleAt(event.target.value)} className="mt-2 h-9 w-full border border-line bg-mat px-2 text-xs text-ink focus:border-electric focus:outline-none" />
                <p className="mt-2 text-[9px] leading-4 text-ink-muted">Shown in {USER_TIME_ZONE}. The saved publication time is timezone-safe.</p>
                <button type="button" onClick={() => void schedulePublication()} disabled={pending || !scheduleAt} className="mt-2 flex h-9 w-full items-center justify-center gap-2 border border-electric/50 text-[8px] font-bold uppercase tracking-[0.14em] text-electric disabled:opacity-40"><CalendarClock className="size-3.5" /> Schedule</button>
              </div>
            </>
          ) : null}
        </div>
      ) : null}
      {canApprove && ['published', 'scheduled'].includes(status) ? <button type="button" onClick={() => void onTransition('unpublish')} disabled={pending} className="mt-4 flex h-9 w-full items-center justify-center border border-ember/50 text-[8px] font-bold uppercase tracking-[0.14em] text-ember disabled:opacity-40">{status === 'scheduled' ? 'Cancel schedule' : 'Unpublish'}</button> : null}
      {canApprove && status !== 'archived' ? <button type="button" onClick={() => void onTransition('archive')} disabled={pending} className="mt-2 flex h-9 w-full items-center justify-center gap-2 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted hover:text-ember disabled:opacity-40"><Archive className="size-3.5" /> Archive</button> : null}
      {canApprove && status === 'archived' ? <button type="button" onClick={() => void onTransition('restore')} disabled={pending} className="mt-4 flex h-9 w-full items-center justify-center border border-electric/50 text-[8px] font-bold uppercase tracking-[0.14em] text-electric disabled:opacity-40">Restore as draft</button> : null}
    </div>
  )
}

function WorkflowTimeline({ article }: { article: Article }) {
  if (!article.workflow_events.length) return <p className="text-[10px] leading-5 text-ink-muted">No workflow actions yet.</p>
  return (
    <ol className="space-y-4">
      {article.workflow_events.map(event => (
        <li key={event.id} className="relative border-l border-line pl-3">
          <span className="absolute -left-1 top-0.5 size-2 rounded-full bg-electric" />
          <p className="font-mono text-[8px] uppercase tracking-[0.13em] text-ink-dim">{statusLabel(event.to_status)}</p>
          <p className="mt-1 text-[10px] leading-4 text-ink-muted">{event.actor?.display_name ?? 'Publishing service'} · {shortDate(event.created_at)} · revision {event.revision}</p>
          {event.note ? <p className="mt-2 text-[10px] leading-4 text-ink-dim">{event.note}</p> : null}
        </li>
      ))}
    </ol>
  )
}

function RevisionViewer({ article, revisionNumber, revision, loading, error, restoring, onClose, onContinue }: { article: Article; revisionNumber: number; revision?: ArticleRevision; loading: boolean; error: boolean; restoring: boolean; onClose: () => void; onContinue?: (revision: ArticleRevision) => Promise<void> }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !restoring) onClose()
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [onClose, restoring])

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto bg-mat">
      <header className="sticky top-0 z-10 border-b border-line bg-mat/95 px-4 backdrop-blur sm:px-6">
        <div className="mx-auto flex min-h-16 max-w-[1500px] items-center justify-between gap-4 py-3">
          <div className="flex min-w-0 items-center gap-3">
            <button type="button" onClick={onClose} disabled={restoring} className="grid size-9 place-items-center border border-line text-ink-muted hover:border-electric hover:text-electric disabled:opacity-40" aria-label="Close revision"><X className="size-4" /></button>
            <div className="min-w-0"><p className="font-mono text-[8px] uppercase tracking-[0.18em] text-electric">Revision {revisionNumber}</p><p className="mt-1 truncate text-xs text-ink-dim">Read-only historical snapshot</p></div>
          </div>
          {revision && onContinue ? <button type="button" onClick={() => void onContinue(revision)} disabled={restoring} className="inline-flex h-10 items-center gap-2 bg-electric px-4 text-[8px] font-black uppercase tracking-[0.14em] text-mat hover:bg-ink disabled:opacity-60"><RotateCcw className="size-3.5" /> {restoring ? 'Restoring…' : 'Continue from this revision'}</button> : null}
        </div>
      </header>
      {loading ? <EditorMessage>Loading revision {revisionNumber}…</EditorMessage> : null}
      {error ? <EditorMessage error>This revision could not be loaded.</EditorMessage> : null}
      {revision ? <ArticleCanvas title={revision.title} subtitle={revision.subtitle} document={revision.document} author={article.author} updatedAt={revision.created_at} subjects={revision.subjects} references={referencesFromDocument(revision.document)} topics={revision.topics} sourceNotes={revision.source_notes} /> : null}
    </div>
  )
}

function NoEditorialAccess() {
  return <StaffFrame eyebrow="Editorial workspace"><div className="grid flex-1 place-items-center text-center"><div><ShieldCheck className="mx-auto size-8 text-ember" /><h1 className="mt-5 text-2xl font-bold text-ink">Editorial access is not assigned.</h1><p className="mt-2 text-sm text-ink-dim">Ask a superuser to review your account role.</p></div></div></StaffFrame>
}

function DeskMessage({ children, tone = 'normal' }: { children: ReactNode; tone?: 'normal' | 'error' }) {
  return <div className={`mt-6 flex min-h-40 items-center justify-center gap-2 border px-6 text-xs ${tone === 'error' ? 'border-ember/35 bg-ember-dim/35 text-ink' : 'border-line bg-panel/40 text-ink-dim'}`}>{children}</div>
}

function EditorMessage({ children, error = false }: { children: ReactNode; error?: boolean }) {
  return <main className="grid min-h-svh place-items-center bg-mat px-6 text-center"><div><MoreHorizontal className={`mx-auto size-6 ${error ? 'text-ember' : 'animate-pulse text-electric'}`} /><p className="mt-4 text-sm text-ink-dim">{children}</p>{error ? <Link to="/analysis" className="mt-5 inline-block text-xs font-bold text-electric">Back to the desk</Link> : null}</div></main>
}

function SaveStatus({ state }: { state: SaveState }) {
  const labels: Record<SaveState, string> = { saved: 'Saved', unsaved: 'Unsaved changes', saving: 'Saving…', recovered: 'Recovered locally · saving…', error: 'Save interrupted' }
  return <p className={`mt-1 flex items-center gap-1.5 font-mono text-[7px] uppercase tracking-[0.14em] ${state === 'error' ? 'text-ember' : state === 'saved' ? 'text-mint' : 'text-ink-muted'}`}><span className={`size-1.5 rounded-full ${state === 'error' ? 'bg-ember' : state === 'saved' ? 'bg-mint' : 'bg-gold'}`} />{labels[state]}</p>
}

function InspectorSection({ title, children, defaultOpen = false }: { title: string; children: ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return <section className="border-b border-line py-5 first:pt-0 last:border-0"><button type="button" onClick={() => setOpen(current => !current)} aria-expanded={open} className="flex w-full items-center justify-between gap-3 font-mono text-[8px] uppercase tracking-[0.2em] text-ink-muted hover:text-electric focus-visible:text-electric focus-visible:outline-none">{title}<ChevronDown className={`size-3 transition-transform ${open ? 'rotate-180' : ''}`} /></button>{open ? <div className="mt-4">{children}</div> : null}</section>
}

function articleToDraft(article: Pick<Article, 'title' | 'subtitle' | 'document' | 'subjects' | 'topics' | 'source_notes'> | ArticleRevision): ArticleDraft {
  return { title: article.title, subtitle: article.subtitle, document: article.document, subjects: article.subjects, topics: article.topics, source_notes: article.source_notes }
}

function relativeDate(value: string): string {
  const days = Math.floor((PAGE_LOADED_AT - new Date(value).getTime()) / 86_400_000)
  if (days <= 0) return 'Edited today'
  if (days === 1) return 'Edited yesterday'
  return `Edited ${days} days ago`
}

function shortDate(value: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function statusLabel(status: ArticleStatus): string {
  return {
    draft: 'Draft',
    submitted: 'Submitted',
    changes_requested: 'Changes requested',
    approved: 'Approved',
    scheduled: 'Scheduled',
    published: 'Published',
    archived: 'Archived',
  }[status]
}

function statusTone(status: ArticleStatus): string {
  if (status === 'published' || status === 'approved') return 'border-mint/45 bg-mint/10 text-mint'
  if (status === 'submitted' || status === 'scheduled') return 'border-gold/45 bg-gold/10 text-gold'
  if (status === 'changes_requested') return 'border-ember/45 bg-ember-dim/45 text-ember'
  if (status === 'archived') return 'border-line-bright bg-raised/50 text-ink-muted'
  return 'border-electric/35 bg-electric-dim/45 text-electric'
}

function cardStatusTone(status: ArticleStatus): string {
  return statusTone(status)
}

function cardStatusLabel(article: ArticleSummary, isOwner: boolean): string {
  if (article.status === 'submitted') return isOwner ? 'Submitted' : 'For review'
  if (article.status === 'published') return 'Live'
  if (article.status === 'approved' && article.published_at) return 'Approved · Unpublished'
  return statusLabel(article.status)
}

function workflowDescription(article: Article): string {
  if (article.status === 'draft') return 'Editable and private. Submit when this draft is ready for editorial review.'
  if (article.status === 'submitted') return 'Locked while an editor verifies the article, subjects and inline references.'
  if (article.status === 'changes_requested') return 'Editable again. Address the editor note, then resubmit the article.'
  if (article.status === 'approved') return 'Editorially approved and private until an editor publishes or schedules it.'
  if (article.status === 'scheduled') return article.scheduled_for ? `Private until ${shortDate(article.scheduled_for)}, then published automatically.` : 'Queued for publication.'
  if (article.status === 'published') return 'Public discovery relationships are active. Content remains locked until unpublished.'
  return 'Removed from the active workflow and all public discovery surfaces.'
}

function localDateTimeMinimum(): string {
  return localDateTimeValue(new Date())
}

function localDateTimeValue(date: Date): string {
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 16)
}

function preventEnterActivation(event: ReactKeyboardEvent<HTMLButtonElement>) {
  if (event.key === 'Enter') event.preventDefault()
}

function focusLastEditableBlock(blockIds: string[]) {
  for (const blockId of blockIds) {
    const editors = document.querySelectorAll<HTMLElement>(`[data-editor-block-id="${blockId}"], [data-editor-block-id^="${blockId}-"]`)
    const editor = editors.item(editors.length - 1)
    if (!editor) continue
    editor.focus()
    const range = document.createRange()
    range.selectNodeContents(editor)
    range.collapse(false)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    return
  }
}

function focusAdjacentEditableBlock(blockIds: string[], direction: -1 | 1): boolean {
  for (const blockId of blockIds) {
    const editors = document.querySelectorAll<HTMLElement>(`[data-editor-block-id="${blockId}"], [data-editor-block-id^="${blockId}-"]`)
    const editor = direction === 1 ? editors.item(0) : editors.item(editors.length - 1)
    if (!editor) continue
    editor.focus()
    const range = document.createRange()
    range.selectNodeContents(editor)
    range.collapse(direction === 1)
    const selection = window.getSelection()
    selection?.removeAllRanges()
    selection?.addRange(range)
    return true
  }
  return false
}
