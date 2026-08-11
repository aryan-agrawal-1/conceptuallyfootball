import { forwardRef, useCallback, useEffect, useImperativeHandle, useLayoutEffect, useMemo, useRef, type KeyboardEvent } from 'react'
import { plainText, type InlineContent } from '../../lib/editorial'

export interface InlineTextEditorHandle {
  applyLink: (url?: string) => boolean
  focus: (position?: 'start' | 'end') => void
  hasSelection: () => boolean
}

interface InlineTextEditorProps {
  blockId: string
  content: InlineContent
  onChange: (content: InlineContent) => void
  onEnter: (before: InlineContent, after: InlineContent) => void
  onRequestLink?: (editor: InlineTextEditorHandle) => void
  onActivate?: (editor: InlineTextEditorHandle) => void
  onCommandKeyDown?: (key: 'ArrowDown' | 'ArrowUp' | 'Enter') => boolean
  onBackspaceEmpty?: () => boolean
  placeholder: string
  className?: string
}

export const InlineTextEditor = forwardRef<InlineTextEditorHandle, InlineTextEditorProps>(function InlineTextEditor({
  blockId,
  content,
  onChange,
  onEnter,
  onRequestLink,
  onActivate,
  onCommandKeyDown,
  onBackspaceEmpty,
  placeholder,
  className = '',
}, forwardedRef) {
  const rootRef = useRef<HTMLDivElement>(null)
  const savedSelectionRef = useRef<{ start: number; end: number } | null>(null)
  const onChangeRef = useRef(onChange)
  const onEnterRef = useRef(onEnter)
  const onRequestLinkRef = useRef(onRequestLink)
  const onActivateRef = useRef(onActivate)
  const onCommandKeyDownRef = useRef(onCommandKeyDown)
  const onBackspaceEmptyRef = useRef(onBackspaceEmpty)
  useEffect(() => {
    onChangeRef.current = onChange
    onEnterRef.current = onEnter
    onRequestLinkRef.current = onRequestLink
    onActivateRef.current = onActivate
    onCommandKeyDownRef.current = onCommandKeyDown
    onBackspaceEmptyRef.current = onBackspaceEmpty
  }, [onActivate, onBackspaceEmpty, onChange, onCommandKeyDown, onEnter, onRequestLink])

  const rememberSelection = useCallback(() => {
    const root = rootRef.current
    if (!root) return
    const selection = selectionOffsets(root)
    if (selection) savedSelectionRef.current = selection
  }, [])

  const api = useMemo<InlineTextEditorHandle>(() => ({
    applyLink(url) {
      const root = rootRef.current
      const selection = savedSelectionRef.current
      if (!root || !selection || selection.start === selection.end) return false
      const next = applyLinkToContent(readContent(root), selection.start, selection.end, url)
      renderContent(root, next)
      onChangeRef.current(next)
      root.focus()
      restoreSelection(root, selection.start, selection.end)
      return true
    },
    focus(position = 'end') {
      const root = rootRef.current
      if (!root) return
      root.focus()
      const offset = position === 'start' ? 0 : readContent(root).reduce((total, run) => total + run.text.length, 0)
      restoreSelection(root, offset, offset)
    },
    hasSelection() {
      const selection = savedSelectionRef.current
      return Boolean(selection && selection.start !== selection.end)
    },
  }), [])

  useImperativeHandle(forwardedRef, () => api, [api])

  useLayoutEffect(() => {
    const root = rootRef.current
    if (!root) return
    if (sameContent(readContent(root), content)) return
    renderContent(root, content)
  }, [content])

  function emitContent() {
    const root = rootRef.current
    if (!root) return
    const next = readContent(root)
    onChangeRef.current(next)
    rememberSelection()
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
      event.preventDefault()
      rememberSelection()
      onRequestLinkRef.current?.(api)
      return
    }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (onCommandKeyDownRef.current?.(event.key)) event.preventDefault()
      return
    }
    if (event.key === 'Backspace') {
      const root = rootRef.current
      const current = root ? readContent(root) : content
      const selection = root ? selectionOffsets(root) : null
      if (contentIsVisuallyEmpty(current) && selection?.start === 0 && selection.end === 0 && onBackspaceEmptyRef.current?.()) {
        event.preventDefault()
      }
      return
    }
    if (event.key !== 'Enter' || event.shiftKey) return
    event.preventDefault()
    rememberSelection()
    if (onCommandKeyDownRef.current?.('Enter')) return
    const root = rootRef.current
    if (!root) return
    const current = readContent(root)
    const offset = savedSelectionRef.current?.start ?? plainText(current).length
    const [before, after] = splitContent(current, offset)
    onEnterRef.current(before, after)
  }

  return (
    <div
      ref={rootRef}
      data-editor-block-id={blockId}
      data-placeholder={placeholder}
      contentEditable
      suppressContentEditableWarning
      role="textbox"
      aria-multiline="false"
      className={`min-h-[1em] whitespace-pre-wrap break-words outline-none empty:before:pointer-events-none empty:before:text-ink-muted empty:before:content-[attr(data-placeholder)] ${className}`}
      onInput={emitContent}
      onKeyDown={handleKeyDown}
      onFocus={() => onActivateRef.current?.(api)}
      onMouseUp={() => { rememberSelection(); onActivateRef.current?.(api) }}
      onKeyUp={() => { rememberSelection(); onActivateRef.current?.(api) }}
      onBlur={rememberSelection}
      onClick={event => {
        if ((event.target as HTMLElement).closest('a')) event.preventDefault()
      }}
    />
  )
})

