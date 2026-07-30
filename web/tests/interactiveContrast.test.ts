import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

function channel(value: number): number {
  const normalized = value / 255
  return normalized <= 0.04045
    ? normalized / 12.92
    : ((normalized + 0.055) / 1.055) ** 2.4
}

function luminance(hex: string): number {
  const value = hex.replace('#', '')
  const red = channel(Number.parseInt(value.slice(0, 2), 16))
  const green = channel(Number.parseInt(value.slice(2, 4), 16))
  const blue = channel(Number.parseInt(value.slice(4, 6), 16))
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

function contrast(left: string, right: string): number {
  const leftLuminance = luminance(left)
  const rightLuminance = luminance(right)
  return (
    (Math.max(leftLuminance, rightLuminance) + 0.05) /
    (Math.min(leftLuminance, rightLuminance) + 0.05)
  )
}

function token(css: string, name: string): string {
  const match = css.match(new RegExp(`--color-${name}:\\s*(#[0-9A-Fa-f]{6})`))
  if (!match) throw new Error(`Missing colour token ${name}`)
  return match[1]
}

describe('interactive control contrast tokens', () => {
  const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
  const backgrounds = ['mat', 'panel', 'raised', 'overlay'].map(name => token(css, name))

  it('keeps default interactive text above 4.5:1 on every supported dark surface', () => {
    const foreground = token(css, 'control-fg')
    for (const background of backgrounds) {
      expect(contrast(foreground, background)).toBeGreaterThanOrEqual(4.5)
    }
  })

  it('keeps meaningful control borders and focus indicators above 3:1', () => {
    const border = token(css, 'control-border')
    const focus = token(css, 'electric')
    for (const background of backgrounds) {
      expect(contrast(border, background)).toBeGreaterThanOrEqual(3)
      expect(contrast(focus, background)).toBeGreaterThanOrEqual(3)
    }
  })

  it('uses a separate disabled foreground token', () => {
    expect(token(css, 'control-disabled')).not.toBe(token(css, 'control-fg'))
  })
})
