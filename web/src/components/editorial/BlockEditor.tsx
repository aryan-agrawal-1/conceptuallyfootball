import { ArrowDown, ArrowUp, AtSign, BarChart3, GripVertical, Link2, Plus, Shield, Trash2, UserRound } from 'lucide-react'
import { useMemo, useRef, useState, type FormEvent, type MouseEvent, type ReactElement } from 'react'
import { inlineText, plainText, type ArticleBlock, type EditorialEntityReference, type InlineContent, type VisualArticleBlock, type VisualBlockType } from '../../lib/editorial'
import { foldForSearch } from '../../lib/foldAccents'
import type { SearchEntitiesResponse, SearchPlayerEntity, SearchTeamEntity } from '../../types/api'
import { InlineTextEditor, type InlineTextEditorHandle, type MentionRequest } from './InlineTextEditor'
import { VisualAnalysisBlock } from './VisualAnalysisBlock'

const metaInputClass = 'h-9 w-full border border-line bg-mat px-3 text-xs text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none'

const BLOCK_TYPES = [
  { value: 'paragraph', label: 'Text', keywords: 'paragraph text' },
  { value: 'heading:2', label: 'Heading 2', keywords: 'heading section h2' },
  { value: 'heading:3', label: 'Heading 3', keywords: 'heading subheading h3' },
  { value: 'bulleted_list', label: 'Bulleted list', keywords: 'bullet unordered list' },
  { value: 'numbered_list', label: 'Numbered list', keywords: 'number ordered list' },
  { value: 'quote', label: 'Quote', keywords: 'quote pullquote' },
  { value: 'callout', label: 'Callout', keywords: 'callout insight note warning' },
  { value: 'image', label: 'Image', keywords: 'image photo media' },
  { value: 'divider', label: 'Divider', keywords: 'divider rule separator' },
] as const

const VISUAL_COMMANDS = [
  { value: 'visual:similar_players', label: 'Similar players', keywords: 'visual chart similarity player' },
  { value: 'visual:player_radar', label: 'Player profile', keywords: 'visual chart pizza radar player profile percentile' },
  { value: 'visual:stat_card', label: 'Key-stat cards', keywords: 'visual player team stats percentile cards' },
  { value: 'visual:player_comparison', label: 'Player comparison', keywords: 'visual compare versus radar' },
  { value: 'visual:custom_chart', label: 'Custom chart', keywords: 'visual graph scatter bar x y player team' },
] as const

type BlockTypeChoice = typeof BLOCK_TYPES[number]['value']
type SlashCommandChoice = BlockTypeChoice | typeof VISUAL_COMMANDS[number]['value']

