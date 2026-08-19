import { ArrowDown, ArrowUp, AtSign, BarChart3, Bold, ChevronDown, CopyPlus, FileImage, Heading2, HelpCircle, Italic, Lightbulb, Link2, List, ListOrdered, Menu, Minus, Pilcrow, Plus, Quote, SidebarClose, SidebarOpen, Trash2, X } from 'lucide-react'
import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import type { ArticleBlock } from '../../lib/editorial'
import type { BlockEditorHandle } from './BlockEditor'
import type { InlineSelectionState } from './InlineTextEditor'
import { BLOCK_COMMANDS, EDITOR_COMMANDS, blockChoice, blockLabel, type BlockTypeChoice, type EditorCommandChoice } from './editorCommands'

export function EditorToolbar({
  activeBlock,
  activeIndex,
  total,
  activeHandle,
  selectionState,
  inspectorOpen,
  onInsert,
  onChangeType,
  onMove,
  onDuplicate,
  onRemove,
  onToggleInspector,
}: {
  activeBlock?: ArticleBlock
  activeIndex: number
  total: number
  activeHandle?: BlockEditorHandle
  selectionState: InlineSelectionState
  inspectorOpen: boolean
  onInsert: (choice: EditorCommandChoice, afterIndex: number) => void
  onChangeType: (choice: BlockTypeChoice) => void
  onMove: (direction: -1 | 1) => void
  onDuplicate: () => void
  onRemove: () => void
  onToggleInspector: () => void
}) {
  const toolbarRef = useRef<HTMLDivElement>(null)
  const [desktopMenu, setDesktopMenu] = useState<'add' | 'help' | null>(null)
  const [mobileSheet, setMobileSheet] = useState<'add' | 'tools' | 'help' | null>(null)
  const hasTextHandle = Boolean(activeHandle && activeBlock && !['image', 'visual', 'divider'].includes(activeBlock.type))

  useEffect(() => {
    if (!desktopMenu && !mobileSheet) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setDesktopMenu(null)
        setMobileSheet(null)
      }
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [desktopMenu, mobileSheet])

  useEffect(() => {
    if (!desktopMenu) return
    const closeOutside = (event: PointerEvent) => {
      const menuRoot = toolbarRef.current?.querySelector(`[data-editor-menu-root="${desktopMenu}"]`)
      if (!menuRoot?.contains(event.target as Node)) setDesktopMenu(null)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [desktopMenu])

  const insert = (choice: EditorCommandChoice) => {
    onInsert(choice, activeIndex)
    setDesktopMenu(null)
    setMobileSheet(null)
  }

  return (
    <div ref={toolbarRef} className="sticky top-16 z-20 border-b border-line bg-panel/95 px-3 py-2 shadow-[0_10px_24px_rgba(0,0,0,0.16)] backdrop-blur sm:px-5">
      <div className="mx-auto flex max-w-[820px] items-center justify-between gap-2">
        <div className="relative hidden min-w-0 items-center gap-1 sm:flex">
          <div className="relative" data-editor-menu-root="add">
            <ToolbarButton strong label="Add block" onClick={() => setDesktopMenu(current => current === 'add' ? null : 'add')}><Plus /></ToolbarButton>
            {desktopMenu === 'add' ? <div className="absolute left-0 top-full z-30 mt-2 w-[22rem] border border-line-bright bg-panel p-2 shadow-2xl"><BlockCommandMenu onChoose={insert} /></div> : null}
          </div>
          <div className="mx-1 h-6 w-px bg-line" />
          <label className="relative flex h-9 items-center gap-2 border border-line bg-mat px-3 text-[9px] font-bold text-ink-dim hover:border-electric">
            <span className="text-ink-muted">Block</span>
            <span className="max-w-28 truncate text-ink">{activeBlock ? blockLabel(activeBlock) : 'Text'}</span>
            <ChevronDown className="size-3 text-ink-muted" />
            <select
              value={activeBlock && activeBlock.type !== 'visual' ? blockChoice(activeBlock) : 'paragraph'}
              onChange={event => onChangeType(event.target.value as BlockTypeChoice)}
              disabled={!activeBlock || activeBlock.type === 'visual'}
              className="absolute inset-0 cursor-pointer opacity-0 disabled:cursor-not-allowed"
              aria-label="Change current block type"
            >
              {BLOCK_COMMANDS.map(command => <option key={command.value} value={command.value}>{command.label}</option>)}
            </select>
          </label>
          <ToolbarIcon label="Bold (⌘B)" active={selectionState.bold} disabled={!hasTextHandle} onClick={() => activeHandle?.toggleFormat('bold')}><Bold /></ToolbarIcon>
          <ToolbarIcon label="Italic (⌘I)" active={selectionState.italic} disabled={!hasTextHandle} onClick={() => activeHandle?.toggleFormat('italic')}><Italic /></ToolbarIcon>
          <ToolbarIcon label="Link selected text (⌘K)" disabled={!hasTextHandle} onClick={() => activeHandle?.openLink()}><Link2 /></ToolbarIcon>
          <ToolbarIcon label="Reference a player or team" disabled={!hasTextHandle} onClick={() => activeHandle?.openReferencePicker()}><AtSign /></ToolbarIcon>
          <div className="mx-1 h-6 w-px bg-line" />
          <ToolbarIcon label="Move block up" disabled={activeIndex <= 0} onClick={() => onMove(-1)}><ArrowUp /></ToolbarIcon>
          <ToolbarIcon label="Move block down" disabled={activeIndex < 0 || activeIndex >= total - 1} onClick={() => onMove(1)}><ArrowDown /></ToolbarIcon>
          <ToolbarIcon label="Duplicate current block" disabled={!activeBlock} onClick={onDuplicate}><CopyPlus /></ToolbarIcon>
          <ToolbarIcon label="Delete current block" disabled={!activeBlock} destructive onClick={onRemove}><Trash2 /></ToolbarIcon>
        </div>

        <div className="flex flex-1 items-center gap-2 sm:hidden">
          <ToolbarButton strong label="Add" onClick={() => setMobileSheet('add')}><Plus /></ToolbarButton>
          <button type="button" onClick={() => setMobileSheet('tools')} className="flex h-9 min-w-0 flex-1 items-center justify-between border border-line bg-mat px-3 text-left text-[9px] font-bold uppercase tracking-[0.12em] text-ink-dim">
            <span className="truncate">{activeBlock ? blockLabel(activeBlock) : 'Editor tools'}</span><Menu className="size-3.5 text-electric" />
          </button>
        </div>

        <div className="hidden items-center gap-1 sm:flex">
          <div className="relative" data-editor-menu-root="help">
            <ToolbarIcon label="Editor help" onClick={() => setDesktopMenu(current => current === 'help' ? null : 'help')}><HelpCircle /></ToolbarIcon>
            {desktopMenu === 'help' ? <div className="absolute right-0 top-full z-30 mt-2 w-80 border border-line-bright bg-panel p-5 shadow-2xl"><EditorHelp /></div> : null}
          </div>
          <ToolbarIcon label={inspectorOpen ? 'Hide article details' : 'Show article details'} onClick={onToggleInspector}>{inspectorOpen ? <SidebarClose /> : <SidebarOpen />}</ToolbarIcon>
        </div>
      </div>

      {mobileSheet ? (
        <MobileSheet title={mobileSheet === 'add' ? 'Add a block' : mobileSheet === 'help' ? 'Editor help' : activeBlock ? `${blockLabel(activeBlock)} tools` : 'Editor tools'} onClose={() => setMobileSheet(null)}>
          {mobileSheet === 'add' ? <BlockCommandMenu onChoose={insert} /> : null}
          {mobileSheet === 'help' ? <EditorHelp /> : null}
          {mobileSheet === 'tools' ? (
            <div className="space-y-5">
              {activeBlock && activeBlock.type !== 'visual' ? <label className="block"><span className="mb-2 block font-mono text-[8px] uppercase tracking-[0.16em] text-ink-muted">Block type</span><select value={blockChoice(activeBlock)} onChange={event => onChangeType(event.target.value as BlockTypeChoice)} className="h-11 w-full border border-line-bright bg-mat px-3 text-sm text-ink focus:border-electric focus:outline-none">{BLOCK_COMMANDS.map(command => <option key={command.value} value={command.value}>{command.label}</option>)}</select></label> : null}
              <div className="grid grid-cols-2 gap-2">
                <SheetAction active={selectionState.bold} disabled={!hasTextHandle} onClick={() => activeHandle?.toggleFormat('bold')} icon={<Bold />}>Bold</SheetAction>
                <SheetAction active={selectionState.italic} disabled={!hasTextHandle} onClick={() => activeHandle?.toggleFormat('italic')} icon={<Italic />}>Italic</SheetAction>
                <SheetAction disabled={!hasTextHandle} onClick={() => { setMobileSheet(null); activeHandle?.openLink() }} icon={<Link2 />}>Add link</SheetAction>
                <SheetAction disabled={!hasTextHandle} onClick={() => { setMobileSheet(null); activeHandle?.openReferencePicker() }} icon={<AtSign />}>Reference</SheetAction>
                <SheetAction disabled={activeIndex <= 0} onClick={() => onMove(-1)} icon={<ArrowUp />}>Move up</SheetAction>
                <SheetAction disabled={activeIndex < 0 || activeIndex >= total - 1} onClick={() => onMove(1)} icon={<ArrowDown />}>Move down</SheetAction>
                <SheetAction disabled={!activeBlock} onClick={onDuplicate} icon={<CopyPlus />}>Duplicate</SheetAction>
                <SheetAction onClick={() => { setMobileSheet(null); onToggleInspector() }} icon={inspectorOpen ? <SidebarClose /> : <SidebarOpen />}>{inspectorOpen ? 'Hide details' : 'Show details'}</SheetAction>
                <SheetAction disabled={!activeBlock} destructive onClick={onRemove} icon={<Trash2 />}>Delete block</SheetAction>
              </div>
              <button type="button" onClick={() => setMobileSheet('help')} className="flex w-full items-center gap-3 border-t border-line pt-4 text-left text-xs text-ink-dim"><HelpCircle className="size-4 text-electric" /> Keyboard shortcuts and block help</button>
            </div>
          ) : null}
        </MobileSheet>
      ) : null}
    </div>
  )
}

export function BlockInsertionControl({ afterIndex, onInsert }: { afterIndex: number; onInsert: (choice: EditorCommandChoice, afterIndex: number) => void }) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => {
    if (!open) return
    const closeOutside = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', closeOutside)
    return () => document.removeEventListener('pointerdown', closeOutside)
  }, [open])
  return (
    <div ref={rootRef} className="group/insert relative -my-2 flex h-8 items-center justify-center" data-editor-insertion-after={afterIndex}>
      <div className={`absolute inset-x-0 top-1/2 border-t transition-colors ${open ? 'border-electric/60' : 'border-transparent group-hover/insert:border-line-bright group-focus-within/insert:border-line-bright'}`} />
      <button type="button" onClick={() => setOpen(current => !current)} className={`relative z-10 grid size-6 place-items-center rounded-full border bg-panel transition-[opacity,color,border-color,transform] hover:scale-105 hover:border-electric hover:text-electric focus-visible:border-electric focus-visible:text-electric focus-visible:outline-none sm:opacity-0 sm:group-hover/insert:opacity-100 sm:group-focus-within/insert:opacity-100 ${open ? 'border-electric text-electric opacity-100' : 'border-line-bright text-ink-muted opacity-70'}`} aria-label="Insert block here" aria-expanded={open}><Plus className="size-3" /></button>
      {open ? <div className="absolute left-1/2 top-7 z-30 w-[min(22rem,calc(100vw-2rem))] -translate-x-1/2 border border-line-bright bg-panel p-2 shadow-2xl"><BlockCommandMenu onChoose={choice => { onInsert(choice, afterIndex); setOpen(false) }} /></div> : null}
    </div>
  )
}