function readContent(root: HTMLElement): InlineContent {
  const runs: InlineContent = []
  const visit = (node: Node, inheritedLink?: string) => {
    if (node.nodeType === Node.TEXT_NODE) {
      appendRun(runs, node.textContent ?? '', inheritedLink)
      return
    }
    if (!(node instanceof HTMLElement)) return
    if (node.tagName === 'BR') {
      appendRun(runs, '\n', inheritedLink)
      return
    }
    const link = node instanceof HTMLAnchorElement ? safeUrl(node.href) : inheritedLink
    node.childNodes.forEach(child => visit(child, link || inheritedLink))
  }
  root.childNodes.forEach(node => visit(node))
  return runs.length ? runs : [{ text: '' }]
}

function renderContent(root: HTMLElement, content: InlineContent) {
  root.replaceChildren()
  for (const run of content) {
    const link = run.link ? safeUrl(run.link) : ''
    if (link) {
      const anchor = document.createElement('a')
      anchor.href = link
      anchor.target = '_blank'
      anchor.rel = 'noreferrer'
      anchor.className = 'border-b border-electric/60 text-electric'
      anchor.append(document.createTextNode(run.text))
      root.append(anchor)
    } else if (run.text) {
      root.append(document.createTextNode(run.text))
    }
  }
}

function appendRun(runs: InlineContent, text: string, link?: string) {
  if (!text) return
  const previous = runs.at(-1)
  if (previous && previous.link === link) previous.text += text
  else runs.push({ text, ...(link ? { link } : {}) })
}

function selectionOffsets(root: HTMLElement): { start: number; end: number } | null {
  const selection = window.getSelection()
  if (!selection?.rangeCount) return null
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) return null
  const beforeStart = range.cloneRange()
  beforeStart.selectNodeContents(root)
  beforeStart.setEnd(range.startContainer, range.startOffset)
  const beforeEnd = range.cloneRange()
  beforeEnd.selectNodeContents(root)
  beforeEnd.setEnd(range.endContainer, range.endOffset)
  return { start: beforeStart.toString().length, end: beforeEnd.toString().length }
}

function restoreSelection(root: HTMLElement, start: number, end: number) {
  const range = document.createRange()
  const selection = window.getSelection()
  let cursor = 0
  let startPoint: { node: Node; offset: number } | null = null
  let endPoint: { node: Node; offset: number } | null = null
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  let node = walker.nextNode()
  while (node) {
    const length = node.textContent?.length ?? 0
    if (!startPoint && start <= cursor + length) startPoint = { node, offset: Math.max(0, start - cursor) }
    if (!endPoint && end <= cursor + length) {
      endPoint = { node, offset: Math.max(0, end - cursor) }
      break
    }
    cursor += length
    node = walker.nextNode()
  }
  if (!startPoint || !endPoint) {
    range.selectNodeContents(root)
    range.collapse(false)
  } else {
    range.setStart(startPoint.node, startPoint.offset)
    range.setEnd(endPoint.node, endPoint.offset)
  }
  selection?.removeAllRanges()
  selection?.addRange(range)
}

function splitContent(content: InlineContent, offset: number): [InlineContent, InlineContent] {
  const before: InlineContent = []
  const after: InlineContent = []
  let cursor = 0
  for (const run of content) {
    const boundary = offset - cursor
    if (boundary <= 0) appendRun(after, run.text, run.link)
    else if (boundary >= run.text.length) appendRun(before, run.text, run.link)
    else {
      appendRun(before, run.text.slice(0, boundary), run.link)
      appendRun(after, run.text.slice(boundary), run.link)
    }
    cursor += run.text.length
  }
  return [before.length ? before : [{ text: '' }], after.length ? after : [{ text: '' }]]
}

function applyLinkToContent(content: InlineContent, start: number, end: number, url?: string): InlineContent {
  const result: InlineContent = []
  let cursor = 0
  for (const run of content) {
    const runStart = cursor
    const runEnd = cursor + run.text.length
    const overlapStart = Math.max(start, runStart)
    const overlapEnd = Math.min(end, runEnd)
    if (overlapStart >= overlapEnd) {
      appendRun(result, run.text, run.link)
    } else {
      appendRun(result, run.text.slice(0, overlapStart - runStart), run.link)
      appendRun(result, run.text.slice(overlapStart - runStart, overlapEnd - runStart), url)
      appendRun(result, run.text.slice(overlapEnd - runStart), run.link)
    }
    cursor = runEnd
  }
  return result.length ? result : [{ text: '' }]
}

function sameContent(left: InlineContent, right: InlineContent): boolean {
  return JSON.stringify(left) === JSON.stringify(right)
}

function contentIsVisuallyEmpty(content: InlineContent): boolean {
  return plainText(content).replace(/[\n\r\u200b]/g, '').length === 0
}

function safeUrl(value: string): string {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : ''
  } catch {
    return ''
  }
}
