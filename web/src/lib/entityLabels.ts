const SURNAME_PARTICLE_SEQUENCES = [
  ['van', 'de'],
  ['van', 'der'],
  ['op', 'de'],
  ['van'],
  ['de'],
  ['den'],
  ['der'],
  ['ter'],
  ['ten'],
  ['te'],
  ['del'],
  ['della'],
  ['di'],
  ['da'],
  ['dos'],
  ['das'],
  ['do'],
  ['mac'],
  ['mc'],
  ['el'],
  ['al'],
  ['ben'],
  ['ibn'],
  ['abdel'],
  ['abdul'],
]

function matchesParticleSequence(parts: string[], start: number, sequence: string[]): boolean {
  if (start + sequence.length >= parts.length) return false
  return sequence.every((token, index) => parts[start + index]?.toLowerCase() === token)
}

export function shortPlayerName(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 2) return name

  for (let i = 1; i < parts.length - 1; i += 1) {
    const sequence = SURNAME_PARTICLE_SEQUENCES.find(candidate => matchesParticleSequence(parts, i, candidate))
    if (sequence) return `${parts[0]} ${parts.slice(i).join(' ')}`
  }

  return `${parts[0]} ${parts[parts.length - 1]}`
}

export function shortEntityLabel(label: string): string {
  return shortPlayerName(label)
}

export function playerNameTitle(name: string): string | undefined {
  return shortPlayerName(name) === name ? undefined : name
}