export function EditorStarter({ onChoose }: { onChoose: (choice: 'paragraph' | 'heading:2' | 'callout' | 'visual:custom_chart') => void }) {
  return (
    <section className="mb-8 border border-electric/25 bg-electric/[0.035] p-5 sm:p-6" aria-labelledby="editor-starter-title">
      <p className="font-mono text-[8px] uppercase tracking-[0.2em] text-electric">New analysis</p>
      <h2 id="editor-starter-title" className="mt-2 text-xl font-black tracking-[-0.025em] text-ink">Start with a clear first move.</h2>
      <p className="mt-2 text-xs leading-5 text-ink-muted">Choose a starting block. You can change it or add something else at any time.</p>
      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        <StarterChoice icon={<Pilcrow />} title="Write text" description="Begin with a paragraph" onClick={() => onChoose('paragraph')} />
        <StarterChoice icon={<Heading2 />} title="Add heading" description="Open with a section title" onClick={() => onChoose('heading:2')} />
        <StarterChoice icon={<BarChart3 />} title="Add visual" description="Build a data-led block" onClick={() => onChoose('visual:custom_chart')} />
        <StarterChoice icon={<Lightbulb />} title="Add key insight" description="Lead with the conclusion" onClick={() => onChoose('callout')} />
      </div>
    </section>
  )
}

