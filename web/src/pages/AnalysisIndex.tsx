import { useQuery } from '@tanstack/react-query'
import { ArrowUpRight, BookOpen, Search, SlidersHorizontal, UserRound, X } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { ARTICLE_TOPICS } from '../lib/articleTopics'
import { listPublishedArticles, type PublicArticleFilters, type PublicArticleSummary } from '../lib/editorial'
import { useSeoMeta } from '../lib/seo'
import { fetchStaffSession } from '../lib/staffAuth'


export function AnalysisIndex() {
  const [searchParams, setSearchParams] = useSearchParams()
  const filters = filtersFromParams(searchParams)
  const queryKey = searchParams.toString()
  const articlesQuery = useQuery({
    queryKey: ['public-analysis', queryKey],
    queryFn: () => listPublishedArticles(filters),
    staleTime: 60_000,
  })
  const sessionQuery = useQuery({
    queryKey: ['staff-session'],
    queryFn: fetchStaffSession,
    staleTime: 30_000,
    retry: false,
  })
  const data = articlesQuery.data
  const hasFilters = [...searchParams.keys()].some(key => PUBLIC_FILTER_KEYS.has(key))

  useSeoMeta({
    title: 'Football Analysis & Ideas | Conceptually Football',
    description: 'Read original football analysis on tactics, players, teams and data — connected directly to Conceptually Football profiles and visual tools.',
    canonicalPath: '/articles',
  })

  function updateFilter(key: string, value: string) {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      if (value) next.set(key, value)
      else next.delete(key)
      if (key !== 'page') next.delete('page')
      return next
    })
  }

  function toggleTopic(topic: string) {
    const nextTopics = filters.topics?.includes(topic)
      ? filters.topics.filter(value => value !== topic)
      : [...(filters.topics ?? []), topic]
    updateFilter('article_topics', nextTopics.join(','))
  }

  function clearFilters() {
    setSearchParams(previous => {
      const next = new URLSearchParams(previous)
      for (const key of PUBLIC_FILTER_KEYS) next.delete(key)
      return next
    })
  }

  const selectedPlayer = filters.playerId ?? ''
  const selectedTeam = filters.teamId ?? ''
  const canOpenDesk = Boolean(sessionQuery.data?.user?.can_access_editorial)

  return (
    <div className="min-h-svh overflow-hidden bg-mat">
      <header className="relative border-b border-line px-5 py-10 sm:px-8 sm:py-12 lg:px-12 lg:py-14">
        <div className="pointer-events-none absolute inset-0 opacity-50 [background-image:linear-gradient(rgba(74,158,245,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(74,158,245,0.08)_1px,transparent_1px)] [background-size:44px_44px] [mask-image:linear-gradient(to_bottom,black,transparent)]" />
        <div className="relative mx-auto max-w-[1380px]">
          <div className="max-w-5xl">
            <p className="font-mono text-[9px] uppercase tracking-[0.28em] text-electric">Analysis / ideas / evidence</p>
            <h1 className="mt-4 text-[clamp(2.5rem,5vw,4.5rem)] font-black leading-[0.92] tracking-[-0.06em] text-ink">
              See the game <span className="text-electric">between the numbers.</span>
            </h1>
            <p className="mt-5 max-w-2xl border-l border-electric/40 pl-5 text-sm leading-7 text-ink-dim">
              Original football writing connected to the players, teams and visual evidence behind every argument.
            </p>
            {canOpenDesk ? <Link to="/analysis" className="mt-6 inline-flex items-center gap-2 border border-electric/45 px-3 py-2 font-mono text-[8px] uppercase tracking-[0.16em] text-electric transition-colors hover:bg-electric hover:text-mat"><UserRound className="size-3.5" /> Open analysis desk</Link> : null}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1380px] px-5 py-10 sm:px-8 lg:px-12 lg:py-14">
        <section aria-labelledby="analysis-filters-heading" className="border-b border-line pb-6">
          <div className="mb-4 flex items-center justify-between gap-4">
            <h2 id="analysis-filters-heading" className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.18em] text-ink-muted"><SlidersHorizontal className="size-3.5 text-electric" /> Find a line of thought</h2>
            {hasFilters ? <button type="button" onClick={clearFilters} className="inline-flex items-center gap-1.5 font-mono text-[8px] uppercase tracking-[0.14em] text-ink-muted hover:text-electric"><X className="size-3" /> Clear filters</button> : null}
          </div>
          <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
            <label className="relative md:col-span-2">
              <span className="sr-only">Search analysis</span>
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-electric" />
              <input value={filters.q ?? ''} onChange={event => updateFilter('q', event.target.value)} placeholder="Search titles, ideas, writers…" className="h-11 w-full border border-line-bright bg-panel/50 pl-10 pr-3 text-xs text-ink placeholder:text-ink-muted focus:border-electric focus:outline-none" />
            </label>
            <FilterSelect label="Author" value={filters.author ?? ''} onChange={value => updateFilter('author', value)} options={data?.facets.authors.map(author => ({ value: String(author.id), label: author.name })) ?? []} />
            <FilterSelect label="Player" value={selectedPlayer} onChange={value => updateFilter('player_id', value)} options={data?.facets.players.map(player => ({ value: String(player.id), label: player.name })) ?? []} />
            <FilterSelect label="Team" value={selectedTeam} onChange={value => updateFilter('team_id', value)} options={data?.facets.teams.map(team => ({ value: String(team.id), label: team.name })) ?? []} />
            <FilterSelect label="Relationship" value={filters.relationship ?? ''} onChange={value => updateFilter('relationship', value)} disabled={!selectedPlayer && !selectedTeam} options={[{ value: 'subject', label: 'Primary subject' }, { value: 'reference', label: 'Referenced only' }]} />
            <FilterSelect label="Competition" value={filters.competition ?? ''} onChange={value => updateFilter('article_competition', value)} options={data?.facets.competitions.map(value => ({ value, label: value })) ?? []} />
            <FilterSelect label="Season" value={filters.season ?? ''} onChange={value => updateFilter('article_season', value)} options={data?.facets.seasons.map(value => ({ value, label: value })) ?? []} />
          </div>
          <fieldset className="mt-3">
            <legend className="mb-2 font-mono text-[8px] uppercase tracking-[0.15em] text-ink-muted">Topics</legend>
            <div className="flex flex-wrap gap-2">
              {ARTICLE_TOPICS.map(topic => {
                const selected = filters.topics?.includes(topic) ?? false
                return <button key={topic} type="button" aria-pressed={selected} onClick={() => toggleTopic(topic)} className={`border px-3 py-2 font-mono text-[8px] uppercase tracking-[0.12em] transition-colors ${selected ? 'border-electric bg-electric/15 text-electric' : 'border-line-bright text-ink-muted hover:border-electric hover:text-ink'}`}>{topic}</button>
              })}
            </div>
          </fieldset>
          <p className="mt-3 max-w-3xl text-[10px] leading-5 text-ink-muted"><span className="font-mono uppercase tracking-[0.12em] text-electric">Competition and season</span> describe the frozen data context used by an article’s published visual blocks. Articles without that visual context remain available under the unfiltered view.</p>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:max-w-xl">
            <DateFilter label="Published after" value={filters.from ?? ''} onChange={value => updateFilter('from', value)} />
            <DateFilter label="Published before" value={filters.to ?? ''} onChange={value => updateFilter('to', value)} />
          </div>
        </section>

        <div className="mt-9 flex items-end justify-between gap-4">
          <div>
            <p className="font-mono text-[8px] uppercase tracking-[0.2em] text-electric">Published analysis</p>
            <h2 className="mt-2 text-2xl font-black tracking-[-0.04em] text-ink sm:text-3xl">{data ? `${data.pagination.total} ${data.pagination.total === 1 ? 'article' : 'articles'}` : 'Reading the archive…'}</h2>
          </div>
        </div>

        {articlesQuery.isLoading ? <AnalysisMessage>Loading the archive…</AnalysisMessage> : null}
        {articlesQuery.isError ? <AnalysisMessage error>The analysis archive could not be loaded.</AnalysisMessage> : null}
        {data && !data.articles.length ? <AnalysisMessage>No published analysis matches these filters.</AnalysisMessage> : null}
        {data?.articles.length ? (
          <div className="mt-7 divide-y divide-line border-y border-line">
            {data.articles.map(article => <ArticleCard key={article.id} article={article} />)}
          </div>
        ) : null}

        {data && data.pagination.pages > 1 ? (
          <nav className="mt-9 flex items-center justify-center gap-3" aria-label="Analysis pagination">
            <PageButton disabled={data.pagination.page <= 1} onClick={() => updateFilter('page', String(data.pagination.page - 1))}>Previous</PageButton>
            <span className="font-mono text-[9px] uppercase tracking-[0.15em] text-ink-muted">Page {data.pagination.page} / {data.pagination.pages}</span>
            <PageButton disabled={data.pagination.page >= data.pagination.pages} onClick={() => updateFilter('page', String(data.pagination.page + 1))}>Next</PageButton>
          </nav>
        ) : null}
      </main>
    </div>
  )
}

