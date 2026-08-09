import { FilePlus2, LogOut, PenLine, ShieldCheck } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { StaffFrame } from '../components/staff/StaffFrame'
import { StaffRoute } from '../components/staff/StaffRoute'
import { useStaffAuth } from '../context/StaffAuthContext'

export function EditorialWorkspace() {
  return (
    <StaffRoute>
      <WorkspaceHome />
    </StaffRoute>
  )
}

function WorkspaceHome() {
  const { user, logout } = useStaffAuth()
  const navigate = useNavigate()

  if (!user) return null
  if (!user.can_access_editorial) {
    return (
      <StaffFrame eyebrow="Editorial workspace">
        <div className="grid flex-1 place-items-center text-center">
          <div>
            <ShieldCheck className="mx-auto size-8 text-ember" />
            <h1 className="mt-5 text-2xl font-bold text-ink">Editorial access is not assigned.</h1>
            <p className="mt-2 text-sm text-ink-dim">Ask a superuser to review your account role.</p>
          </div>
        </div>
      </StaffFrame>
    )
  }

  async function handleLogout() {
    await logout()
    navigate('/staff/login', { replace: true })
  }

  return (
    <StaffFrame eyebrow="Editorial workspace">
      <div className="flex flex-1 flex-col py-10 sm:py-14">
        <div className="flex flex-col gap-6 border-b border-line pb-10 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-electric">
              Access confirmed · {user.role?.replace('_', ' ')}
            </p>
            <h1 className="mt-4 text-4xl font-black tracking-[-0.045em] text-ink sm:text-5xl">
              Welcome to the desk, {user.display_name.split(' ')[0]}.
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-6 text-ink-dim">
              The secure editorial foundation is ready. Draft creation and the rendered block editor arrive in the next stage.
            </p>
          </div>
          <button type="button" onClick={handleLogout} className="flex h-10 items-center gap-2 self-start border border-line-bright px-4 text-[10px] font-bold uppercase tracking-[0.15em] text-ink-dim hover:border-electric hover:text-ink">
            <LogOut className="size-4" /> Sign out
          </button>
        </div>

        <div className="grid flex-1 gap-4 py-8 md:grid-cols-3">
          <WorkspaceCard icon={PenLine} label="Workspace status" title="Your writing desk is secured" copy="Your account and editorial role are verified on the server for every private request." accent />
          <WorkspaceCard icon={FilePlus2} label="Coming in #77" title="Rendered article editor" copy="Compose headings, media, captions and analysis blocks exactly as readers will see them." />
          <WorkspaceCard icon={ShieldCheck} label="Access model" title={user.can_approve_editorial ? 'Writer and approver' : 'Editorial writer'} copy={user.can_approve_editorial ? 'You can write and will be eligible for review permissions as publishing tools arrive.' : 'Operational ingestion controls remain isolated from your editorial access.'} />
        </div>
      </div>
    </StaffFrame>
  )
}

function WorkspaceCard({ icon: Icon, label, title, copy, accent = false }: { icon: typeof PenLine; label: string; title: string; copy: string; accent?: boolean }) {
  return (
    <article className={`relative min-h-56 border p-6 ${accent ? 'border-electric/50 bg-electric-dim/45' : 'border-line bg-panel/70'}`}>
      <Icon className={`size-5 ${accent ? 'text-electric' : 'text-ink-muted'}`} />
      <p className="mt-10 font-mono text-[8px] uppercase tracking-[0.22em] text-ink-muted">{label}</p>
      <h2 className="mt-3 text-lg font-bold tracking-[-0.02em] text-ink">{title}</h2>
      <p className="mt-3 text-xs leading-5 text-ink-dim">{copy}</p>
    </article>
  )
}
