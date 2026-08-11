import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  BarChart3,
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
  Trash2,
  Unlink,
  UserRound,
  X,
} from 'lucide-react'
import { Link, useBlocker, useNavigate, useParams } from 'react-router-dom'
import { ArticleCanvas } from '../components/editorial/ArticleCanvas'
import { BlockEditor } from '../components/editorial/BlockEditor'
import { VisualBlockPicker } from '../components/editorial/VisualBlockPicker'
import { StaffFrame } from '../components/staff/StaffFrame'
import { StaffRoute } from '../components/staff/StaffRoute'
import { useStaffAuth } from '../context/StaffAuthContext'
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
  saveArticle,
  setArticlePreview,
  storeDraftRecovery,
  type Article,
  type ArticleBlock,
  type ArticleDraft,
  type ArticleRevision,
  type ArticleSummary,
  type VisualArticleBlock,
  type VisualBlockType,
} from '../lib/editorial'

const ARTICLE_LIST_KEY = ['editorial-articles'] as const
const PAGE_LOADED_AT = Date.now()
const REVISION_CHECKPOINT_INTERVAL_MS = 5 * 60 * 1_000

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
  const [filter, setFilter] = useState<'all' | 'shared' | 'recent'>('all')
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
            {(['all', 'recent', 'shared'] as const).map(value => (
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
            <DraftCard key={article.id} article={article} deleting={deleteMutation.isPending && deleteMutation.variables === article.id} onDelete={() => {
              if (window.confirm(`Delete “${article.title}”? This removes its saved revision history.`)) deleteMutation.mutate(article.id)
            }} />
          ))}
        </div>
      </div>
    </StaffFrame>
  )
}

function DraftCard({ article, deleting, onDelete }: { article: ArticleSummary; deleting: boolean; onDelete: () => void }) {
  return (
    <article className="group relative flex min-h-56 flex-col border border-line bg-panel/70 p-5 transition-colors hover:border-electric/50 hover:bg-raised/80">
      <div className="flex items-center justify-between">
        <span className="border border-electric/35 bg-electric-dim/45 px-2 py-1 font-mono text-[7px] uppercase tracking-[0.18em] text-electric">Draft</span>
        <button type="button" onClick={onDelete} disabled={deleting} className="p-2 text-ink-muted opacity-70 hover:text-ember group-hover:opacity-100" aria-label={`Delete ${article.title}`}><Trash2 className="size-4" /></button>
      </div>
      <Link to={`/analysis/${article.id}`} className="mt-8 flex flex-1 flex-col">
        <h2 className="text-xl font-black leading-tight tracking-[-0.035em] text-ink">{article.title}</h2>
        <p className="mt-3 line-clamp-2 text-xs leading-5 text-ink-dim">{article.subtitle || 'No standfirst yet — open the draft to keep writing.'}</p>
        <div className="mt-auto flex items-center justify-between pt-8 font-mono text-[8px] uppercase tracking-[0.14em] text-ink-muted">
          <span>{relativeDate(article.updated_at)}</span>
          <span className={article.preview_enabled ? 'text-mint' : ''}>{article.preview_enabled ? 'Preview shared' : 'Private'}</span>
        </div>
      </Link>
    </article>
  )
}

type SaveState = 'saved' | 'unsaved' | 'saving' | 'recovered' | 'error'

