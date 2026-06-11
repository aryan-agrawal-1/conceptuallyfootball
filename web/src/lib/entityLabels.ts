export function shortEntityLabel(label: string): string {
  const parts = label.trim().split(/\s+/).filter(Boolean)
  if (parts.length <= 2) return label
  return `${parts[0]} ${parts[parts.length - 1]}`
}