export function BlockEditor({
  block,
  index,
  total,
  onChange,
  onMove,
  onRemove,
  onInsertAfter,
  onBackspaceEmpty,
  onRequestVisual,
  onNavigateBlock,
  entities,
}: {
  block: ArticleBlock
  index: number
  total: number
  onChange: (block: ArticleBlock) => void
  onMove: (direction: -1 | 1) => void
  onRemove: () => void
  onInsertAfter: (block: ArticleBlock) => void
  onBackspaceEmpty: () => boolean
  onRequestVisual: (visualType: VisualBlockType, existing?: VisualArticleBlock) => void
  onNavigateBlock: (direction: -1 | 1) => boolean
  entities?: SearchEntitiesResponse
}) {
  const activeEditorRef = useRef<InlineTextEditorHandle | null>(null)
  const [linkEditor, setLinkEditor] = useState<InlineTextEditorHandle | null>(null)
  const [linkUrl, setLinkUrl] = useState('')
  const [linkError, setLinkError] = useState('')
  const [selectedCommand, setSelectedCommand] = useState<SlashCommandChoice | null>(null)
  const [mentionRequest, setMentionRequest] = useState<MentionRequest | null>(null)
  const [selectedMentionIndex, setSelectedMentionIndex] = useState(0)
  const slashQuery = block.type === 'paragraph' && plainText(block.content).startsWith('/')
    ? plainText(block.content).slice(1).trim().toLowerCase()
    : null
  const matchingCommands = useMemo(() => slashQuery === null ? [] : [...BLOCK_TYPES, ...VISUAL_COMMANDS].filter(command => `${command.label} ${command.keywords}`.toLowerCase().includes(slashQuery)), [slashQuery])
  const selectedCommandIndex = Math.max(0, matchingCommands.findIndex(command => command.value === selectedCommand))
  const mentionOptions = useMemo(
    () => mentionRequest ? matchingEntityOptions(entities, mentionRequest.query) : [],
    [entities, mentionRequest],
  )

  function changeType(value: BlockTypeChoice) {
    onChange(convertBlock(block, value))
    if (value === 'image' || value === 'divider') {
      onInsertAfter({ id: crypto.randomUUID(), type: 'paragraph', content: inlineText('') })
      return
    }
    requestAnimationFrame(() => focusEditor(editorIdForBlockType(block.id, value)))
  }

  function chooseCommand(value: SlashCommandChoice) {
    if (value.startsWith('visual:')) {
      onChange({ id: block.id, type: 'paragraph', content: inlineText('') })
      onRequestVisual(value.slice('visual:'.length) as VisualBlockType)
      setSelectedCommand(null)
      return
    }
    const commandBlock = block.type === 'paragraph' ? { ...block, content: inlineText('') } : block
    onChange(convertBlock(commandBlock, value as BlockTypeChoice))
    setSelectedCommand(null)
    if (value === 'image' || value === 'divider') {
      onInsertAfter({ id: crypto.randomUUID(), type: 'paragraph', content: inlineText('') })
      return
    }
    requestAnimationFrame(() => focusEditor(editorIdForBlockType(block.id, value as BlockTypeChoice)))
  }

  function openLink(editor = activeEditorRef.current) {
    if (!editor?.hasSelection()) {
      setLinkError('Highlight some text first.')
      setLinkEditor(null)
      return
    }
    setLinkEditor(editor)
    setLinkUrl('')
    setLinkError('')
  }

  function applyLink(event: FormEvent) {
    event.preventDefault()
    const normalized = normalizeLink(linkUrl)
    if (linkUrl.trim() && !normalized) {
      setLinkError('Use a valid http or https URL.')
      return
    }
    if (!linkEditor?.applyLink(normalized || undefined)) {
      setLinkError('Highlight some text first.')
      return
    }
    setLinkEditor(null)
    setLinkError('')
  }

  function chooseMention(entity: SearchPlayerEntity | SearchTeamEntity) {
    if (!mentionRequest) return
    mentionRequest.editor.insertReference(
      mentionRequest.start,
      mentionRequest.end,
      referenceFromSearchEntity(entity),
    )
    setMentionRequest(null)
    setSelectedMentionIndex(0)
  }

  const inlineProps = {
    onActivate: (editor: InlineTextEditorHandle) => { activeEditorRef.current = editor },
    onRequestLink: openLink,
    onMentionQuery: (request: MentionRequest | null) => {
      setMentionRequest(request)
      setSelectedMentionIndex(0)
    },
  }

  return (
    <section className="group relative -mx-4 px-4 py-1.5" data-block-type={block.type}>
      <div className={`pointer-events-none absolute z-10 hidden w-12 opacity-0 group-hover:pointer-events-auto group-hover:flex group-hover:opacity-100 lg:flex lg:transition-opacity ${block.type === 'visual' ? '-left-12 inset-y-0 items-start pt-5' : '-left-9 top-0 items-start'}`}>
        <div className={`relative flex w-8 flex-col items-center gap-0.5 border border-line bg-panel p-0.5 shadow-lg ${block.type === 'visual' ? 'sticky top-20 after:absolute after:left-full after:top-0 after:h-20 after:w-5 after:[clip-path:polygon(0_0,100%_50%,0_100%)]' : ''}`}>
        <BlockAction label="Add block below" onClick={() => onInsertAfter({ id: crypto.randomUUID(), type: 'paragraph', content: inlineText('') })}><Plus /></BlockAction>
        {block.type === 'visual' ? <BlockAction label="Edit visual" onClick={() => onRequestVisual(block.visual_type, block)}><BarChart3 /></BlockAction> : <label className="relative flex size-7 cursor-pointer items-center justify-center border border-transparent text-ink-muted transition-[color,background-color,border-color,transform] duration-150 hover:-translate-y-px hover:border-electric hover:bg-electric hover:text-mat focus-within:border-electric focus-within:bg-electric focus-within:text-mat" title="Change block type">
          <GripVertical className="size-3.5" />
          <select value={blockChoice(block)} onChange={event => changeType(event.target.value as BlockTypeChoice)} className="absolute inset-0 cursor-pointer opacity-0" aria-label="Change block type">
            {BLOCK_TYPES.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>}
        {isTextBlock(block) ? <BlockAction label="Link selected text" onMouseDown={event => event.preventDefault()} onClick={() => openLink()}><Link2 /></BlockAction> : null}
        <BlockAction label="Move up" disabled={index === 0} onClick={() => onMove(-1)}><ArrowUp /></BlockAction>
        <BlockAction label="Move down" disabled={index === total - 1} onClick={() => onMove(1)}><ArrowDown /></BlockAction>
        <BlockAction label="Delete block" onClick={onRemove} destructive><Trash2 /></BlockAction>
        </div>
      </div>

      {linkEditor ? (
        <form onSubmit={applyLink} className="absolute left-0 top-full z-30 mt-1 flex w-full max-w-md gap-2 border border-line-bright bg-panel p-2 shadow-xl">
          <input autoFocus value={linkUrl} onChange={event => setLinkUrl(event.target.value)} className={metaInputClass} aria-label="Link URL" placeholder="https://…" />
          <button type="submit" className="shrink-0 bg-electric px-3 text-[8px] font-black uppercase tracking-[0.14em] text-mat">Apply</button>
          <button type="button" onClick={() => setLinkEditor(null)} className="shrink-0 px-2 text-[8px] uppercase text-ink-muted">Cancel</button>
        </form>
      ) : null}
      {linkError ? <p className="absolute left-0 top-full z-20 mt-1 bg-panel px-2 py-1 text-[9px] text-ember">{linkError}</p> : null}

      <BlockFields
        block={block}
        onChange={onChange}
        onInsertAfter={onInsertAfter}
        onBackspaceEmpty={onBackspaceEmpty}
        inlineProps={inlineProps}
        onCommandKeyDown={key => {
          if (mentionRequest && mentionOptions.length) {
            if (key === 'Enter') {
              chooseMention(mentionOptions[selectedMentionIndex] ?? mentionOptions[0])
              return true
            }
            const direction = key === 'ArrowDown' ? 1 : -1
            setSelectedMentionIndex(current => (
              current + direction + mentionOptions.length
            ) % mentionOptions.length)
            return true
          }
          if (matchingCommands.length && key === 'Enter') {
            chooseCommand(matchingCommands[selectedCommandIndex].value)
            return true
          }
          if (key === 'Enter') return false
          const direction = key === 'ArrowDown' ? 1 : -1
          if (matchingCommands.length) {
            const nextIndex = (selectedCommandIndex + direction + matchingCommands.length) % matchingCommands.length
            setSelectedCommand(matchingCommands[nextIndex].value)
            return true
          }
          return onNavigateBlock(direction)
        }}
      />

      {matchingCommands.length ? (
        <div className="absolute left-4 top-full z-20 mt-1 w-64 border border-line-bright bg-panel p-1 shadow-2xl">
          <p className="px-3 py-2 font-mono text-[7px] uppercase tracking-[0.18em] text-ink-muted">Turn into</p>
          {matchingCommands.map((command, commandIndex) => (
            <button key={command.value} type="button" onMouseDown={event => event.preventDefault()} onMouseEnter={() => setSelectedCommand(command.value)} onClick={() => chooseCommand(command.value)} className={`flex w-full items-center justify-between px-3 py-2 text-left text-xs ${commandIndex === selectedCommandIndex ? 'bg-electric-dim text-electric' : 'text-ink-dim hover:bg-mat hover:text-ink'}`}>
              <span>{command.label}</span>{commandIndex === selectedCommandIndex ? <span className="font-mono text-[7px] uppercase">Enter</span> : null}
            </button>
          ))}
        </div>
      ) : null}

      {mentionRequest ? (
        <div className="absolute left-4 top-full z-30 mt-1 w-[min(24rem,calc(100vw-3rem))] border border-line-bright bg-panel p-1 shadow-2xl">
          <div className="flex items-center justify-between px-3 py-2">
            <p className="flex items-center gap-2 font-mono text-[7px] uppercase tracking-[0.18em] text-electric"><AtSign className="size-3" /> Add canonical reference</p>
            <span className="font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">References, not subjects</span>
          </div>
          {mentionOptions.length ? mentionOptions.map((entity, optionIndex) => {
            const kind = entity.kind
            const name = kind === 'player' ? entity.canonical_player_name : entity.canonical_team_name
            const membership = entity.memberships[0]
            return (
              <button
                key={`${kind}-${kind === 'player' ? entity.canonical_player_id : entity.canonical_team_id}`}
                type="button"
                onMouseDown={event => event.preventDefault()}
                onMouseEnter={() => setSelectedMentionIndex(optionIndex)}
                onClick={() => chooseMention(entity)}
                className={`flex w-full items-center gap-3 px-3 py-2.5 text-left ${optionIndex === selectedMentionIndex ? 'bg-electric-dim text-electric' : 'text-ink-dim hover:bg-mat hover:text-ink'}`}
              >
                <span className="grid size-7 shrink-0 place-items-center border border-current/25">{kind === 'player' ? <UserRound className="size-3.5" /> : <Shield className="size-3.5" />}</span>
                <span className="min-w-0 flex-1"><span className="block truncate text-xs font-bold">{name}</span><span className="mt-1 block truncate font-mono text-[7px] uppercase tracking-[0.1em] opacity-60">{kind}{membership ? ` · ${membership.competition} · ${membership.season}` : ''}</span></span>
                {optionIndex === selectedMentionIndex ? <span className="font-mono text-[7px] uppercase">Enter</span> : null}
              </button>
            )
          }) : <p className="px-3 py-5 text-center text-xs text-ink-muted">No canonical player or team matches “{mentionRequest.query}”.</p>}
        </div>
      ) : null}
    </section>
  )
}

function BlockFields({
  block,
  onChange,
  onInsertAfter,
  onBackspaceEmpty,
  inlineProps,
  onCommandKeyDown,
}: {
  block: ArticleBlock
  onChange: (block: ArticleBlock) => void
  onInsertAfter: (block: ArticleBlock) => void
  onBackspaceEmpty: () => boolean
  inlineProps: { onActivate: (editor: InlineTextEditorHandle) => void; onRequestLink: (editor: InlineTextEditorHandle) => void; onMentionQuery: (request: MentionRequest | null) => void }
  onCommandKeyDown: (key: 'ArrowDown' | 'ArrowUp' | 'Enter') => boolean
}) {
  const splitIntoParagraph = (before: InlineContent, after: InlineContent) => {
    if (!('content' in block)) return
    onChange({ ...block, content: before })
    const next = { id: crypto.randomUUID(), type: 'paragraph' as const, content: after }
    onInsertAfter(next)
  }

  switch (block.type) {
    case 'heading':
      return <InlineTextEditor {...inlineProps} blockId={block.id} content={block.content} onChange={content => onChange({ ...block, content })} onEnter={splitIntoParagraph} onCommandKeyDown={onCommandKeyDown} onBackspaceEmpty={onBackspaceEmpty} placeholder={block.level === 2 ? 'Section heading' : 'Subheading'} className={block.level === 2 ? 'py-1 text-2xl font-black leading-tight tracking-[-0.035em] text-ink sm:text-3xl' : 'py-1 text-xl font-bold tracking-[-0.025em] text-ink'} />
    case 'paragraph':
      return <InlineTextEditor {...inlineProps} blockId={block.id} content={block.content} onChange={content => onChange({ ...block, content })} onEnter={splitIntoParagraph} onCommandKeyDown={onCommandKeyDown} onBackspaceEmpty={onBackspaceEmpty} placeholder="Write the next thought… Type / for blocks" className="text-[15px] leading-8 text-ink-dim" />
    case 'quote':
      return <div className="border-l-2 border-electric py-2 pl-6"><InlineTextEditor {...inlineProps} blockId={block.id} content={block.content} onChange={content => onChange({ ...block, content })} onEnter={splitIntoParagraph} onCommandKeyDown={onCommandKeyDown} onBackspaceEmpty={onBackspaceEmpty} placeholder="A telling line or key conclusion…" className="text-xl font-semibold leading-8 tracking-[-0.02em] text-ink" /></div>
    case 'callout':
      return (
        <div className={`border p-5 ${block.tone === 'warning' ? 'border-gold/40 bg-gold-dim/35' : 'border-electric/35 bg-electric-dim/35'}`}>
          <select value={block.tone} onChange={event => onChange({ ...block, tone: event.target.value as typeof block.tone })} className="mb-3 bg-transparent font-mono text-[8px] uppercase tracking-[0.18em] text-electric focus:outline-none" aria-label="Callout tone"><option value="insight">Key insight</option><option value="note">Note</option><option value="warning">Caveat</option></select>
          <InlineTextEditor {...inlineProps} blockId={block.id} content={block.content} onChange={content => onChange({ ...block, content })} onEnter={splitIntoParagraph} onCommandKeyDown={onCommandKeyDown} onBackspaceEmpty={onBackspaceEmpty} placeholder="Give this observation extra weight…" className="text-sm leading-6 text-ink" />
        </div>
      )
    case 'bulleted_list':
    case 'numbered_list':
      return (
        <div className="space-y-1">
          {block.items.map((item, itemIndex) => (
            <div key={`${block.id}-${itemIndex}`} className="flex items-start gap-3">
              <span className={`w-6 shrink-0 text-right font-mono leading-7 text-electric ${block.type === 'numbered_list' ? 'text-sm' : 'text-xl'}`}>{block.type === 'numbered_list' ? `${itemIndex + 1}.` : '•'}</span>
              <InlineTextEditor
                {...inlineProps}
                blockId={`${block.id}-${itemIndex}`}
                content={item}
                onChange={content => { const items = [...block.items]; items[itemIndex] = content; onChange({ ...block, items }) }}
                onEnter={(before, after) => {
                  if (!plainText(item).trim() && itemIndex === block.items.length - 1) {
                    if (block.items.length === 1) {
                      onChange({ id: block.id, type: 'paragraph', content: inlineText('') })
                      requestAnimationFrame(() => focusEditor(block.id))
                    } else {
                      onChange({ ...block, items: block.items.slice(0, -1) })
                      onInsertAfter({ id: crypto.randomUUID(), type: 'paragraph', content: inlineText('') })
                    }
                    return
                  }
                  const items = [...block.items]
                  items.splice(itemIndex, 1, before, after)
                  onChange({ ...block, items })
                  requestAnimationFrame(() => focusEditor(`${block.id}-${itemIndex + 1}`))
                }}
                onCommandKeyDown={onCommandKeyDown}
                onBackspaceEmpty={() => {
                  if (block.items.length === 1) return onBackspaceEmpty()
                  const items = block.items.filter((_, index) => index !== itemIndex)
                  onChange({ ...block, items })
                  requestAnimationFrame(() => focusEditor(`${block.id}-${Math.max(0, itemIndex - 1)}`, 'end'))
                  return true
                }}
                placeholder="List item"
                className="min-w-0 flex-1 text-[15px] leading-7 text-ink-dim"
              />
            </div>
          ))}
        </div>
      )
    case 'image':
      return (
        <div className="space-y-3 border border-line bg-mat p-4">
          {block.url ? <img src={block.url} alt={block.alt} className="max-h-96 w-full object-contain" /> : <div className="grid aspect-[16/7] place-items-center border border-dashed border-line-bright text-[10px] uppercase tracking-[0.16em] text-ink-muted">Paste a public image URL below</div>}
          <label className="block space-y-1.5"><FieldLabel>Image URL</FieldLabel><input type="url" value={block.url} onChange={event => onChange({ ...block, url: event.target.value })} placeholder="https://…" className={metaInputClass} /></label>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="space-y-1.5"><FieldLabel>Caption</FieldLabel><input value={block.caption} onChange={event => onChange({ ...block, caption: event.target.value })} placeholder="Source or context" className={metaInputClass} /></label>
            <label className="space-y-1.5"><FieldLabel>Alt text</FieldLabel><input value={block.alt} onChange={event => onChange({ ...block, alt: event.target.value })} placeholder="Describe the image" className={metaInputClass} /></label>
          </div>
        </div>
      )
    case 'visual':
      return <VisualAnalysisBlock block={block} editor />
    case 'divider':
      return <div className="py-7"><hr className="border-0 border-t border-line" /></div>
  }
}

function matchingEntityOptions(
  entities: SearchEntitiesResponse | undefined,
  query: string,
): Array<SearchPlayerEntity | SearchTeamEntity> {
  if (!entities) return []
  const needle = foldForSearch(query.trim())
  const players = entities.players.filter(entity => !needle || foldForSearch(entity.canonical_player_name).includes(needle)).slice(0, 5)
  const teams = entities.teams.filter(entity => !needle || foldForSearch(entity.canonical_team_name).includes(needle)).slice(0, 5)
  return [...players, ...teams]
    .sort((left, right) => {
      const leftName = left.kind === 'player' ? left.canonical_player_name : left.canonical_team_name
      const rightName = right.kind === 'player' ? right.canonical_player_name : right.canonical_team_name
      const leftStarts = needle && foldForSearch(leftName).startsWith(needle) ? 0 : 1
      const rightStarts = needle && foldForSearch(rightName).startsWith(needle) ? 0 : 1
      return leftStarts - rightStarts || leftName.localeCompare(rightName)
    })
    .slice(0, 8)
}

function referenceFromSearchEntity(entity: SearchPlayerEntity | SearchTeamEntity): EditorialEntityReference {
  if (entity.kind === 'player') {
    const membership = entity.memberships[0]
    const context = membership ? {
      competition_code: membership.competition,
      season_label: membership.season,
      competition_season_id: membership.competition_season_id,
      ...(membership.canonical_team_id && membership.canonical_team_name
        ? { team: { id: membership.canonical_team_id, name: membership.canonical_team_name } }
        : {}),
    } : undefined
    return { kind: 'player', id: entity.canonical_player_id, name: entity.canonical_player_name, ...(context ? { context } : {}) }
  }
  const membership = entity.memberships[0]
  const context = membership ? {
    competition_code: membership.competition,
    season_label: membership.season,
    competition_season_id: membership.competition_season_id,
  } : undefined
  return { kind: 'team', id: entity.canonical_team_id, name: entity.canonical_team_name, ...(context ? { context } : {}) }
}

function convertBlock(block: ArticleBlock, choice: BlockTypeChoice): ArticleBlock {
  const content = contentFromBlock(block)
  const id = block.id
  switch (choice) {
    case 'paragraph': return { id, type: 'paragraph', content }
    case 'heading:2': return { id, type: 'heading', level: 2, content }
    case 'heading:3': return { id, type: 'heading', level: 3, content }
    case 'quote': return { id, type: 'quote', content }
    case 'callout': return { id, type: 'callout', tone: 'insight', content }
    case 'bulleted_list': return { id, type: 'bulleted_list', items: [content] }
    case 'numbered_list': return { id, type: 'numbered_list', items: [content] }
    case 'image': return { id, type: 'image', url: '', caption: '', alt: '' }
    case 'divider': return { id, type: 'divider' }
  }
}

function contentFromBlock(block: ArticleBlock): InlineContent {
  if (block.type === 'heading' || block.type === 'paragraph' || block.type === 'quote' || block.type === 'callout') return block.content
  if (block.type === 'bulleted_list' || block.type === 'numbered_list') return block.items[0] ?? inlineText('')
  if (block.type === 'image' || block.type === 'visual') return inlineText(block.caption || block.alt)
  return inlineText('')
}

function blockChoice(block: ArticleBlock): BlockTypeChoice {
  if (block.type === 'visual') return 'paragraph'
  return block.type === 'heading' ? `heading:${block.level}` : block.type
}

function isTextBlock(block: ArticleBlock): boolean {
  return block.type !== 'image' && block.type !== 'visual' && block.type !== 'divider'
}

function normalizeLink(value: string): string {
  if (!value.trim()) return ''
  try {
    const url = new URL(value.trim())
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}

function focusEditor(blockId: string, position: 'start' | 'end' = 'start') {
  const editor = document.querySelector<HTMLElement>(`[data-editor-block-id="${blockId}"]`)
  if (!editor) return
  editor.focus()
  const range = document.createRange()
  range.selectNodeContents(editor)
  range.collapse(position === 'start')
  const selection = window.getSelection()
  selection?.removeAllRanges()
  selection?.addRange(range)
}

function editorIdForBlockType(blockId: string, type: BlockTypeChoice): string {
  return type === 'bulleted_list' || type === 'numbered_list' ? `${blockId}-0` : blockId
}

function FieldLabel({ children }: { children: string }) {
  return <span className="block font-mono text-[8px] uppercase tracking-[0.16em] text-ink-muted">{children}</span>
}

function BlockAction({ children, label, onClick, onMouseDown, disabled = false, destructive = false }: { children: ReactElement<{ className?: string }>; label: string; onClick: () => void; onMouseDown?: (event: MouseEvent<HTMLButtonElement>) => void; disabled?: boolean; destructive?: boolean }) {
  return <button type="button" onMouseDown={onMouseDown} onClick={onClick} disabled={disabled} className={`grid size-7 place-items-center border border-transparent text-ink-muted transition-[color,background-color,border-color,transform] duration-150 hover:-translate-y-px focus-visible:-translate-y-px focus-visible:outline-none active:translate-y-0 disabled:pointer-events-none disabled:opacity-25 ${destructive ? 'hover:border-ember hover:bg-ember hover:text-mat focus-visible:border-ember focus-visible:bg-ember focus-visible:text-mat' : 'hover:border-electric hover:bg-electric hover:text-mat focus-visible:border-electric focus-visible:bg-electric focus-visible:text-mat'}`} aria-label={label} title={label}><span className="[&>svg]:size-3.5">{children}</span></button>
}
