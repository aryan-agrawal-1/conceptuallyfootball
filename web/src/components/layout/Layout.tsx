import type { ReactNode } from 'react'
import { NavBar } from './NavBar'

interface LayoutProps {
  children: ReactNode
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="flex flex-col min-h-svh bg-mat">
      <NavBar />
      <main className="flex-1 mt-[64px] pb-[68px] lg:mt-[52px] lg:pb-0">
        {children}
      </main>
    </div>
  )
}
