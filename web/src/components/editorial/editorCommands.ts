import { inlineText, type ArticleBlock, type InlineContent, type VisualBlockType } from '../../lib/editorial'

export const BLOCK_COMMANDS = [
  { value: 'paragraph', label: 'Text', description: 'A standard paragraph', group: 'Writing', keywords: 'paragraph text' },
  { value: 'heading:2', label: 'Heading 2', description: 'A main section heading', group: 'Writing', keywords: 'heading section h2' },
  { value: 'heading:3', label: 'Heading 3', description: 'A smaller subheading', group: 'Writing', keywords: 'heading subheading h3' },
  { value: 'bulleted_list', label: 'Bulleted list', description: 'An unordered list', group: 'Writing', keywords: 'bullet unordered list' },
  { value: 'numbered_list', label: 'Numbered list', description: 'A numbered sequence', group: 'Writing', keywords: 'number ordered list' },
  { value: 'quote', label: 'Quote', description: 'A prominent quotation', group: 'Writing', keywords: 'quote pullquote' },
  { value: 'callout', label: 'Key insight', description: 'A highlighted conclusion or caveat', group: 'Writing', keywords: 'callout insight note warning' },
  { value: 'image', label: 'Image', description: 'An image with caption and alt text', group: 'Media', keywords: 'image photo media' },
  { value: 'divider', label: 'Divider', description: 'A visual section break', group: 'Media', keywords: 'divider rule separator' },
] as const

export const VISUAL_COMMANDS = [
  { value: 'visual:similar_players', label: 'Similar players', description: 'A ranked similarity analysis', group: 'Data visuals', keywords: 'visual chart similarity player' },
  { value: 'visual:player_radar', label: 'Player profile', description: 'A percentile radar profile', group: 'Data visuals', keywords: 'visual chart pizza radar player profile percentile' },
  { value: 'visual:stat_card', label: 'Key-stat cards', description: 'A compact statistical summary', group: 'Data visuals', keywords: 'visual player team stats percentile cards' },
  { value: 'visual:player_comparison', label: 'Player comparison', description: 'Compare players side by side', group: 'Data visuals', keywords: 'visual compare versus radar' },
  { value: 'visual:custom_chart', label: 'Custom chart', description: 'Build a chart from selected metrics', group: 'Data visuals', keywords: 'visual graph scatter bar x y player team' },
] as const

export const EDITOR_COMMANDS = [...BLOCK_COMMANDS, ...VISUAL_COMMANDS]

export type BlockTypeChoice = typeof BLOCK_COMMANDS[number]['value']
export type EditorCommandChoice = BlockTypeChoice | typeof VISUAL_COMMANDS[number]['value']

export function isVisualChoice(value: EditorCommandChoice): value is `visual:${VisualBlockType}` {
  return value.startsWith('visual:')
}

export function visualTypeFromChoice(value: `visual:${VisualBlockType}`): VisualBlockType {
  return value.slice('visual:'.length) as VisualBlockType
}

export function createBlockFromChoice(choice: BlockTypeChoice): ArticleBlock {
  return convertBlock({ id: crypto.randomUUID(), type: 'paragraph', content: inlineText('') }, choice)
}

export function convertBlock(block: ArticleBlock, choice: BlockTypeChoice): ArticleBlock {
  const content = contentFromBlock(block)
  const id = block.id
  switch (choice) {
    case 'paragraph': return { id, type: 'paragraph', content }
    case 'heading:2': return { id, type: 'heading', level: 2, content }
    case 'heading:3': return { id, type: 'heading', level: 3, content }
    case 'quote': return { id, type: 'quote', content }
    case 'callout': return { id, type: 'callout', tone: 'insight', content }
    case 'bulleted_list': return { id, type: 'bulleted_list', items: [content] }
    case 'numbered_list': return { id, type: 'numbered_list', items: [content] }
    case 'image': return { id, type: 'image', url: '', caption: '', alt: '' }
    case 'divider': return { id, type: 'divider' }
  }
}

export function blockChoice(block: ArticleBlock): BlockTypeChoice {
  if (block.type === 'visual') return 'paragraph'
  return block.type === 'heading' ? `heading:${block.level}` : block.type
}

export function blockLabel(block: ArticleBlock): string {
  if (block.type === 'visual') return VISUAL_COMMANDS.find(command => command.value === `visual:${block.visual_type}`)?.label ?? 'Visual'
  return BLOCK_COMMANDS.find(command => command.value === blockChoice(block))?.label ?? 'Block'
}

function contentFromBlock(block: ArticleBlock): InlineContent {
  if (block.type === 'heading' || block.type === 'paragraph' || block.type === 'quote' || block.type === 'callout') return block.content
  if (block.type === 'bulleted_list' || block.type === 'numbered_list') return block.items[0] ?? inlineText('')
  if (block.type === 'image' || block.type === 'visual') return inlineText(block.caption || block.alt)
  return inlineText('')
}
