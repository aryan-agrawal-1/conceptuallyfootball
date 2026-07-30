export const PNG_MIME_TYPE = 'image/png'
export const PNG_TARGET_BYTES = 1_000_000

export interface PngExportPolicy {
  name: string
  pixelRatios: readonly number[]
  minWidth: number
  minHeight: number
  minTextPixels: number
}

/**
 * Resolution floors are based on the logical export surfaces:
 * - square charts: 1200x1200, never below 900x900
 * - landscape charts: 1400x860, never below 1050x645
 * - A4 player cards: 1240x1754, never below 930x1315
 *
 * All three surfaces use 11px as their smallest intentional export text.
 * The 0.75 floor therefore preserves at least 8.25 output pixels and stays
 * above the documented 8px minimum typography constraint.
 *
 * Ratios are intentionally deterministic so an over-budget render follows the
 * same lossless retry path in every browser.
 */
export const PNG_EXPORT_POLICIES = {
  chartSquare: {
    name: 'square chart',
    pixelRatios: [1, 0.9, 0.8, 0.75],
    minWidth: 900,
    minHeight: 900,
    minTextPixels: 8,
  },
  chartLandscape: {
    name: 'landscape chart',
    pixelRatios: [1, 0.9, 0.8, 0.75],
    minWidth: 1050,
    minHeight: 645,
    minTextPixels: 8,
  },
  playerCard: {
    name: 'A4 player card',
    pixelRatios: [1, 0.9, 0.8, 0.75],
    minWidth: 930,
    minHeight: 1315,
    minTextPixels: 8,
  },
} as const satisfies Record<string, PngExportPolicy>

interface PngCaptureOptions {
  backgroundColor: string
  cacheBust: boolean
  fontEmbedCSS?: string
  pixelRatio: number
  type: typeof PNG_MIME_TYPE
}

type PngCapture = (
  node: HTMLElement,
  options: PngCaptureOptions,
) => Promise<Blob | null>

export interface PngExportReport {
  type: 'exceptional-size' | 'error'
  message: string
  policy: string
  fileName: string
  byteSize?: number
  targetBytes: number
  pixelRatio?: number
  width?: number
  height?: number
  minTextPixels?: number
  error?: unknown
}

export interface PngExportArtifact {
  blob: Blob
  fileName: string
  mimeType: typeof PNG_MIME_TYPE
  byteSize: number
  pixelRatio: number
  width: number
  height: number
  targetBytes: number
  overBudget: boolean
}

interface CreatePngExportOptions {
  resolveNode: () => HTMLElement | null
  fileName: string
  backgroundColor: string
  policy: PngExportPolicy
  targetBytes?: number
  capture?: PngCapture
  prepareSurface?: boolean
  report?: (report: PngExportReport) => void
}

interface PngDownloadRuntime {
  createObjectUrl: (blob: Blob) => string
  revokeObjectUrl: (url: string) => void
  clickDownload: (url: string, fileName: string) => void
}

interface PngShareRuntime {
  createFile: (blob: Blob, fileName: string, mimeType: typeof PNG_MIME_TYPE) => File
  canShare: (file: File) => boolean
  share: (data: ShareData) => Promise<void>
  download: (artifact: PngExportArtifact) => Promise<void>
}

export interface PngHandoffOptions {
  mode: 'download' | 'share'
  title: string
  text: string
}

function defaultReport(report: PngExportReport) {
  if (report.type === 'exceptional-size') {
    console.warn(report.message, report)
    return
  }
  console.error(report.message, report)
}

function nextPaint(): Promise<void> {
  if (typeof requestAnimationFrame !== 'function') return Promise.resolve()
  return new Promise(resolve => requestAnimationFrame(() => resolve()))
}

async function prepareExportSurface(resolveNode: () => HTMLElement | null): Promise<HTMLElement> {
  await nextPaint()
  await nextPaint()
  const node = resolveNode()
  if (!node) throw new Error('Export surface unavailable.')

  if (typeof document !== 'undefined' && document.fonts) {
    await document.fonts.ready
  }

  const images = Array.from(node.querySelectorAll('img'))
  await Promise.all(
    images.map(async image => {
      if (image.complete) return
      if (typeof image.decode === 'function') {
        await image.decode().catch(() => undefined)
        return
      }
      await new Promise<void>(resolve => {
        image.addEventListener('load', () => resolve(), { once: true })
        image.addEventListener('error', () => resolve(), { once: true })
      })
    }),
  )

  return node
}

function surfaceDimensions(node: HTMLElement): { width: number; height: number } {
  const rect = node.getBoundingClientRect()
  const width = Math.ceil(Math.max(node.clientWidth, node.scrollWidth, rect.width))
  const height = Math.ceil(Math.max(node.clientHeight, node.scrollHeight, rect.height))
  if (width <= 0 || height <= 0) {
    throw new Error('Export surface has no measurable dimensions.')
  }
  return { width, height }
}

function allowedPixelRatios(
  policy: PngExportPolicy,
  dimensions: { width: number; height: number },
): number[] {
  return policy.pixelRatios.filter(
    ratio =>
      Math.floor(dimensions.width * ratio) >= policy.minWidth &&
      Math.floor(dimensions.height * ratio) >= policy.minHeight,
  )
}

