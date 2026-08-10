import { useState, type FormEvent } from 'react'
import { Check, LockKeyhole } from 'lucide-react'
import { Navigate, useNavigate } from 'react-router-dom'
import { StaffFrame } from '../components/staff/StaffFrame'
import { StaffRoute } from '../components/staff/StaffRoute'
import { useStaffAuth } from '../context/StaffAuthContext'
import { StaffAuthError } from '../lib/staffAuth'

export function StaffChangePassword() {
  return (
    <StaffRoute allowPasswordChange>
      <ChangePasswordForm />
    </StaffRoute>
  )
}

function ChangePasswordForm() {
  const { user, changePassword } = useStaffAuth()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [errors, setErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)
  const navigate = useNavigate()

  if (!user) return null
  if (!user.must_change_password) return <Navigate to="/analysis" replace />

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (newPassword === currentPassword) {
      setErrors(['Your new password must be different from your temporary password.'])
      return
    }
    if (newPassword !== confirmation) {
      setErrors(['The new passwords do not match.'])
      return
    }
    setSubmitting(true)
    setErrors([])
    try {
      await changePassword(currentPassword, newPassword)
      navigate('/analysis', { replace: true })
    } catch (caughtError) {
      if (caughtError instanceof StaffAuthError) {
        setErrors(caughtError.errors.length ? caughtError.errors : [caughtError.message])
      } else {
        setErrors(['The password could not be changed. Please try again.'])
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <StaffFrame eyebrow="Secure your account">
      <div className="grid flex-1 place-items-center py-12">
        <section className="w-full max-w-xl border border-line-bright bg-panel p-6 sm:p-10">
          <div className="flex size-11 items-center justify-center border border-electric/40 bg-electric-dim text-electric">
            <LockKeyhole className="size-5" />
          </div>
          <p className="mt-8 font-mono text-[9px] uppercase tracking-[0.22em] text-electric">
            First sign-in · {user.email}
          </p>
          <h1 className="mt-3 text-3xl font-black tracking-[-0.035em] text-ink">
            Replace your temporary password.
          </h1>
          <p className="mt-3 text-sm leading-6 text-ink-dim">
            This step is required before the editorial workspace becomes available.
          </p>
          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <PasswordInput label="Temporary password" value={currentPassword} onChange={setCurrentPassword} autoComplete="current-password" />
            <PasswordInput label="New password" value={newPassword} onChange={setNewPassword} autoComplete="new-password" />
            <PasswordInput label="Confirm new password" value={confirmation} onChange={setConfirmation} autoComplete="new-password" />
            <p className="text-[10px] leading-5 text-ink-muted">
              Use at least eight characters and avoid common, entirely numeric, or personally similar passwords.
            </p>
            {errors.length ? (
              <ul role="alert" className="border-l-2 border-ember bg-ember/5 px-4 py-2 text-xs leading-5 text-red-300">
                {errors.map(error => <li key={error}>{error}</li>)}
              </ul>
            ) : null}
            <button
              type="submit"
              disabled={submitting || !currentPassword || !newPassword || !confirmation}
              className="flex h-12 w-full items-center justify-center gap-2 bg-electric text-[11px] font-black uppercase tracking-[0.16em] text-mat hover:bg-blue-300 disabled:bg-line-bright disabled:text-ink-muted"
            >
              <Check className="size-4" />
              {submitting ? 'Securing account…' : 'Save and continue'}
            </button>
          </form>
        </section>
      </div>
    </StaffFrame>
  )
}

function PasswordInput({ label, value, onChange, autoComplete }: { label: string; value: string; onChange: (value: string) => void; autoComplete: string }) {
  return (
    <label className="block">
      <span className="mb-2 block font-mono text-[9px] uppercase tracking-[0.18em] text-ink-dim">{label}</span>
      <input type="password" value={value} onChange={event => onChange(event.target.value)} autoComplete={autoComplete} required className="h-12 w-full border border-line-bright bg-mat px-3 text-sm text-ink outline-none focus:border-electric" />
    </label>
  )
}
