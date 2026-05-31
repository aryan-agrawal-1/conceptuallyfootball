import { spawnSync } from 'node:child_process'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import path from 'node:path'

const ROOT = path.resolve(import.meta.dirname, '..')
const LOGO_DIR = path.join(ROOT, 'web/public/logos/teams')
const TEAM_LOGOS_TS = path.join(ROOT, 'web/src/lib/teamLogos.ts')

const COMPETITION_COUNTRY = {
  BEL1: 'belgium',
  CYP1: 'cyprus',
  CZE1: 'czech-republic',
  DEN1: 'denmark',
  ENG1: 'england',
  ENG2: 'england',
  EST1: 'estonia',
  FRA1: 'france',
  GER1: 'germany',
  GRE1: 'greece',
  ITA1: 'italy',
  NED1: 'netherlands',
  NOR1: 'norway',
  POL1: 'poland',
  POR1: 'portugal',
  SCO1: 'scotland',
  SPA1: 'spain',
  TUR1: 'turkey',
}

const MANUAL_ALIASES = new Map(Object.entries({
  '1-fc-heidenheim': 'fc-heidenheim',
  '1-fc-koln': 'koln',
  '1-fc-union-berlin': 'union-berlin',
  '1-fsv-mainz-05': 'mainz-05',
  'ac-milan': 'milan',
  'afc-ajax': 'ajax',
  'as-monaco': 'monaco',
  'as-saint-etienne': 'saint-etienne',
  'bochum': 'vfl-bochum',
  'brighton-and-hove-albion-f-c': 'brighton',
  'brighton-and-hove-albion-fc': 'brighton',
  'brighton-hove-albion-f-c': 'brighton',
  'brighton-hove-albion-fc': 'brighton',
  'casa-pia': 'casa-pia-ac',
  'celta-vigo': 'celta',
  'charlton-athletic': 'charlton',
  'clermont-foot-63': 'clermont-foot',
  'como': 'como-1907',
  'cs-maritimo': 'maritimo',
  'darmstadt-98': 'darmstadt',
  'athletic-club': 'athletic-club',
  'fcv-dender': 'fcv-dender-eh',
  'k-beerschot-v-a': 'beerschot-wilrijk',
  'kaa-gent': 'gent',
  'kas-eupen': 'eupen',
  'kmsk-deinze': 'deinze',
  'krc-genk': 'genk',
  'ksc-lokeren': 'lokeren',
  'kvc-westerlo': 'westerlo',
  'lommel-sk': 'lommel',
  'rc-sporting-charleroi': 'charleroi',
  'rsc-anderlecht': 'anderlecht',
  'rwdm-brussels': 'rwd-molenbeek',
  'royal-antwerp-fc': 'antwerp',
  'royale-union-saint-gilloise': 'union-saint-gilloise',
  'sk-beveren': 'beveren',
  'sint-truidense-vv': 'sint-truidense',
  'bayer-04-leverkusen': 'bayer-leverkusen',
  'borussia-mgladbach': 'borussia-monchengladbach',
  'borussia-m-gladbach': 'borussia-monchengladbach',
  'deportivo-alaves': 'deportivo',
  'estrela-amadora': 'estrela-da-amadora',
  'estoril-praia': 'estoril',
  'fc-augsburg': 'augsburg',
  'fc-bayern-munich': 'bayern-munchen',
  'fc-bayern-munchen': 'bayern-munchen',
  'fc-cologne': 'koln',
  'fc-heidenheim': 'heidenheim',
  'cd-nacional': 'nacional-da-madeira',
  'excelsior': 'excelsior-rotterdam',
  'fc-porto': 'porto',
  'fc-schalke-04': 'schalke',
  'fc-st-pauli': 'st-pauli',
  'fiorentina-juventus': 'fiorentina',
  'hellas-verona': 'verona',
  'heart-of-midlothian': 'hearts',
  'hertha-berlin': 'hertha-bsc',
  'huddersfield-town': 'huddersfield',
  'inter': 'inter',
  'ipswich-town': 'ipswich',
  'juventus-fc': 'juventus',
  'leeds-afc': 'leeds-united',
  'leeds-a-f-c': 'leeds-united',
  'le-havre': 'le-havre-ac',
  'lens': 'rc-lens',
  'levante-ud': 'levante',
  'luton': 'luton-town',
  'manchester-city-fc': 'manchester-city',
  'manchester-united-fc': 'manchester-united',
  'metz': 'fc-metz',
  'monaco': 'as-monaco',
  'olympique-de-marseille': 'marseille',
  'olympique-lyonnais': 'lyon',
  'parma-calcio-1913': 'parma',
  'paris-saint-germain-fc': 'paris-saint-germain',
  'pacos-de-ferreira': 'pacos-ferreira',
  'psv-eindhoven': 'psv',
  'rangers': 'rangers-fc',
  'rasenballsport-leipzig': 'rb-leipzig',
  'rc-celta-de-vigo': 'celta',
  'rc-strasbourg': 'rc-strasbourg-alsace',
  'rc-lens': 'lens',
  'rcd-espanyol-de-barcelona': 'espanyol',
  'rcd-mallorca': 'mallorca',
  'real-oviedo': 'oviedo',
  'real-valladolid': 'valladolid',
  'real-betis-balompie': 'real-betis',
  'reims': 'stade-de-reims',
  'rkc-waalwijk': 'rkc',
  'saint-etienne': 'as-saint-etienne',
  'sc-freiburg': 'freiburg',
  'sc-farense': 'farense',
  'sc-telstar': 'telstar',
  'sporting-braga': 'sc-braga',
  'ssc-napoli': 'napoli',
  'stade-brestois': 'brest',
  'stade-rennais': 'rennes',
  'sv-werder-bremen': 'werder-bremen',
  'spvgg-greuther-furth': 'spvgg-greuther-furth',
  'greuther-fuerth': 'spvgg-greuther-furth',
  'tottenham-hotspur-f-c': 'tottenham',
  'tottenham-hotspur-fc': 'tottenham',
  'tsg-hoffenheim': 'hoffenheim',
  'ud-las-palmas': 'las-palmas',
  'usl-dunkerque': 'dunkerque',
  'vitoria-sc': 'vitoria-de-guimaraes',
  'vfb-stuttgart': 'stuttgart',
  'vfl-bochum-1848': 'vfl-bochum',
  'vfl-wolfsburg': 'wolfsburg',
  'wigan-athletic': 'wigan',
  'willem-ii-tilburg': 'willem-ii',
  'wolverhampton-wanderers-f-c': 'wolves',
  'wolverhampton-wanderers-fc': 'wolves',
}))