const PUBLIC_FILTER_KEYS = new Set(['q', 'article_topics', 'author', 'article_competition', 'article_season', 'player_id', 'team_id', 'relationship', 'from', 'to', 'page'])

function filtersFromParams(params: URLSearchParams): PublicArticleFilters {
  const relationship = params.get('relationship')
  return {
    q: params.get('q') ?? '',
    topics: params.get('article_topics')?.split(',').filter(Boolean) ?? [],
    author: params.get('author') ?? '',
    competition: params.get('article_competition') ?? '',
    season: params.get('article_season') ?? '',
    playerId: params.get('player_id') ?? '',
    teamId: params.get('team_id') ?? '',
    relationship: relationship === 'subject' || relationship === 'reference' ? relationship : '',
    from: params.get('from') ?? '',
    to: params.get('to') ?? '',
    page: Number(params.get('page')) || 1,
  }
}

function ArticleCard({ article }: { article: PublicArticleSummary }) {
  return (
    <article className="group relative py-7 transition-colors sm:py-9">
      <div className="max-w-4xl">
        <div className="flex flex-wrap items-center gap-2 font-mono text-[8px] uppercase tracking-[0.14em] text-ink-muted">
          <time dateTime={article.published_at}>{formatDate(article.published_at)}</time>
          <span aria-hidden="true">/</span>
          <span>{article.reading_minutes} min read</span>
        </div>
        <h3 className="mt-4 text-2xl font-black leading-[1.05] tracking-[-0.04em] text-ink transition-colors group-hover:text-electric sm:text-3xl">
          <Link to={article.canonical_path} className="after:absolute after:inset-0">{article.title}</Link>
        </h3>
        {article.subtitle ? <p className="mt-3 max-w-3xl text-sm leading-6 text-ink-dim">{article.subtitle}</p> : null}
        <p className="mt-5 font-mono text-[8px] uppercase tracking-[0.15em] text-electric">By {article.author.display_name}</p>
        {article.topics.length ? <div className="mt-3 flex flex-wrap gap-1.5">{article.topics.map(topic => <span key={topic} className="border border-line px-2 py-1 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">{topic}</span>)}</div> : null}
        <ArrowUpRight className="mt-5 size-5 text-electric transition-transform group-hover:translate-x-1 group-hover:-translate-y-1" />
      </div>
    </article>
  )
}

