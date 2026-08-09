import { useState, type FormEvent } from 'react'
import { ArrowRight, KeyRound } from 'lucide-react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import { StaffFrame } from '../components/staff/StaffFrame'
import { useStaffAuth } from '../context/StaffAuthContext'
import { StaffAuthError } from '../lib/staffAuth'

export function StaffLogin() {
  const { user, isLoading, login } = useStaffAuth()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()
  const location = useLocation()

  if (!isLoading && user) {
    return <Navigate to={user.must_change_password ? '/staff/change-password' : '/analysis'} replace />
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const signedInUser = await login(email.trim().toLowerCase(), password)
      const requestedPath = (location.state as { from?: string } | null)?.from
      navigate(
        signedInUser.must_change_password ? '/staff/change-password' : requestedPath ?? '/analysis',
        { replace: true },
      )
    } catch (caughtError) {
      setError(
        caughtError instanceof StaffAuthError
          ? caughtError.message
          : 'Sign-in is temporarily unavailable. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <StaffFrame eyebrow="Private editorial access">
      <div className="grid flex-1 items-center gap-12 py-14 lg:grid-cols-[1.1fr_.9fr] lg:py-20">
        <section className="max-w-xl">
          <div className="mb-7 flex items-center gap-3 font-mono text-[10px] uppercase tracking-[0.22em] text-ink-dim">
            <span className="h-px w-10 bg-electric" />
            Writers' entrance
          </div>
          <h1 className="text-balance text-4xl font-black leading-[.96] tracking-[-0.045em] text-ink sm:text-6xl">
            The analysis starts behind the touchline.
          </h1>
          <p className="mt-6 max-w-lg text-sm leading-7 text-ink-dim sm:text-base">
            A private workspace for invited writers to shape football ideas into clear,
            evidence-led stories.
          </p>
          <div className="mt-10 hidden grid-cols-3 gap-px overflow-hidden border border-line bg-line sm:grid">
            {['Draft deliberately', 'Build with data', 'Publish with care'].map((label, index) => (
              <div key={label} className="bg-panel px-4 py-5">
                <span className="font-mono text-[9px] text-electric">0{index + 1}</span>
                <p className="mt-3 text-[10px] font-semibold uppercase tracking-[0.13em] text-ink-dim">
                  {label}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="relative border border-line-bright bg-panel/95 p-6 shadow-[18px_18px_0_rgba(13,34,72,.45)] sm:p-9">
          <span className="absolute -right-px -top-px h-8 w-8 border-r border-t border-electric" />
          <KeyRound className="size-5 text-electric" aria-hidden="true" />
          <h2 className="mt-7 text-xl font-bold tracking-[-0.02em] text-ink">Sign in to the desk</h2>
          <p className="mt-2 text-xs leading-5 text-ink-dim">
            Use the email and temporary password supplied with your invitation.
          </p>
          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            <StaffField
              id="staff-email"
              label="Email address"
              type="email"
              value={email}
              onChange={setEmail}
              autoComplete="username"
            />
            <StaffField
              id="staff-password"
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              autoComplete="current-password"
            />
            {error ? (
              <p role="alert" className="border-l-2 border-ember bg-ember/5 px-3 py-2 text-xs text-red-300">
                {error}
              </p>
            ) : null}
            <button
              type="submit"
              disabled={submitting || !email || !password}
              className="group flex h-12 w-full items-center justify-between bg-electric px-4 text-[11px] font-black uppercase tracking-[0.16em] text-mat transition-colors hover:bg-blue-300 disabled:bg-line-bright disabled:text-ink-muted"
            >
              {submitting ? 'Checking access…' : 'Enter workspace'}
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />
            </button>
          </form>
          <p className="mt-6 text-[10px] leading-5 text-ink-muted">
            Access is invitation-only. If you have lost your password, ask an administrator
            for a new temporary one.
          </p>
        </section>
      </div>
    </StaffFrame>
  )
}

function StaffField({
  id,
  label,
  type,
  value,
  onChange,
  autoComplete,
}: {
  id: string
  label: string
  type: string
  value: string
  onChange: (value: string) => void
  autoComplete: string
}) {
  return (
    <label htmlFor={id} className="block">
      <span className="mb-2 block font-mono text-[9px] uppercase tracking-[0.2em] text-ink-dim">
        {label}
      </span>
      <input
        id={id}
        type={type}
        value={value}
        onChange={event => onChange(event.target.value)}
        autoComplete={autoComplete}
        required
        className="h-12 w-full border border-line-bright bg-mat px-3 text-sm text-ink outline-none transition-colors placeholder:text-ink-muted focus:border-electric"
      />
    </label>
  )
}