function slugify(value) {
  return value
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/&/g, ' and ')
    .replace(/['’]/g, '')
    .replace(/\+/g, ' plus ')
    .replace(/[^a-zA-Z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .toLowerCase()
}

function cleanTeamName(value) {
  return value
    .replace(/\s*\([^)]*\)\s*/g, ' ')
    .replace(/\b(F\.?C\.?|A\.?F\.?C\.?|C\.?F\.?|S\.?A\.?D\.?|KV|K\.?|R\.?C\.?|R\.?F\.?C\.?|S\.?V\.?)\b/gi, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function candidatesFor(teamName) {
  const firstClub = teamName.split(',')[0].trim()
  const cleaned = cleanTeamName(firstClub)
  const candidates = [
    slugify(firstClub),
    slugify(cleaned),
    slugify(firstClub.replace(/\bUnited\b/i, '')),
    slugify(firstClub.replace(/\bCity\b/i, '')),
    slugify(cleaned.replace(/\bUnited\b/i, '')),
    slugify(cleaned.replace(/\bCity\b/i, '')),
  ].filter(Boolean)

  const withAliases = new Set(candidates)
  for (const candidate of candidates) {
    if (MANUAL_ALIASES.has(candidate)) {
      withAliases.add(MANUAL_ALIASES.get(candidate))
    }
  }
  return [...withAliases]
}

function getTeams() {
  const code = `
import json
from ingestion.models import MergedPlayerSeason
rows = (
    MergedPlayerSeason.objects
    .filter(is_current=True, canonical_display_team__isnull=False)
    .select_related("canonical_display_team", "competition_season__competition")
    .values_list("competition_season__competition__short_code", "canonical_display_team_id", "canonical_display_team__name")
    .distinct()
    .order_by("competition_season__competition__short_code", "canonical_display_team__name")
)
print(json.dumps([
    {"competition_code": code, "team_id": team_id, "team_name": team_name}
    for code, team_id, team_name in rows
]))
`
  const result = spawnSync(
    'backend/venv/bin/python',
    ['backend/manage.py', 'shell', '-c', code],
    { cwd: ROOT, encoding: 'utf8' },
  )
  if (result.status !== 0) {
    throw new Error(result.stderr || result.stdout)
  }
  const jsonLine = result.stdout.trim().split('\n').at(-1)
  return JSON.parse(jsonLine)
}

async function fetchText(url) {
  const response = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
    },
  })
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`)
  }
  return response.text()
}

async function fetchBytes(url) {
  const response = await fetch(url, {
    headers: {
      'User-Agent': 'Mozilla/5.0',
    },
  })
  if (!response.ok) {
    throw new Error(`GET ${url} failed with ${response.status}`)
  }
  return Buffer.from(await response.arrayBuffer())
}

function parseCountryLogos(country, html) {
  const logos = new Map()
  const re = /data-logo-downloads[^>]*data-category-id="([^"]+)"[^>]*data-logo-id="([^"]+)"[^>]*data-svg-hash="([^"]+)"/g
  let match
  while ((match = re.exec(html)) != null) {
    const [, category, logoId, svgHash] = match
    if (category !== country) {
      continue
    }
    const pngPattern = new RegExp(
      `https://assets\\.football-logos\\.cc/logos/${country}/256x256/${logoId.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.([a-f0-9]+)\\.png`,
    )
    const pngHash = html.match(pngPattern)?.[1]
    if (!pngHash) {
      continue
    }
    logos.set(logoId, { country, logoId, svgHash, pngHash })
  }
  return logos
}

