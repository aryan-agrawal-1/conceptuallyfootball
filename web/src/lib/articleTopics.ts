export const ARTICLE_TOPICS = [
  'Tactics',
  'Match analysis',
  'Player analysis',
  'Team analysis',
  'Recruitment',
  'Coaching',
  'Data analysis',
  'Football culture',
] as const

export type ArticleTopic = typeof ARTICLE_TOPICS[number]
