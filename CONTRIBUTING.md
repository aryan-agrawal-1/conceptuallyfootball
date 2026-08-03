# Contributing

## Issues

Search existing issues before opening a new one.

Use the Feature/Enhancement template for new functionality or any technical delivery work. Use the Bug template for incorrect, broken, or unexpected behaviour that needs fixed.

Every issue should have one primary type label:

- `enhancement`
- `bug`
- `documentation`
- `refactor`
- `security`

Add any relevant supporting labels, such as `help wanted` or `question`.

Don't include credentials, private data, local env files, or generated local reports in issues please.

## Branches

All changes must be made on a branch. Do not commit directly to `main`.

Branch names must use one of these prefixes:

- `feature/` for new functionality
- `fix/` for bug fixes
- `refactor/` for internal restructuring

Examples:

```text
feature/player-comparison-export
fix/mobile-filter-overflow
refactor/ingestion-validation
```

## Pull requests

All changes must be submitted through a PR into `main`.

Pull requests should:

- Explain what changed and why.
- Link any relevant issues.
- Confirm that the issue's acceptance criteria are met.
- Describe any testing and QA performed.
- Identify remaining limitations or blockers.

Again, don't include credentials, private data, local environment files, or generated local reports in pull requests.

## Testing and QA

Run the checks relevant to your change.

Backend changes should normally include:

```bash
cd backend
python manage.py check
python manage.py test
```

Frontend changes should normally include:

```bash
cd web
npm run lint
npm run build
```

Testing and QA notes must describe the exact expected end state, not only the commands that were run.

## Licensing

The project code is licensed under the GNU Affero General Public License, version 3 only.

There is no contributor license agreement. Contributors retain copyright in their contributions, and accepted contributions are made available under AGPLv3-only.