export function BlockCommandMenu({ onChoose }: { onChoose: (choice: EditorCommandChoice) => void }) {
  const groups = ['Writing', 'Data visuals', 'Media'] as const
  return <div className="max-h-[min(32rem,62svh)] overflow-y-auto">{groups.map(group => <div key={group} className="mb-2 last:mb-0"><p className="px-2 py-2 font-mono text-[7px] uppercase tracking-[0.18em] text-ink-muted">{group}</p><div className="grid gap-1">{EDITOR_COMMANDS.filter(command => command.group === group).map(command => <button key={command.value} type="button" onClick={() => onChoose(command.value)} className="group flex items-center gap-3 px-2 py-2.5 text-left hover:bg-electric-dim focus-visible:bg-electric-dim focus-visible:outline-none"><span className="grid size-8 shrink-0 place-items-center border border-line text-ink-muted group-hover:border-electric/40 group-hover:text-electric">{commandIcon(command.value)}</span><span className="min-w-0"><span className="block text-xs font-bold text-ink">{command.label}</span><span className="mt-0.5 block text-[10px] leading-4 text-ink-muted">{command.description}</span></span></button>)}</div></div>)}</div>
}

function EditorHelp() {
  return <div><p className="font-mono text-[8px] uppercase tracking-[0.18em] text-electric">Writing shortcuts</p><dl className="mt-4 grid grid-cols-[1fr_auto] gap-x-4 gap-y-3 text-xs"><dt className="text-ink-dim">Bold selected text</dt><dd><Key>⌘ B</Key></dd><dt className="text-ink-dim">Italicise selected text</dt><dd><Key>⌘ I</Key></dd><dt className="text-ink-dim">Link selected text</dt><dd><Key>⌘ K</Key></dd><dt className="text-ink-dim">Open the block menu</dt><dd><Key>/</Key></dd><dt className="text-ink-dim">Reference a player or team</dt><dd><Key>@</Key></dd><dt className="text-ink-dim">New paragraph</dt><dd><Key>Enter</Key></dd><dt className="text-ink-dim">Line break</dt><dd><Key>⇧ Enter</Key></dd></dl><p className="mt-5 border-t border-line pt-4 text-[10px] leading-5 text-ink-muted">Use the toolbar or the + between blocks when you do not want to remember a shortcut.</p></div>
}

