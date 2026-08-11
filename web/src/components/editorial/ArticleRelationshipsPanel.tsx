import { AtSign, Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'
import {
  editorialEntityPath,
  type ArticleRelationships,
  type EditorialEntityKind,
  type EditorialEntityReference,
} from '../../lib/editorial'
import { foldForSearch } from '../../lib/foldAccents'
import type {
  SearchEntitiesResponse,
  SearchPlayerEntity,
  SearchTeamEntity,
} from '../../types/api'

const MAX_SUBJECTS = 2

export function ArticleRelationshipsPanel({
  subjects,
  references,
  entities,
  loading,
  onChange,
  readOnly = false,
}: {
  subjects: ArticleRelationships
  references: ArticleRelationships
  entities?: SearchEntitiesResponse
  loading: boolean
  onChange: (subjects: ArticleRelationships) => void
  readOnly?: boolean
}) {
  return (
    <div className="space-y-5">
      <div className="border-l-2 border-electric bg-electric-dim/25 px-3 py-2.5">
        <p className="text-[11px] leading-5 text-ink-dim"><strong className="text-ink">Subjects drive discovery.</strong> {readOnly ? 'Verify these separately from inline references before approval.' : 'Add the players and teams this piece is principally about.'}</p>
      </div>
      <SubjectGroup kind="player" selected={subjects.players} entities={entities} loading={loading} readOnly={readOnly} onChange={players => onChange({ ...subjects, players })} />
      <SubjectGroup kind="team" selected={subjects.teams} entities={entities} loading={loading} readOnly={readOnly} onChange={teams => onChange({ ...subjects, teams })} />
      <div className="border-t border-line pt-5">
        <p className="flex items-center gap-2 font-mono text-[8px] uppercase tracking-[0.18em] text-ink-muted"><AtSign className="size-3 text-electric" /> References in draft</p>
        <p className="mt-2 text-[10px] leading-4 text-ink-muted">Type @ while writing. Mentions stay separate from subjects.</p>
        <ReferenceList references={references} />
      </div>
    </div>
  )
}

function SubjectGroup({
  kind,
  selected,
  entities,
  loading,
  onChange,
  readOnly,
}: {
  kind: EditorialEntityKind
  selected: EditorialEntityReference[]
  entities?: SearchEntitiesResponse
  loading: boolean
  onChange: (next: EditorialEntityReference[]) => void
  readOnly: boolean
}) {
  const [query, setQuery] = useState('')
  const options = useMemo(() => {
    const needle = foldForSearch(query.trim())
    if (!needle || !entities) return []
    const selectedIds = new Set(selected.map(entity => entity.id))
    const source = kind === 'player' ? entities.players : entities.teams
    return source.filter(entity => {
      const id = canonicalId(entity)
      const name = canonicalName(entity)
      return !selectedIds.has(id) && foldForSearch(name).includes(needle)
    }).slice(0, 6)
  }, [entities, kind, query, selected])
  const label = kind === 'player' ? 'Player subjects' : 'Team subjects'

  function addSubject(entity: SearchPlayerEntity | SearchTeamEntity) {
    if (selected.length >= MAX_SUBJECTS) return
    onChange([...selected, referenceFromSearch(entity)])
    setQuery('')
  }

  return (
    <section>
      <div className="flex items-center justify-between">
        <p className="font-mono text-[8px] uppercase tracking-[0.16em] text-ink-dim">{label}</p>
        <span className="font-mono text-[7px] text-ink-muted">{selected.length}/{MAX_SUBJECTS}</span>
      </div>
      <div className="mt-2 space-y-2">
        {selected.map((entity, index) => (
          <div key={`${entity.kind}-${entity.id}`} className="border border-line bg-panel/60 p-2.5">
            <div className="flex items-center gap-2">
              <a href={editorialEntityPath(entity)} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-xs font-bold text-ink hover:text-electric">{entity.name}</a>
              {!readOnly ? <button type="button" onClick={() => onChange(selected.filter((_, selectedIndex) => selectedIndex !== index))} className="grid size-7 place-items-center text-ink-muted hover:text-ember" aria-label={`Remove ${entity.name} as a subject`}><X className="size-3.5" /></button> : null}
            </div>
          </div>
        ))}
      </div>
      {!readOnly && selected.length < MAX_SUBJECTS ? (
        <div className="relative mt-2">
          <label className="flex h-9 items-center gap-2 border border-line bg-mat px-3 focus-within:border-electric">
            <Search className="size-3.5 text-ink-muted" />
            <input value={query} onChange={event => setQuery(event.target.value)} placeholder={loading ? 'Loading canonical index…' : `Find a ${kind}`} disabled={loading} className="min-w-0 flex-1 bg-transparent text-xs text-ink placeholder:text-ink-muted focus:outline-none disabled:opacity-50" />
          </label>
          {query.trim() ? (
            <div className="absolute inset-x-0 top-full z-30 border border-line-bright bg-panel p-1 shadow-xl">
              {options.length ? options.map(entity => <button key={`${entity.kind}-${canonicalId(entity)}`} type="button" onClick={() => addSubject(entity)} className="flex w-full items-center justify-between gap-3 px-2.5 py-2 text-left text-xs text-ink-dim hover:bg-electric-dim hover:text-electric"><span className="truncate font-bold">{canonicalName(entity)}</span><span className="shrink-0 font-mono text-[7px] uppercase opacity-60">{entity.kind}</span></button>) : <p className="px-2.5 py-3 text-center text-[10px] text-ink-muted">No canonical match.</p>}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  )
}

function ReferenceList({ references }: { references: ArticleRelationships }) {
  const all = [...references.players, ...references.teams]
  if (!all.length) return <p className="mt-3 border border-dashed border-line px-3 py-4 text-center text-[10px] text-ink-muted">No @ references yet.</p>
  return <div className="mt-3 flex flex-wrap gap-1.5">{all.map(entity => <a key={`${entity.kind}-${entity.id}`} href={editorialEntityPath(entity)} target="_blank" rel="noreferrer" className="border border-line bg-panel px-2 py-1 text-[9px] text-ink-dim hover:border-electric hover:text-electric">@{entity.name}</a>)}</div>
}

function canonicalId(entity: SearchPlayerEntity | SearchTeamEntity): number {
  return entity.kind === 'player' ? entity.canonical_player_id : entity.canonical_team_id
}

function canonicalName(entity: SearchPlayerEntity | SearchTeamEntity): string {
  return entity.kind === 'player' ? entity.canonical_player_name : entity.canonical_team_name
}

function referenceFromSearch(entity: SearchPlayerEntity | SearchTeamEntity): EditorialEntityReference {
  return { kind: entity.kind, id: canonicalId(entity), name: canonicalName(entity) }
}
