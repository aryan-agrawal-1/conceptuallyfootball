const measurementId = import.meta.env.VITE_GA_MEASUREMENT_ID

const isAnalyticsEnabled = import.meta.env.PROD && Boolean(measurementId)

type GtagCommand =
  | ['js', Date]
  | ['config', string, Record<string, unknown>?]
  | ['event', string, Record<string, unknown>?]

declare global {
  interface Window {
    dataLayer?: GtagCommand[]
    gtag?: (...args: GtagCommand) => void
  }
}

let hasInitialized = false

export function initializeAnalytics() {
  if (!isAnalyticsEnabled || hasInitialized) {
    return
  }

  hasInitialized = true
  window.dataLayer = window.dataLayer ?? []
  window.gtag = (...args) => {
    window.dataLayer?.push(args)
  }

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
