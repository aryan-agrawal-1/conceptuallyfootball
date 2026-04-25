import { lazy, Suspense } from 'react'
import { Routes, Route } from 'react-router-dom'
import { Layout } from './components/layout/Layout'

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

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<StatMatrix />} />
          <Route path="/player/:id" element={<PlayerProfile />} />
          <Route path="/team/:id" element={<TeamProfile />} />
          <Route path="/galaxy" element={<Galaxy />} />
          <Route path="/comparisons" element={<Comparisons />} />
          <Route path="/regression-lab" element={<RegressionLab />} />
          <Route path="/data-visualiser" element={<DataVisualiser />} />
        </Routes>
      </Suspense>
    </Layout>
  )
}
