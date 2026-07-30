import assert from 'node:assert/strict'
import { it } from 'vitest'
import {
  createPngExport,
  downloadPngExport,
  handoffPngExport,
  PNG_MIME_TYPE,
  type PngExportArtifact,
  type PngExportPolicy,
  type PngExportReport,
} from '../src/components/share/pngExport.ts'

const TEST_POLICY: PngExportPolicy = {
  name: 'test export',
  pixelRatios: [1, 0.8, 0.6],
  minWidth: 600,
  minHeight: 480,
  minTextPixels: 8,
}

function pngBlob(size: number, type = PNG_MIME_TYPE): Blob {
  return new Blob([new Uint8Array(size)], { type })
}

function surface(width = 1000, height = 800): HTMLElement {
  return {
    clientWidth: width,
    clientHeight: height,
    scrollWidth: width,
    scrollHeight: height,
    getBoundingClientRect: () => ({ width, height }),
  } as unknown as HTMLElement
}

it('returns an under-budget lossless PNG on the first pass', async () => {
  const attempts: number[] = []
  const artifact = await createPngExport({
    resolveNode: () => surface(),
    fileName: 'chart.png',
    backgroundColor: '#000',
    policy: TEST_POLICY,
    prepareSurface: false,
    capture: async (_node, options) => {
      attempts.push(options.pixelRatio)
      return pngBlob(900_000)
    },
  })

  assert.deepEqual(attempts, [1])
  assert.equal(artifact.mimeType, PNG_MIME_TYPE)
  assert.equal(artifact.blob.type, PNG_MIME_TYPE)
  assert.equal(artifact.byteSize, 900_000)
  assert.equal(artifact.overBudget, false)
  assert.deepEqual([artifact.width, artifact.height], [1000, 800])
})

it('retries deterministic lower ratios until the blob meets the target', async () => {
  const attempts: number[] = []
  const sizes = [1_300_000, 1_100_000, 800_000]
  const artifact = await createPngExport({
    resolveNode: () => surface(),
    fileName: 'chart.png',
    backgroundColor: '#000',
    policy: TEST_POLICY,
    prepareSurface: false,
    capture: async (_node, options) => {
      attempts.push(options.pixelRatio)
      return pngBlob(sizes[attempts.length - 1])
    },
  })

  assert.deepEqual(attempts, [1, 0.8, 0.6])
  assert.equal(artifact.pixelRatio, 0.6)
  assert.deepEqual([artifact.width, artifact.height], [600, 480])
  assert.equal(artifact.overBudget, false)
})

it('stops at the minimum readable resolution and reports an exceptional size', async () => {
  const attempts: number[] = []
  const reports: PngExportReport[] = []
  const artifact = await createPngExport({
    resolveNode: () => surface(),
    fileName: 'complex-chart.png',
    backgroundColor: '#000',
    policy: TEST_POLICY,
    prepareSurface: false,
    capture: async (_node, options) => {
      attempts.push(options.pixelRatio)
      return pngBlob(1_100_000)
    },
    report: report => reports.push(report),
  })

  assert.deepEqual(attempts, [1, 0.8, 0.6])
  assert.deepEqual([artifact.width, artifact.height], [600, 480])
  assert.equal(artifact.overBudget, true)
  assert.equal(reports.length, 1)
  assert.equal(reports[0].type, 'exceptional-size')
  assert.equal(reports[0].byteSize, 1_100_000)
})

it('rejects a capture that is not encoded as PNG', async () => {
  const reports: PngExportReport[] = []
  await assert.rejects(
    createPngExport({
      resolveNode: () => surface(),
      fileName: 'chart.png',
      backgroundColor: '#000',
      policy: TEST_POLICY,
      prepareSurface: false,
      capture: async () => pngBlob(100, 'image/jpeg'),
      report: report => reports.push(report),
    }),
    /Expected a lossless PNG blob/,
  )
  assert.equal(reports.at(-1)?.type, 'error')
})

it('download uses the artifact blob and always revokes its object URL', async () => {
  const artifact = testArtifact()
  let receivedBlob: Blob | null = null
  let clicked: [string, string] | null = null
  const revoked: string[] = []

  await downloadPngExport(artifact, {
    createObjectUrl: blob => {
      receivedBlob = blob
      return 'blob:test-url'
    },
    clickDownload: (url, fileName) => {
      clicked = [url, fileName]
    },
    revokeObjectUrl: url => revoked.push(url),
  })

  assert.equal(receivedBlob, artifact.blob)
  assert.deepEqual(clicked, ['blob:test-url', artifact.fileName])
  assert.deepEqual(revoked, ['blob:test-url'])
})

it('download and native share handoffs reuse the same generated blob', async () => {
  const artifact = testArtifact()
  const downloaded: PngExportArtifact[] = []
  const file = { name: artifact.fileName, type: PNG_MIME_TYPE } as File
  let fileSource: Blob | null = null
  const sharedPayloads: ShareData[] = []
  const runtime = {
    createFile: (blob: Blob) => {
      fileSource = blob
      return file
    },
    canShare: (candidate: File) => candidate === file,
    share: async (data: ShareData) => {
      sharedPayloads.push(data)
    },
    download: async (candidate: PngExportArtifact) => {
      downloaded.push(candidate)
    },
  }

  await handoffPngExport(artifact, { mode: 'download', title: 'Chart', text: 'Context' }, runtime)
  await handoffPngExport(artifact, { mode: 'share', title: 'Chart', text: 'Context' }, runtime)

  assert.equal(downloaded[0], artifact)
  assert.equal(fileSource, artifact.blob)
  assert.equal(sharedPayloads[0]?.files?.[0], file)
})

function testArtifact(): PngExportArtifact {
  const blob = pngBlob(1234)
  return {
    blob,
    fileName: 'chart.png',
    mimeType: PNG_MIME_TYPE,
    byteSize: blob.size,
    pixelRatio: 1,
    width: 1000,
    height: 800,
    targetBytes: 1_000_000,
    overBudget: false,
  }
}
