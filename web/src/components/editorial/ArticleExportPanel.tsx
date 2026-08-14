import { useState, type ReactNode } from 'react'
import { Check, ClipboardCopy, Download, FileCode2, FileText, ImageDown, Loader2, TriangleAlert } from 'lucide-react'
import type { ArticleDocument, VisualArticleBlock } from '../../lib/editorial'
import { articleExportUrl, copyArticleForSubstack, downloadVisual } from '../../lib/editorialExports'

type BusyExport = 'substack' | 'html' | 'markdown' | 'pdf' | string | null

export function ArticleExportPanel({ articleId, document }: { articleId: string; document: ArticleDocument }) {
  const [busy, setBusy] = useState<BusyExport>(null)
  const [message, setMessage] = useState('')
  const [warnings, setWarnings] = useState<string[]>([])
  const visuals = document.blocks.filter((block): block is VisualArticleBlock => block.type === 'visual')

  async function copySubstack() {
    setBusy('substack')
    setMessage('')
    setWarnings([])
    try {
      const payload = await copyArticleForSubstack(articleId)
      setWarnings(payload.warnings)
      setMessage('Copied with Substack-ready formatting. Paste it into a new article draft and review before publishing.')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The Substack copy failed.')
    } finally {
      setBusy(null)
    }
  }

  function downloadArticle(format: 'html' | 'markdown' | 'pdf') {
    setBusy(format)
    setMessage('')
    const link = window.document.createElement('a')
    link.href = articleExportUrl(articleId, format)
    window.document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => setBusy(null), 500)
  }

  async function exportVisual(block: VisualArticleBlock, format: 'png' | 'svg', index: number) {
    const key = `${block.id}-${format}`
    setBusy(key)
    setMessage('')
    try {
      await downloadVisual(block, format, index)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'The visual export failed.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs leading-5 text-ink-dim">Copy the rendered article into Substack, including static chart images, captions, sources and accessible descriptions.</p>
        <button type="button" onClick={() => void copySubstack()} disabled={busy !== null} className="mt-3 flex h-10 w-full items-center justify-center gap-2 bg-electric text-[8px] font-black uppercase tracking-[0.15em] text-mat disabled:opacity-45">
          {busy === 'substack' ? <Loader2 className="size-3.5 animate-spin" /> : message.startsWith('Copied') ? <Check className="size-3.5" /> : <ClipboardCopy className="size-3.5" />}
          {busy === 'substack' ? 'Preparing copy…' : 'Copy for Substack'}
        </button>
      </div>

      <div className="grid grid-cols-3 gap-1.5">
        <ExportButton label="PDF" icon={<FileText />} busy={busy === 'pdf'} onClick={() => downloadArticle('pdf')} />
        <ExportButton label="HTML" icon={<FileCode2 />} busy={busy === 'html'} onClick={() => downloadArticle('html')} />
        <ExportButton label="Markdown" icon={<Download />} busy={busy === 'markdown'} onClick={() => downloadArticle('markdown')} />
      </div>

      {visuals.length ? (
        <div className="border-t border-line pt-4">
          <p className="font-mono text-[7px] uppercase tracking-[0.15em] text-ink-muted">Individual visuals</p>
          <div className="mt-2 space-y-2">
            {visuals.map((visual, index) => (
              <div key={visual.id} className="border border-line bg-mat/45 p-2.5">
                <p className="truncate text-[10px] font-semibold text-ink">{String(index + 1).padStart(2, '0')} · {visual.title || visual.caption || `Visual ${index + 1}`}</p>
                <div className="mt-2 grid grid-cols-2 gap-1.5">
                  {(['png', 'svg'] as const).map(format => {
                    const key = `${visual.id}-${format}`
                    return <button key={format} type="button" onClick={() => void exportVisual(visual, format, index)} disabled={busy !== null} className="flex h-8 items-center justify-center gap-1.5 border border-line text-[7px] font-bold uppercase tracking-[0.12em] text-ink-muted hover:border-electric hover:text-electric disabled:opacity-40">{busy === key ? <Loader2 className="size-3 animate-spin" /> : <ImageDown className="size-3" />} {format}</button>
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {message ? <p className={`text-[9px] leading-4 ${message.startsWith('Copied') ? 'text-mint' : 'text-gold'}`}>{message}</p> : null}
      {message.startsWith('Copied') && visuals.length ? <p className="text-[9px] leading-4 text-ink-dim">If Substack replaces a chart with its alt text, add the matching numbered PNG below at that position.</p> : null}
      {warnings.map(warning => <p key={warning} className="flex gap-2 text-[9px] leading-4 text-gold"><TriangleAlert className="mt-0.5 size-3 shrink-0" />{warning}</p>)}
      <p className="font-mono text-[7px] leading-4 uppercase tracking-[0.1em] text-ink-muted">Draft exports stay private. Substack audience, paywall, email and scheduling remain under your control.</p>
    </div>
  )
}

function ExportButton({ label, icon, busy, onClick }: { label: string; icon: ReactNode; busy: boolean; onClick: () => void }) {
  return <button type="button" onClick={onClick} disabled={busy} className="flex min-h-12 flex-col items-center justify-center gap-1 border border-line text-[7px] font-bold uppercase tracking-[0.1em] text-ink-muted hover:border-electric hover:text-electric disabled:opacity-40">{busy ? <Loader2 className="size-3.5 animate-spin" /> : <span className="[&>svg]:size-3.5">{icon}</span>}{label}</button>
}
