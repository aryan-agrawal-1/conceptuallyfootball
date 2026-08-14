import type { VisualArticleBlock } from './editorial'

const PRIVATE_BASE = '/api/v1/private/editorial'

export interface SubstackExportPayload {
  html: string
  text: string
  is_public: boolean
  canonical_url: string | null
  warnings: string[]
  visuals: { block_id: string; title: string; alt: string }[]
}

export function articleExportUrl(articleId: string, format: 'html' | 'markdown' | 'pdf'): string {
  return `${PRIVATE_BASE}/articles/${articleId}/exports/${format}`
}

async function substackPayload(articleId: string): Promise<SubstackExportPayload> {
  const response = await fetch(`${PRIVATE_BASE}/articles/${articleId}/exports/substack`, {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(body.detail ?? 'The Substack export could not be prepared.')
  return body as SubstackExportPayload
}

function visualElement(blockId: string): HTMLElement | null {
  return Array.from(document.querySelectorAll<HTMLElement>('[data-visual-block-id]'))
    .find(element => element.dataset.visualBlockId === blockId) ?? null
}

async function renderedVisualPng(blockId: string): Promise<string> {
  const element = visualElement(blockId)
  if (!element) throw new Error('Open the rendered article before exporting its visuals.')
  await document.fonts?.ready
  const { toPng } = await import('html-to-image')
  return toPng(element, {
    backgroundColor: '#070810',
    cacheBust: true,
    pixelRatio: 2,
  })
}

function richCopyFallback(html: string): boolean {
  const container = document.createElement('div')
  container.contentEditable = 'true'
  container.setAttribute('aria-hidden', 'true')
  container.style.position = 'fixed'
  container.style.left = '-20000px'
  container.innerHTML = html
  document.body.appendChild(container)
  const selection = window.getSelection()
  const range = document.createRange()
  range.selectNodeContents(container)
  selection?.removeAllRanges()
  selection?.addRange(range)
  const copied = document.execCommand('copy')
  selection?.removeAllRanges()
  container.remove()
  return copied
}

export async function copyArticleForSubstack(articleId: string): Promise<SubstackExportPayload> {
  const payload = await substackPayload(articleId)
  const parsed = new DOMParser().parseFromString(payload.html, 'text/html')
  const visualImages = await Promise.all(
    payload.visuals.map(async visual => ({
      ...visual,
      source: await renderedVisualPng(visual.block_id),
    })),
  )

  for (const visual of visualImages) {
    const placeholder = Array.from(parsed.querySelectorAll<HTMLElement>('[data-visual-block-id]'))
      .find(element => element.dataset.visualBlockId === visual.block_id)
    if (!placeholder) continue
    const image = parsed.createElement('img')
    image.src = visual.source
    image.alt = visual.alt
    image.setAttribute('data-visual-block-id', visual.block_id)
    image.setAttribute('style', 'display:block;max-width:100%;height:auto;margin:1.5em auto')
    placeholder.replaceWith(image)
  }

  const html = parsed.body.innerHTML
  if (typeof ClipboardItem !== 'undefined' && navigator.clipboard?.write) {
    await navigator.clipboard.write([
      new ClipboardItem({
        'text/html': new Blob([html], { type: 'text/html' }),
        'text/plain': new Blob([payload.text], { type: 'text/plain' }),
      }),
    ])
  } else if (!richCopyFallback(html)) {
    throw new Error('This browser does not support rich clipboard copy. Download the HTML bundle instead.')
  }
  return payload
}

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function visualFileName(block: VisualArticleBlock, extension: 'png' | 'svg', index: number): string {
  const value = block.title || block.caption || block.visual_type
  const slug = value.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '')
  return `conceptually-football-${String(index + 1).padStart(2, '0')}-${slug || 'visual'}.${extension}`
}

export async function downloadVisual(block: VisualArticleBlock, format: 'png' | 'svg', index: number): Promise<void> {
  const element = visualElement(block.id)
  if (!element) throw new Error('Open the rendered article before exporting this visual.')
  await document.fonts?.ready
  const { toBlob, toSvg } = await import('html-to-image')
  if (format === 'png') {
    const blob = await toBlob(element, { backgroundColor: '#070810', cacheBust: true, pixelRatio: 2 })
    if (!blob) throw new Error('The browser could not encode this visual as PNG.')
    downloadBlob(blob, visualFileName(block, 'png', index))
    return
  }
  const dataUrl = await toSvg(element, { backgroundColor: '#070810', cacheBust: true })
  const response = await fetch(dataUrl)
  downloadBlob(await response.blob(), visualFileName(block, 'svg', index))
}