function FilterSelect({ label, value, options, onChange, disabled = false }: { label: string; value: string; options: { value: string; label: string }[]; onChange: (value: string) => void; disabled?: boolean }) {
  return <label><span className="sr-only">{label}</span><select aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)} className="h-11 w-full border border-line-bright bg-panel/50 px-3 font-mono text-[9px] uppercase tracking-[0.1em] text-ink-dim focus:border-electric focus:outline-none disabled:opacity-40"><option value="">{label}</option>{options.map(option => <option key={option.value} value={option.value}>{option.label}</option>)}</select></label>
}

function DateFilter({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <label className="flex h-10 items-center gap-3 border border-line bg-panel/30 px-3"><span className="shrink-0 font-mono text-[7px] uppercase tracking-[0.12em] text-ink-muted">{label}</span><input type="date" value={value} onChange={event => onChange(event.target.value)} className="min-w-0 flex-1 bg-transparent text-right font-mono text-[9px] text-ink-dim focus:outline-none" /></label>
}

function PageButton({ children, disabled, onClick }: { children: string; disabled: boolean; onClick: () => void }) {
  return <button type="button" disabled={disabled} onClick={onClick} className="border border-line-bright px-4 py-2 font-mono text-[8px] uppercase tracking-[0.14em] text-ink-dim hover:border-electric hover:text-electric disabled:pointer-events-none disabled:opacity-30">{children}</button>
}

function AnalysisMessage({ children, error = false }: { children: string; error?: boolean }) {
  return <div className={`mt-7 grid min-h-52 place-items-center border border-dashed px-6 text-center text-xs ${error ? 'border-ember/40 text-ember' : 'border-line text-ink-muted'}`}><span><BookOpen className="mx-auto mb-3 size-5" />{children}</span></div>
}

function formatDate(value: string): string {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }).format(new Date(value))
}
