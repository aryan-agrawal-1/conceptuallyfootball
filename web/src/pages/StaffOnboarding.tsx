import { useState, type FormEvent } from 'react'
import { Check } from 'lucide-react'
import { StaffFrame } from '../components/staff/StaffFrame'
import { StaffRoute } from '../components/staff/StaffRoute'
import { useStaffAuth } from '../context/StaffAuthContext'
import { StaffAuthError, type SocialLinks, type SocialPlatform } from '../lib/staffAuth'
import { useNavigate } from 'react-router-dom'
import { SocialBrandIcon } from '../components/social/SocialBrandIcon'

const SOCIAL_FIELDS: Array<{
  key: SocialPlatform
  label: string
  placeholder: string
}> = [
  { key: 'x', label: 'X', placeholder: 'https://x.com/yourname' },
  { key: 'instagram', label: 'Instagram', placeholder: 'https://instagram.com/yourname' },
  { key: 'bluesky', label: 'Bluesky', placeholder: 'https://bsky.app/profile/yourname.bsky.social' },
  { key: 'youtube', label: 'YouTube', placeholder: 'https://youtube.com/@yourchannel' },
  { key: 'discord', label: 'Discord', placeholder: 'https://discord.com/users/…' },
  { key: 'website', label: 'Personal site', placeholder: 'https://yourname.com' },
]

export function StaffOnboarding() {
  return (
    <StaffRoute allowOnboarding>
      <WriterProfileForm />
    </StaffRoute>
  )
}

function WriterProfileForm() {
  const { user, saveProfile } = useStaffAuth()
  const navigate = useNavigate()
  const [displayName, setDisplayName] = useState(user?.onboarding_required ? '' : user?.display_name ?? '')
  const [socialLinks, setSocialLinks] = useState<SocialLinks>(() => user?.social_links ?? {})
  const [errors, setErrors] = useState<string[]>([])
  const [submitting, setSubmitting] = useState(false)

  if (!user) return null

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setErrors([])
    try {
      await saveProfile(displayName, socialLinks)
      navigate('/analysis', { replace: true })
    } catch (error) {
      if (error instanceof StaffAuthError) {
        setErrors(error.errors.length ? error.errors : [error.message])
      } else {
        setErrors(['Your writer profile could not be saved. Please try again.'])
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <StaffFrame eyebrow={user.onboarding_required ? 'Set up your byline' : 'Writer profile'}>
      <div className="grid flex-1 place-items-center py-10 sm:py-14">
        <section className="w-full max-w-3xl border border-line-bright bg-panel p-6 sm:p-10">
          <p className="font-mono text-[9px] uppercase tracking-[0.22em] text-electric">
            {user.onboarding_required ? 'Final onboarding step' : 'Public author details'}
          </p>
          <h1 className="mt-3 text-3xl font-black tracking-[-0.04em] text-ink sm:text-4xl">
            Put a name to your analysis.
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-dim">
            Your public name appears in every byline. Add any profiles where readers can follow more of your work; all social links are optional.
          </p>

          <form onSubmit={handleSubmit} className="mt-9">
            <label className="block">
              <span className="mb-2 block font-mono text-[9px] uppercase tracking-[0.18em] text-ink-dim">Public name</span>
              <input value={displayName} onChange={event => setDisplayName(event.target.value)} maxLength={100} autoComplete="name" placeholder="e.g. Alex Morgan" className="h-12 w-full border border-line-bright bg-mat px-4 text-sm text-ink outline-none placeholder:text-ink-muted focus:border-electric" required />
              <span className="mt-2 block text-[10px] text-ink-muted">This replaces your email address in article bylines.</span>
            </label>

            <div className="mt-8 border-t border-line pt-7">
              <div className="grid gap-4 sm:grid-cols-2">
                {SOCIAL_FIELDS.map(({ key, label, placeholder }) => (
                  <label key={key} className="block">
                    <span className="mb-2 flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.16em] text-ink-dim"><span className="grid size-6 place-items-center border border-line-bright bg-panel text-electric"><SocialBrandIcon platform={key} className="size-3" /></span>{label}</span>
                    <input type="url" value={socialLinks[key] ?? ''} onChange={event => setSocialLinks(current => ({ ...current, [key]: event.target.value }))} placeholder={placeholder} className="h-11 w-full border border-line bg-mat px-3 text-xs text-ink outline-none placeholder:text-ink-muted focus:border-electric" />
                  </label>
                ))}
              </div>
            </div>

            {errors.length ? <ul role="alert" className="mt-6 border-l-2 border-ember bg-ember/5 px-4 py-2 text-xs leading-5 text-red-300">{errors.map(error => <li key={error}>{error}</li>)}</ul> : null}

            <div className="mt-8 flex flex-col-reverse gap-3 border-t border-line pt-6 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-[10px] leading-5 text-ink-muted">You can update these details from the analysis desk at any time.</p>
              <button type="submit" disabled={submitting || displayName.trim().length < 2} className="inline-flex h-11 items-center justify-center gap-2 bg-electric px-6 text-[9px] font-black uppercase tracking-[0.16em] text-mat hover:bg-ink disabled:bg-line-bright disabled:text-ink-muted"><Check className="size-4" />{submitting ? 'Saving…' : 'Save writer profile'}</button>
            </div>
          </form>
        </section>
      </div>
    </StaffFrame>
  )
}
