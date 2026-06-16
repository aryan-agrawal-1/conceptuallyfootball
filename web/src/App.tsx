import { lazy, Suspense, useEffect } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import { Layout } from './components/layout/Layout'
import { initializeAnalytics, trackPageView } from './lib/analytics'
import { CREATE_CHARTS_PATH, LEGACY_DATA_VISUALISER_PATH } from './lib/createChartsUrl'
import { useSeoMeta, type SeoMeta } from './lib/seo'

const StatMatrix = lazy(() =>
  import('./pages/StatMatrix').then(m => ({ default: m.StatMatrix })),
)
const PlayerProfile = lazy(() =>
  import('./pages/PlayerProfile').then(m => ({ default: m.PlayerProfile })),
)
const TeamProfile = lazy(() =>
  import('./pages/TeamProfile').then(m => ({ default: m.TeamProfile })),
)
const Galaxy = lazy(() =>
  import('./pages/Galaxy').then(m => ({ default: m.Galaxy })),
)
const Comparisons = lazy(() =>
  import('./pages/Comparisons').then(m => ({ default: m.Comparisons })),
)
const RegressionLab = lazy(() =>
  import('./pages/RegressionLab').then(m => ({ default: m.RegressionLab })),
)
const DataVisualiser = lazy(() =>
  import('./pages/DataVisualiser').then(m => ({ default: m.DataVisualiser })),
)

function RouteFallback() {
  return (
    <div className="flex items-center justify-center min-h-[50vh]">
      <div
        className="size-7 rounded-full border-2 border-line border-t-electric animate-spin"
        role="status"
        aria-label="Loading page"
      />
    </div>
  )
}

function AnalyticsPageViews() {
  const location = useLocation()

  useEffect(() => {
    initializeAnalytics()
  }, [])

  useEffect(() => {
    trackPageView(`${location.pathname}${location.search}`)
  }, [location.pathname, location.search])

  return null
}

const ROUTE_SEO: Record<string, SeoMeta> = {
  '/': {
    title: 'Football Data Matrix | Conceptually Football',
    description:
      'Explore football player stats with per 90 metrics, percentiles, heatmaps, team filters, position groups and season-level football data.',
    canonicalPath: '/',
  },
  '/galaxy': {
    title: 'Football Player Similarity Galaxy | Conceptually Football',
    description:
      'Map football players by statistical similarity, compare profiles and discover similar players across leagues, seasons and positions.',
    canonicalPath: '/galaxy',
  },
  '/comparisons': {
    title: 'Football Player Comparison Tool | Conceptually Football',
    description:
      'Compare football players with radar charts, percentiles and selected stats across positions, teams, leagues and seasons.',
    canonicalPath: '/comparisons',
  },
  '/regression-lab': {
    title: 'Football Regression Analysis Lab | Conceptually Football',
    description:
      'Build football analysis models with regression tools for player metrics, predictors, target stats and scouting workflows.',
    canonicalPath: '/regression-lab',
  },
  [CREATE_CHARTS_PATH]: {
    title: 'Football Data Visualisation Tool | Conceptually Football',
    description:
      'Create football data visualisations with scatter plots, bar charts and radar charts for players, teams and statistical comparisons.',
    canonicalPath: CREATE_CHARTS_PATH,
  },
  [LEGACY_DATA_VISUALISER_PATH]: {
    title: 'Football Data Visualisation Tool | Conceptually Football',
    description:
      'Create football data visualisations with scatter plots, bar charts and radar charts for players, teams and statistical comparisons.',
    canonicalPath: CREATE_CHARTS_PATH,
  },
}

function RouteSeo() {
  const location = useLocation()
  const pathname = location.pathname

  const meta =
    pathname.startsWith('/player/')
      ? {
          title: 'Football Player Stats | Conceptually Football',
          description:
            'View football player stats, per 90 data, percentile rankings, similar players and comparison tools.',
          canonicalPath: pathname,
        }
      : pathname.startsWith('/team/')
        ? {
            title: 'Football Team Stats | Conceptually Football',
            description:
              'View football team stats, squad data, xG, xA, per-match metrics and team analysis tools.',
            canonicalPath: pathname,
          }
        : ROUTE_SEO[pathname] ?? ROUTE_SEO['/']

  useSeoMeta(meta)
  return null
}

export default function App() {
  return (
    <Layout>
      <RouteSeo />
      <AnalyticsPageViews />
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<StatMatrix />} />
          <Route path="/player/:id" element={<PlayerProfile />} />
          <Route path="/team/:id" element={<TeamProfile />} />
          <Route path="/galaxy" element={<Galaxy />} />
          <Route path="/comparisons" element={<Comparisons />} />
          <Route path="/regression-lab" element={<RegressionLab />} />
          <Route path={CREATE_CHARTS_PATH} element={<DataVisualiser />} />
          <Route path={LEGACY_DATA_VISUALISER_PATH} element={<DataVisualiser />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}
