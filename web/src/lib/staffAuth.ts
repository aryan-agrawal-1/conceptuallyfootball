export interface StaffUser {
  id: number
  email: string
  display_name: string
  role: 'writer' | 'approver' | 'operations' | 'superuser' | null
  must_change_password: boolean
  can_access_editorial: boolean
  can_approve_editorial: boolean
  can_access_operations: boolean
}

export interface StaffSession {
  authenticated: boolean
  user?: StaffUser
}

export class StaffAuthError extends Error {
  code?: string
  errors: string[]

  constructor(message: string, code?: string, errors: string[] = []) {
    super(message)
    this.name = 'StaffAuthError'
    this.code = code
    this.errors = errors
  }
}

const AUTH_BASE = '/api/v1/auth'

function cookieValue(name: string): string {
  const encodedName = `${encodeURIComponent(name)}=`
  const cookie = document.cookie.split('; ').find(value => value.startsWith(encodedName))
  return cookie ? decodeURIComponent(cookie.slice(encodedName.length)) : ''
}

async function responseJson<T>(response: Response): Promise<T> {
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new StaffAuthError(
      body.detail ?? `Request failed with status ${response.status}.`,
      body.code,
      body.errors,
    )
  }
  return body as T
}

async function csrfHeaders(): Promise<HeadersInit> {
  let token = cookieValue('csrftoken')
  if (!token) {
    const response = await fetch(`${AUTH_BASE}/csrf`, {
      credentials: 'same-origin',
      cache: 'no-store',
    })
    await responseJson(response)
    token = cookieValue('csrftoken')
  }
  return {
    'Content-Type': 'application/json',
    'X-CSRFToken': token,
  }
}

async function postAuth<T>(path: string, payload: Record<string, string> = {}): Promise<T> {
  const response = await fetch(`${AUTH_BASE}/${path}`, {
    method: 'POST',
    credentials: 'same-origin',
    cache: 'no-store',
    headers: await csrfHeaders(),
    body: JSON.stringify(payload),
  })
  return responseJson<T>(response)
}

export async function fetchStaffSession(): Promise<StaffSession> {
  const response = await fetch(`${AUTH_BASE}/session`, {
    credentials: 'same-origin',
    cache: 'no-store',
  })
  return responseJson<StaffSession>(response)
}

export function signIn(email: string, password: string): Promise<StaffSession> {
  return postAuth('login', { email, password })
}

export function signOut(): Promise<StaffSession> {
  return postAuth('logout')
}

export function replaceTemporaryPassword(
  currentPassword: string,
  newPassword: string,
): Promise<StaffSession> {
  return postAuth('password', {
    current_password: currentPassword,
    new_password: newPassword,
  })
}
