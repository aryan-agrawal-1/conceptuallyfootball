import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { useStaffAuth } from '../../context/StaffAuthContext'

export function StaffRoute({
  children,
  allowPasswordChange = false,
}: {
  children: ReactNode
  allowPasswordChange?: boolean
}) {
  const { user, isLoading } = useStaffAuth()
  const location = useLocation()

  if (isLoading) {
    return (
      <main className="grid min-h-svh place-items-center bg-mat" aria-busy="true">
        <div className="flex items-center gap-3 text-xs font-semibold uppercase tracking-[0.22em] text-ink-dim">
          <span className="size-2 animate-pulse rounded-full bg-electric" />
          Verifying access
        </div>
      </main>
    )
  }
  if (!user) {
    return <Navigate to="/staff/login" replace state={{ from: location.pathname }} />
  }
  if (user.must_change_password && !allowPasswordChange) {
    return <Navigate to="/staff/change-password" replace />
  }
  return children
}