function resolveLogo(team, countryLogos) {
  const country = COMPETITION_COUNTRY[team.competition_code]
  const logos = countryLogos.get(country)
  if (!logos) {
    return null
  }
  for (const candidate of candidatesFor(team.team_name)) {
    if (logos.has(candidate)) {
      return logos.get(candidate)
    }
  }
  return null
}

async function writeTeamLogosModule(matched) {
  let existingNameMap = ''
  if (existsSync(TEAM_LOGOS_TS)) {
    existingNameMap = await readFile(TEAM_LOGOS_TS, 'utf8')
  }

  const byTeamId = new Map()
  for (const item of matched) {
    byTeamId.set(item.teamId, item)
  }

  const idEntries = [...byTeamId.values()]
    .sort((a, b) => a.teamId - b.teamId)
    .map(({ teamId }) => `  ${teamId}: '/logos/teams/${teamId}.png',`)
    .join('\n')

  const moduleText = `/**
 * Maps canonical team ids/names from the backend to locally served logo paths.
 * Generated with scripts/sync-team-logos.mjs.
 */
export const TEAM_LOGOS_BY_ID: Record<number, string> = {
${idEntries}
}

${existingNameMap.match(/export const TEAM_LOGOS:[\s\S]*?\n}/)?.[0] ?? 'export const TEAM_LOGOS: Record<string, string> = {\n}'}

export function getTeamLogoPath(teamId: number | null | undefined, teamName: string | null | undefined): string | undefined {
  if (teamId != null && TEAM_LOGOS_BY_ID[teamId]) {
    return TEAM_LOGOS_BY_ID[teamId]
  }
  if (teamName && TEAM_LOGOS[teamName]) {
    return TEAM_LOGOS[teamName]
  }
  return undefined
}
`

  await writeFile(TEAM_LOGOS_TS, moduleText)
}

async function main() {
  const teams = getTeams()
  await mkdir(LOGO_DIR, { recursive: true })

  const countries = [...new Set(teams.map(team => COMPETITION_COUNTRY[team.competition_code]).filter(Boolean))]
  const countryLogos = new Map()
  for (const country of countries) {
    const html = await fetchText(`https://football-logos.cc/${country}/`)
    countryLogos.set(country, parseCountryLogos(country, html))
  }

  const matched = []
  const unmatched = []
  const seenIds = new Set()
  for (const team of teams) {
    const logo = resolveLogo(team, countryLogos)
    if (!logo) {
      unmatched.push(team)
      continue
    }
    matched.push({
      teamId: team.team_id,
      teamName: team.team_name,
      logo,
    })
    if (seenIds.has(team.team_id)) {
      continue
    }
    seenIds.add(team.team_id)
    const url = `https://assets.football-logos.cc/logos/${logo.country}/256x256/${logo.logoId}.${logo.pngHash}.png`
    const bytes = await fetchBytes(url)
    await writeFile(path.join(LOGO_DIR, `${team.team_id}.png`), bytes)
  }

  await writeTeamLogosModule(matched)
  await writeFile(
    path.join(ROOT, 'scripts/team-logo-unmatched.json'),
    `${JSON.stringify(unmatched, null, 2)}\n`,
  )

  console.log(`Matched ${matched.length} team rows, downloaded ${seenIds.size} unique team-id logos.`)
  console.log(`Unmatched ${unmatched.length} team rows. See scripts/team-logo-unmatched.json`)
}

main().catch(error => {
  console.error(error)
  process.exitCode = 1
})