async function browserCapture(
  node: HTMLElement,
  options: PngCaptureOptions,
): Promise<Blob | null> {
  const { toBlob } = await import('html-to-image')
  return toBlob(node, options)
}

async function reusableFontCss(node: HTMLElement): Promise<string | undefined> {
  try {
    const { getFontEmbedCSS } = await import('html-to-image')
    return await getFontEmbedCSS(node)
  } catch {
    // html-to-image can still embed fonts during capture if precomputation is
    // unavailable (for example because a cross-origin stylesheet blocks it).
    return undefined
  }
}

export function pngFileName(...parts: string[]): string {
  const slug = parts
    .map(part => part.replace(/\.png$/i, ''))
    .join('-')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `${slug || 'export'}.png`
}

export async function createPngExport({
  resolveNode,
  fileName,
  backgroundColor,
  policy,
  targetBytes = PNG_TARGET_BYTES,
  capture = browserCapture,
  prepareSurface = true,
  report = defaultReport,
}: CreatePngExportOptions): Promise<PngExportArtifact> {
  try {
    const node = prepareSurface
      ? await prepareExportSurface(resolveNode)
      : resolveNode()
    if (!node) throw new Error('Export surface unavailable.')

    const dimensions = surfaceDimensions(node)
    const pixelRatios = allowedPixelRatios(policy, dimensions)
    if (pixelRatios.length === 0) {
      throw new Error(
        `${policy.name} surface is smaller than its ${policy.minWidth}x${policy.minHeight} minimum.`,
      )
    }

    const fontEmbedCSS = capture === browserCapture
      ? await reusableFontCss(node)
      : undefined
    let artifact: PngExportArtifact | null = null

    for (const pixelRatio of pixelRatios) {
      const blob = await capture(node, {
        backgroundColor,
        cacheBust: true,
        fontEmbedCSS,
        pixelRatio,
        type: PNG_MIME_TYPE,
      })
      if (!blob) throw new Error('Browser could not encode the PNG export.')
      if (blob.type !== PNG_MIME_TYPE) {
        throw new Error(`Expected a lossless PNG blob, received ${blob.type || 'an unknown MIME type'}.`)
      }

      artifact = {
        blob,
        fileName,
        mimeType: PNG_MIME_TYPE,
        byteSize: blob.size,
        pixelRatio,
        width: Math.floor(dimensions.width * pixelRatio),
        height: Math.floor(dimensions.height * pixelRatio),
        targetBytes,
        overBudget: blob.size > targetBytes,
      }
      if (!artifact.overBudget) return artifact
    }

    if (!artifact) throw new Error('PNG export did not produce an image.')
    report({
      type: 'exceptional-size',
      message: `${fileName} remains ${formatByteSize(artifact.byteSize)} at the minimum safe ${artifact.width}x${artifact.height} lossless resolution.`,
      policy: policy.name,
      fileName,
      byteSize: artifact.byteSize,
      targetBytes,
      pixelRatio: artifact.pixelRatio,
      width: artifact.width,
      height: artifact.height,
      minTextPixels: policy.minTextPixels,
    })
    return artifact
  } catch (error) {
    report({
      type: 'error',
      message: `Unable to create ${fileName}.`,
      policy: policy.name,
      fileName,
      targetBytes,
      error,
    })
    throw error
  }
}

function browserDownloadRuntime(): PngDownloadRuntime {
  return {
    createObjectUrl: blob => URL.createObjectURL(blob),
    revokeObjectUrl: url => URL.revokeObjectURL(url),
    clickDownload: (url, fileName) => {
      const link = document.createElement('a')
      link.href = url
      link.download = fileName
      document.body.appendChild(link)
      link.click()
      link.remove()
    },
  }
}

export async function downloadPngExport(
  artifact: PngExportArtifact,
  runtime = browserDownloadRuntime(),
): Promise<void> {
  const objectUrl = runtime.createObjectUrl(artifact.blob)
  try {
    runtime.clickDownload(objectUrl, artifact.fileName)
  } finally {
    runtime.revokeObjectUrl(objectUrl)
  }
}

function browserShareRuntime(): PngShareRuntime {
  return {
    createFile: (blob, fileName, mimeType) => new File([blob], fileName, { type: mimeType }),
    canShare: file =>
      typeof navigator !== 'undefined' &&
      typeof navigator.share === 'function' &&
      typeof navigator.canShare === 'function' &&
      navigator.canShare({ files: [file] }),
    share: data => navigator.share(data),
    download: artifact => downloadPngExport(artifact),
  }
}

export async function handoffPngExport(
  artifact: PngExportArtifact,
  options: PngHandoffOptions,
  runtime = browserShareRuntime(),
): Promise<'downloaded' | 'shared'> {
  if (options.mode === 'download') {
    await runtime.download(artifact)
    return 'downloaded'
  }

  const file = runtime.createFile(artifact.blob, artifact.fileName, artifact.mimeType)
  if (runtime.canShare(file)) {
    await runtime.share({
      title: options.title,
      text: options.text,
      files: [file],
    })
    return 'shared'
  }

  await runtime.download(artifact)
  return 'downloaded'
}

export function formatByteSize(bytes: number): string {
  if (bytes < 1_000) return `${bytes} B`
  if (bytes < 1_000_000) return `${(bytes / 1_000).toFixed(1)} KB`
  return `${(bytes / 1_000_000).toFixed(2)} MB`
}
