import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchStaffSession,
  replaceTemporaryPassword,
  signIn,
  signOut,
  type StaffSession,
  type StaffUser,
} from '../lib/staffAuth'

interface StaffAuthContextValue {
  user: StaffUser | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<StaffUser>
  logout: () => Promise<void>
  changePassword: (currentPassword: string, newPassword: string) => Promise<StaffUser>
}

const SESSION_QUERY_KEY = ['staff-session'] as const
const StaffAuthContext = createContext<StaffAuthContextValue | null>(null)

export function StaffAuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const sessionQuery = useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: fetchStaffSession,
    staleTime: 30_000,
    retry: false,
  })

  const storeSession = useCallback(
    (session: StaffSession): StaffUser => {
      queryClient.setQueryData(SESSION_QUERY_KEY, session)
      if (!session.user) throw new Error('The server did not return the signed-in user.')
      return session.user
    },
    [queryClient],
  )

  const login = useCallback(
    async (email: string, password: string) => storeSession(await signIn(email, password)),
    [storeSession],
  )

  const logout = useCallback(async () => {
    const session = await signOut()
    queryClient.setQueryData(SESSION_QUERY_KEY, session)
  }, [queryClient])

  const changePassword = useCallback(
    async (currentPassword: string, newPassword: string) =>
      storeSession(await replaceTemporaryPassword(currentPassword, newPassword)),
    [storeSession],
  )

  const value = useMemo(
    () => ({
      user: sessionQuery.data?.user ?? null,
      isLoading: sessionQuery.isLoading,
      login,
      logout,
      changePassword,
    }),
    [changePassword, login, logout, sessionQuery.data?.user, sessionQuery.isLoading],
  )

  return <StaffAuthContext.Provider value={value}>{children}</StaffAuthContext.Provider>
}

// The provider and its paired hook intentionally share one context module.
// eslint-disable-next-line react-refresh/only-export-components
export function useStaffAuth(): StaffAuthContextValue {
  const context = useContext(StaffAuthContext)
  if (!context) throw new Error('useStaffAuth must be used inside StaffAuthProvider.')
  return context
}
