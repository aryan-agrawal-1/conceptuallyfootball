const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID

const isAnalyticsEnabled = import.meta.env.PROD && Boolean(measurementId)

type DataLayerItem = IArguments | Record<string, unknown>

type Gtag = {
  (command: 'js', date: Date): void
  (command: 'config', targetId: string, config?: Record<string, unknown>): void
  (command: 'event', eventName: string, params?: Record<string, unknown>): void
}

declare global {
  interface Window {
    dataLayer?: DataLayerItem[]
    gtag?: Gtag
  }
}

let hasInitialized = false

export function initializeAnalytics() {
  if (!isAnalyticsEnabled || hasInitialized) {
    return
  }

  hasInitialized = true
  window.dataLayer = window.dataLayer ?? []
  window.gtag = function gtag() {
    window.dataLayer?.push(arguments)
  } as Gtag

  const script = document.createElement('script')
  script.async = true
  script.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`
  document.head.appendChild(script)

  window.gtag('js', new Date())
  window.gtag('config', measurementId, {
    send_page_view: false,
  })
}

export function trackPageView(path: string) {
  if (!isAnalyticsEnabled || !window.gtag) {
    return
  }

  window.gtag('event', 'page_view', {
    page_path: path,
    page_location: window.location.href,
    page_title: document.title,
  })
}