function MobileSheet({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return createPortal(<div className="fixed inset-0 z-50 flex items-end bg-mat/75 backdrop-blur-sm sm:hidden" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose() }}><section role="dialog" aria-modal="true" aria-label={title} className="max-h-[82svh] w-full overflow-y-auto border-t border-line-bright bg-panel px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3 shadow-2xl"><div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line-bright" /><header className="mb-4 flex items-center justify-between gap-4"><h2 className="text-base font-black text-ink">{title}</h2><button type="button" onClick={onClose} className="grid size-9 place-items-center border border-line text-ink-muted" aria-label="Close"><X className="size-4" /></button></header>{children}</section></div>, document.body)
}

function ToolbarButton({ label, children, onClick, strong = false }: { label: string; children: ReactNode; onClick: () => void; strong?: boolean }) {
  return <button type="button" onClick={onClick} className={`inline-flex h-9 items-center gap-2 px-3 text-[8px] font-black uppercase tracking-[0.13em] ${strong ? 'bg-electric text-mat hover:bg-ink' : 'border border-line text-ink-dim hover:border-electric'}`}><span className="[&>svg]:size-3.5">{children}</span>{label}</button>
}

function ToolbarIcon({ label, children, onClick, disabled = false, destructive = false, active = false }: { label: string; children: ReactNode; onClick: () => void; disabled?: boolean; destructive?: boolean; active?: boolean }) {
  const preserveSelection = (event: MouseEvent<HTMLButtonElement>) => event.preventDefault()
  return <button type="button" title={label} aria-label={label} aria-pressed={active || undefined} disabled={disabled} onMouseDown={preserveSelection} onClick={onClick} className={`grid size-9 place-items-center border transition-colors disabled:pointer-events-none disabled:opacity-25 ${active ? 'border-electric/50 bg-electric text-mat shadow-[0_0_16px_rgba(74,158,245,0.16)]' : destructive ? 'border-transparent text-ink-muted hover:border-ember/50 hover:bg-ember-dim hover:text-ember' : 'border-transparent text-ink-muted hover:border-electric/50 hover:bg-electric-dim hover:text-electric'}`}><span className="[&>svg]:size-3.5">{children}</span></button>
}

