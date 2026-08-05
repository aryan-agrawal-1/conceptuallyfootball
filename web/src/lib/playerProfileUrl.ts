import { withProfileSliceParams, type ProfileSlice } from './profileSlice'

/**
 * Keeps the application's comparison scope separate from the concrete
 * league-season membership displayed by a player profile.
 */
export function withPlayerProfileSlice(
  path: string,
  slice?: ProfileSlice | null,
): string {
  if (!slice) return path

  const [pathname, rawSearch = ''] = path.split('?')
  const params = withProfileSliceParams(new URLSearchParams(rawSearch), slice)
  return `${pathname}?${params.toString()}`
}
