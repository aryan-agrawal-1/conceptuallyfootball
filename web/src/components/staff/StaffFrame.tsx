import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { BRAND_LOGO_URL, BRAND_NAME } from '../../lib/brand'

export function StaffFrame({ children, eyebrow }: { children: ReactNode; eyebrow: string }) {
  return (
    <main className="relative min-h-svh overflow-hidden bg-mat px-5 py-6 sm:px-8 sm:py-8">
      <div className="pointer-events-none absolute inset-0 opacity-60 [background-image:linear-gradient(rgba(74,158,245,.055)_1px,transparent_1px),linear-gradient(90deg,rgba(74,158,245,.055)_1px,transparent_1px)] [background-size:48px_48px]" />
      <div className="pointer-events-none absolute left-[-12rem] top-[-14rem] size-[34rem] rounded-full bg-electric/10 blur-[120px]" />
      <div className="relative mx-auto flex min-h-[calc(100svh-3rem)] w-full max-w-6xl flex-col">
        <header className="flex items-center justify-between border-b border-line pb-5">
          <Link to="/" className="flex items-center gap-3">
            <img src={BRAND_LOGO_URL} alt="" className="size-8 object-contain" />
            <span className="text-[11px] font-black uppercase tracking-[0.16em] text-ink sm:text-xs">
              {BRAND_NAME}
            </span>
          </Link>
          <span className="font-mono text-[9px] uppercase tracking-[0.24em] text-electric sm:text-[10px]">
            {eyebrow}
          </span>
        </header>
        {children}
      </div>
    </main>
  )
}
