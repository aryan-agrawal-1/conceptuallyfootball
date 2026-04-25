/**
 * Lowercase, accent-insensitive folding for search matching.
 * Display strings stay untouched; compare using this on both query and text.
 *
 * Most accents strip via NFD + removing combining marks (`\p{M}`). Some Latin
 * letters (e.g. ø, æ) do *not* decompose that way in Unicode, so we map them
 * explicitly — otherwise "ode" cannot match "Ødegaard".
 */
export function foldForSearch(s: string): string {
  let t = s.normalize('NFD').replace(/\p{M}/gu, '')
  t = foldLatinWithoutMarkDecomposition(t)
  return t.toLowerCase()
}

/** Letters that stay as one code point after NFD and need ASCII-ish substitutes. */
function foldLatinWithoutMarkDecomposition(s: string): string {
  let out = ''
  for (const c of s) {
    const code = c.charCodeAt(0)
    switch (code) {
      case 0x00d8: // Ø
      case 0x00f8: // ø
        out += 'o'
        break
      case 0x00c6: // Æ
      case 0x00e6: // æ
        out += 'ae'
        break
      case 0x0152: // Œ
      case 0x0153: // œ
        out += 'oe'
        break
      case 0x00df: // ß
        out += 'ss'
        break
      case 0x0130: // İ
        out += 'i'
        break
      case 0x0131: // ı
        out += 'i'
        break
      default:
        out += c
    }
  }
  return out
}