function ArticleEditor() {
  const { articleId = '' } = useParams()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const articleQuery = useQuery({ queryKey: ['editorial-article', articleId], queryFn: () => getArticle(articleId), enabled: Boolean(articleId), retry: false })
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
  const [saveError, setSaveError] = useState('')
  const [mode, setMode] = useState<'write' | 'reader'>('write')
  const [copied, setCopied] = useState(false)
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
  const pendingSaveRef = useRef(false)
  const pendingCheckpointRef = useRef(false)
  const lastCheckpointAtRef = useRef(Date.now())
  const performSaveRef = useRef<(createRevision?: boolean) => Promise<boolean>>(async () => false)
  const checkpointingNavigationRef = useRef(false)
  const navigationBlocker = useBlocker(Boolean(article))

  useEffect(() => {
    const serverArticle = articleQuery.data
    if (!serverArticle || initializedIdRef.current === serverArticle.id) return
    const recovery = loadDraftRecovery(serverArticle.id)
    const hasNewerRecovery = recovery && new Date(recovery.savedAt) > new Date(serverArticle.updated_at)
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
    editDraft(current => {
      const blocks = current.document.blocks.filter((_, blockIndex) => blockIndex !== index)
      return { ...current, document: { ...current.document, blocks: blocks.length ? blocks : [newBlock('paragraph')] } }
    })
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
    if (!draft) return false
    const blockIds = direction === 1
      ? draft.document.blocks.slice(index + 1).map(block => block.id)
      : draft.document.blocks.slice(0, index).map(block => block.id).reverse()
    return focusAdjacentEditableBlock(blockIds, direction)
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

  const previewUrl = article.preview_token ? `${window.location.origin}/analysis/preview/${article.preview_token}` : ''

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
              <button type="button" onClick={() => void selectMode('write')} className={`px-3 py-1.5 text-[8px] font-bold uppercase tracking-[0.15em] ${mode === 'write' ? 'bg-electric-dim text-electric' : 'text-ink-muted'}`}>Write</button>
              <button type="button" onClick={() => void selectMode('reader')} disabled={saveState === 'saving'} className={`px-3 py-1.5 text-[8px] font-bold uppercase tracking-[0.15em] disabled:opacity-50 ${mode === 'reader' ? 'bg-electric-dim text-electric' : 'text-ink-muted'}`}>Reader view</button>
            </div>
            <button type="button" onClick={() => void performSaveRef.current(true)} disabled={saveState === 'saving'} className="inline-flex h-9 items-center gap-2 border border-line-bright px-3 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-dim hover:border-electric hover:text-ink"><Save className="size-3.5" /> Save</button>
            {article.preview_enabled && previewUrl ? <a href={previewUrl} target="_blank" rel="noreferrer" className="inline-flex h-9 items-center gap-2 bg-electric px-3 text-[8px] font-black uppercase tracking-[0.14em] text-mat"><ExternalLink className="size-3.5" /> Preview</a> : null}
          </div>
        </div>
      </header>

      {saveError ? <div className="border-b border-ember/35 bg-ember-dim/55 px-6 py-2 text-center text-xs text-ink">{saveError}</div> : null}

      <div className={`mx-auto ${mode === 'write' ? 'grid max-w-[1500px] lg:grid-cols-[minmax(0,1fr)_260px]' : 'w-full'}`}>
        <section className="min-h-[calc(100svh-4rem)] bg-panel/30">
          {mode === 'reader' ? (
            <ArticleCanvas title={draft.title} subtitle={draft.subtitle} document={draft.document} author={article.author} updatedAt={article.updated_at} />
          ) : (
            <div className="mx-auto max-w-[760px] px-7 py-12 sm:px-12 sm:py-16">
              <div className="flex flex-wrap items-center justify-between gap-3"><p className="font-mono text-[8px] uppercase tracking-[0.22em] text-electric">Draft · Revision {article.revision}</p><button type="button" onClick={() => setVisualPicker({ insertAfterIndex: draft.document.blocks.length - 1 })} className="inline-flex h-9 items-center gap-2 border border-electric/35 bg-electric-dim/25 px-3 text-[8px] font-black uppercase tracking-[0.14em] text-electric hover:border-electric hover:bg-electric hover:text-mat"><BarChart3 className="size-3.5" /> Add visual <span className="hidden font-mono font-normal opacity-60 sm:inline">/chart</span></button></div>
              <textarea value={draft.title} onChange={event => editDraft(current => ({ ...current, title: event.target.value }))} rows={2} maxLength={180} placeholder="Untitled analysis" className="mt-5 w-full resize-none bg-transparent text-4xl font-black leading-[1.05] tracking-[-0.05em] text-ink placeholder:text-ink-muted focus:outline-none sm:text-5xl" />
              <textarea value={draft.subtitle} onChange={event => editDraft(current => ({ ...current, subtitle: event.target.value }))} rows={3} maxLength={280} placeholder="A clear standfirst that tells readers why this matters…" className="mt-4 w-full resize-none bg-transparent text-base leading-7 text-ink-dim placeholder:text-ink-muted focus:outline-none" />
              <div className="mt-8 border-t border-line pt-10">
                <div className="space-y-4">
                  {draft.document.blocks.map((block, index) => (
                    <BlockEditor key={block.id} block={block} index={index} total={draft.document.blocks.length} onChange={next => updateBlock(block.id, next)} onMove={direction => moveBlock(index, direction)} onRemove={() => removeBlock(index)} onInsertAfter={next => insertBlockAfter(index, next)} onBackspaceEmpty={() => removeEmptyBlock(index)} onRequestVisual={(initialType, initialBlock) => setVisualPicker({ replaceBlockId: block.id, initialType, initialBlock })} onNavigateBlock={direction => navigateFromBlock(index, direction)} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </section>

        {mode === 'write' ? <aside className="border-t border-line p-5 lg:sticky lg:top-16 lg:h-[calc(100svh-4rem)] lg:overflow-y-auto lg:border-l lg:border-t-0">
          <InspectorSection title="Private preview">
            <p className="text-xs leading-5 text-ink-dim">Anyone with the active link can review this saved draft.</p>
            {article.preview_enabled ? (
              <div className="mt-4 space-y-2">
                <button type="button" onClick={() => void copyPreview()} className="flex h-10 w-full items-center justify-center gap-2 bg-electric text-[8px] font-black uppercase tracking-[0.15em] text-mat"><Copy className="size-3.5" /> {copied ? 'Copied' : 'Copy preview link'}</button>
                <button type="button" onClick={() => void togglePreview(true, true)} className="flex h-9 w-full items-center justify-center gap-2 border border-line text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted hover:text-ink"><RefreshCw className="size-3.5" /> Rotate link</button>
                <button type="button" onClick={() => void togglePreview(false)} className="flex h-9 w-full items-center justify-center gap-2 text-[8px] font-bold uppercase tracking-[0.14em] text-ink-muted hover:text-ember"><Unlink className="size-3.5" /> Revoke access</button>
              </div>
            ) : <button type="button" onClick={() => void togglePreview(true)} className="mt-4 flex h-10 w-full items-center justify-center gap-2 border border-electric/50 bg-electric-dim/45 text-[8px] font-black uppercase tracking-[0.15em] text-electric"><Share2 className="size-3.5" /> Create preview link</button>}
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
          onContinue={continueFromRevision}
        />
      ) : null}
      {visualPicker ? <VisualBlockPicker initialType={visualPicker.initialType} initialBlock={visualPicker.initialBlock} onClose={() => setVisualPicker(null)} onInsert={insertVisual} /> : null}
    </main>
  )
}

function RevisionViewer({ article, revisionNumber, revision, loading, error, restoring, onClose, onContinue }: { article: Article; revisionNumber: number; revision?: ArticleRevision; loading: boolean; error: boolean; restoring: boolean; onClose: () => void; onContinue: (revision: ArticleRevision) => Promise<void> }) {
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
          {revision ? <button type="button" onClick={() => void onContinue(revision)} disabled={restoring} className="inline-flex h-10 items-center gap-2 bg-electric px-4 text-[8px] font-black uppercase tracking-[0.14em] text-mat hover:bg-ink disabled:opacity-60"><RotateCcw className="size-3.5" /> {restoring ? 'Restoring…' : 'Continue from this revision'}</button> : null}
        </div>
      </header>
      {loading ? <EditorMessage>Loading revision {revisionNumber}…</EditorMessage> : null}
      {error ? <EditorMessage error>This revision could not be loaded.</EditorMessage> : null}
      {revision ? <ArticleCanvas title={revision.title} subtitle={revision.subtitle} document={revision.document} author={article.author} updatedAt={revision.created_at} /> : null}
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

function InspectorSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="border-b border-line py-6 first:pt-0 last:border-0"><h2 className="mb-4 font-mono text-[8px] uppercase tracking-[0.2em] text-ink-muted">{title}</h2>{children}</section>
}

function articleToDraft(article: Pick<Article, 'title' | 'subtitle' | 'document'>): ArticleDraft {
  return { title: article.title, subtitle: article.subtitle, document: article.document }
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
