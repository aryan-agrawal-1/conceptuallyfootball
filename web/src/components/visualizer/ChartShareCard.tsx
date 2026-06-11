import { useRef, useState, type ReactNode } from 'react'
import { BRAND_DOMAIN, BRAND_LOGO_URL, BRAND_NAME_UPPER, BRAND_SLUG } from '../../lib/brand'
import { ShareActions, type ShareActionBusy } from '../share/ShareActions'

type ExportAspect = 'square' | 'landscape'

interface ChartShareCardProps {
  title: string
  subtitle: string
  contextLabel: string
  fileName: string
  aspect?: ExportAspect
  copyUrl?: string
  compact?: boolean
  renderContent: (opts: { exportMode: boolean }) => ReactNode
  renderExportLegend?: () => ReactNode
}

function aspectClass(aspect: ExportAspect): string {
  return aspect === 'landscape' ? 'w-[1400px] min-h-[860px]' : 'w-[1200px] min-h-[1200px]'
}

async function dataUrlToFile(dataUrl: string, fileName: string): Promise<File> {
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  return new File([blob], fileName, { type: blob.type || 'image/png' })
}

export function ChartShareCard({
  title,
  subtitle,
  contextLabel,
  fileName,
  aspect = 'landscape',
  copyUrl,
  compact = true,
  renderContent,
  renderExportLegend,
}: ChartShareCardProps) {
  const exportRef = useRef<HTMLDivElement>(null)
  const [busy, setBusy] = useState<ShareActionBusy>(null)
  const safeFileName = `${BRAND_SLUG}-${fileName.replace(/[^a-z0-9-_]+/gi, '-').toLowerCase()}.png`

  async function waitForExportSurface() {
    await new Promise<void>(resolve => requestAnimationFrame(() => resolve()))
  }

  async function buildImage(): Promise<string> {
    const node = exportRef.current
    if (!node) throw new Error('Export surface unavailable.')
    const { toPng } = await import('html-to-image')
    return toPng(node, {
      cacheBust: true,
      pixelRatio: 2.5,
      backgroundColor: '#070810',
    })
  }

  async function handleDownload() {
    try {
      setBusy('download')
      await waitForExportSurface()
      const dataUrl = await buildImage()
      const link = document.createElement('a')
      link.href = dataUrl
      link.download = safeFileName
      link.click()
    } finally {
      setBusy(null)
    }
  }

  async function handleShare() {
    try {
      setBusy('share')
      await waitForExportSurface()
      const dataUrl = await buildImage()
      const file = await dataUrlToFile(dataUrl, safeFileName)
      if (
        typeof navigator !== 'undefined' &&
        'share' in navigator &&
        'canShare' in navigator &&
        navigator.canShare?.({ files: [file] })
      ) {
        await navigator.share({
          title,
          text: subtitle,
          files: [file],
        })
        return
      }
      const link = document.createElement('a')
      link.href = dataUrl
      link.download = safeFileName
      link.click()
    } finally {
      setBusy(null)
    }
  }

  async function handleCopyLink() {
    if (!copyUrl) return
    try {
      setBusy('copy')
      let copied = false
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        try {
          await navigator.clipboard.writeText(copyUrl)
          copied = true
        } catch {
          copied = false
        }
      }
      if (!copied) {
        const input = document.createElement('textarea')
        input.value = copyUrl
        input.setAttribute('readonly', '')
        input.style.position = 'fixed'
        input.style.left = '-9999px'
        document.body.appendChild(input)
        input.select()
        document.execCommand('copy')
        document.body.removeChild(input)
      }
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <ShareActions
        busy={busy}
        onShare={handleShare}
        onDownload={handleDownload}
        onCopyLink={copyUrl ? handleCopyLink : undefined}
        compact={compact}
      />

      {(busy === 'share' || busy === 'download') && <div className="fixed left-[-20000px] top-0 pointer-events-none opacity-0" aria-hidden="true">
        <div
          ref={exportRef}
          className={`relative overflow-hidden border border-electric/30 bg-[#070810] text-ink shadow-[0_0_80px_-12px_rgba(74,158,245,0.3)] ${aspectClass(aspect)}`}
        >
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(74,158,245,0.16),transparent_40%),linear-gradient(180deg,rgba(74,158,245,0.08),transparent_30%),linear-gradient(135deg,rgba(255,255,255,0.03),transparent_55%)]" />
          <div className="absolute inset-x-0 top-0 h-px bg-electric/25" />
          <div className="absolute inset-y-0 left-0 w-px bg-electric/18" />
          <div className="absolute inset-y-0 right-0 w-px bg-electric/18" />
          <div className="absolute inset-x-0 bottom-0 h-px bg-electric/18" />

          <div className="relative flex min-h-full flex-col gap-6 p-8">
            <div className="flex items-start justify-between gap-6">
              <div className="min-w-0">
                <p className="mb-3 text-[12px] uppercase tracking-[0.32em] text-electric/85">
                  {contextLabel}
                </p>
                <h2 className="max-w-[80%] text-[40px] font-black leading-none tracking-tight text-ink">
                  {title}
                </h2>
                <p className="mt-3 max-w-[78ch] text-[16px] text-ink-dim">{subtitle}</p>
              </div>
              <div className="flex shrink-0 items-center justify-end gap-3 text-right">
                <img src={BRAND_LOGO_URL} alt="" className="size-12 object-contain" />
                <div className="max-w-[220px] text-[13px] font-black uppercase leading-tight tracking-[0.12em] text-electric">
                  {BRAND_NAME_UPPER}
                </div>
              </div>
            </div>

            <div className="relative flex-1 overflow-hidden border border-electric/20 bg-panel/70 px-4 py-4 shadow-[inset_0_0_0_1px_rgba(74,158,245,0.06)]">
              <div className="absolute left-2 top-2 size-3 border-l border-t border-electric/60" />
              <div className="absolute right-2 top-2 size-3 border-r border-t border-electric/60" />
              <div className="absolute bottom-2 left-2 size-3 border-b border-l border-electric/60" />
              <div className="absolute bottom-2 right-2 size-3 border-b border-r border-electric/60" />
              <div className="relative z-10 flex h-full min-h-[660px] w-full flex-col items-center justify-center gap-6">
                <div className="flex w-full flex-1 items-center justify-center">
                  {renderContent({ exportMode: true })}
                </div>
                {renderExportLegend && <div className="w-full">{renderExportLegend()}</div>}
              </div>
            </div>

            <div className="flex items-center justify-between gap-4 text-[11px] uppercase tracking-[0.22em] text-electric/70">
              <span>{BRAND_DOMAIN}</span>
              <span>{contextLabel}</span>
            </div>
          </div>
        </div>
      </div>}
    </>
  )
}