function SheetAction({ children, icon, onClick, disabled = false, destructive = false, active = false }: { children: ReactNode; icon: ReactNode; onClick: () => void; disabled?: boolean; destructive?: boolean; active?: boolean }) {
  return <button type="button" onClick={onClick} aria-pressed={active || undefined} disabled={disabled} className={`flex min-h-12 items-center gap-3 border px-3 text-left text-xs font-bold disabled:opacity-35 ${active ? 'border-electric bg-electric text-mat' : destructive ? 'border-ember/30 text-ember' : 'border-line text-ink-dim'}`}><span className="[&>svg]:size-4">{icon}</span>{children}</button>
}

function StarterChoice({ icon, title, description, onClick }: { icon: ReactNode; title: string; description: string; onClick: () => void }) {
  return <button type="button" onClick={onClick} className="group flex items-center gap-3 border border-line bg-panel/70 p-3 text-left transition-[border-color,transform] hover:-translate-y-px hover:border-electric focus-visible:border-electric focus-visible:outline-none"><span className="grid size-9 shrink-0 place-items-center border border-line text-ink-muted group-hover:border-electric/40 group-hover:text-electric [&>svg]:size-4">{icon}</span><span><span className="block text-xs font-bold text-ink">{title}</span><span className="mt-1 block text-[10px] text-ink-muted">{description}</span></span></button>
}

function Key({ children }: { children: ReactNode }) {
  return <kbd className="inline-flex min-w-8 justify-center border border-line-bright bg-mat px-1.5 py-1 font-mono text-[8px] text-ink">{children}</kbd>
}

function commandIcon(choice: EditorCommandChoice) {
  if (choice === 'paragraph') return <Pilcrow className="size-3.5" />
  if (choice.startsWith('heading:')) return <Heading2 className="size-3.5" />
  if (choice === 'bulleted_list') return <List className="size-3.5" />
  if (choice === 'numbered_list') return <ListOrdered className="size-3.5" />
  if (choice === 'quote') return <Quote className="size-3.5" />
  if (choice === 'callout') return <Lightbulb className="size-3.5" />
  if (choice === 'image') return <FileImage className="size-3.5" />
  if (choice === 'divider') return <Minus className="size-3.5" />
  return <BarChart3 className="size-3.5" />
}
