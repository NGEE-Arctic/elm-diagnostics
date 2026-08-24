# RST API Documentation for elm-diagnostics

---
type: analysis
status: draft
created: 2026-05-12
language: python
environment: elm-diagnostics
test_strategy: doctest
---

## Summary

Develop RST documentation for existing features that document the API of this package.

## Background

README has usage examples but no API reference. Users need detailed class/function docs for advanced use. Current docstrings follow NumPy style but aren't rendered or discoverable outside source code.

## Scope

Deliverables:

1. **Sphinx setup** in `docs/` directory
   - `conf.py` configuration
   - `index.rst` landing page
   - API reference structure

2. **Full API coverage** for all `elm_diagnostics.*` modules:
   - `elm_diagnostics.io` (Run, Comparison, derived variables)
   - `elm_diagnostics.balances` (WaterBalance, CarbonBalance, EnergyBalance, base classes)
   - `elm_diagnostics.plots` (all plot functions, helpers)
   - `elm_diagnostics.time` (integration, calendars)
   - `elm_diagnostics.config` (schema, defaults)
   - `elm_diagnostics.report` (Report class, build logic)
   - `elm_diagnostics.cli` (CLI commands)

3. **GitHub Pages deployment**
   - GitHub Actions workflow (`.github/workflows/docs.yml`)
   - Build on push to main
   - Deploy to `gh-pages` branch
   - Accessible at `https://rfiorella.github.io/elm-diagnostics/`

4. **Docstring completeness**
   - Verify all public classes/functions have NumPy-style docstrings
   - Add missing docstrings where needed
   - Examples in docstrings (for doctest)

## Success Criteria

- [ ] `sphinx-build` passes without warnings
- [ ] All public classes/functions have docstrings
- [ ] Examples in docstrings are runnable (pass doctest)
- [ ] GitHub Pages shows rendered documentation at `https://rfiorella.github.io/elm-diagnostics/`
- [ ] API reference covers all modules listed in Scope
- [ ] Landing page has navigation to tutorials (link to existing markdown docs)

## Test Strategy

**Doctest validation:**
- Run `sphinx-build -b doctest docs/ docs/_build/doctest`
- All examples in docstrings must execute successfully
- Use `# doctest: +SKIP` for examples requiring external data

**Build validation:**
- CI checks `sphinx-build` exits 0
- No warnings in build output
- Generated HTML includes all expected modules

**Manual checks:**
- Navigation works (sidebar, TOC)
- Code blocks render correctly
- Links to GitHub source correct

## Dependencies

**Python packages** (add to `pyproject.toml` dev deps):
- `sphinx>=7.0`
- `sphinx-autodoc-typehints`
- `sphinx-rtd-theme` (Read the Docs theme)
- `myst-parser` (for markdown integration if linking tutorials)

**Existing assets:**
- NumPy-style docstrings already present in codebase
- Markdown tutorials in `docs/*.md` (can link from Sphinx landing)

**Constraints:**
- Preserve existing markdown docs (don't convert, just link)
- Build must work in CI (GitHub Actions ubuntu-latest)
- No manual deployment step (automated via Actions)

## Output Artifacts

**Repository structure:**
```
docs/
├── conf.py                 # Sphinx configuration
├── index.rst              # Landing page
├── api/
│   ├── io.rst            # elm_diagnostics.io API
│   ├── balances.rst      # Balance classes
│   ├── plots.rst         # Plotting functions
│   ├── time.rst          # Time utilities
│   ├── config.rst        # Configuration
│   ├── report.rst        # Report generation
│   └── cli.rst           # CLI reference
├── tutorials.rst          # Links to existing markdown tutorials
└── Makefile               # Sphinx build commands

.github/workflows/docs.yml  # GitHub Actions for deployment
```

**Hosted documentation:**
- URL: `https://rfiorella.github.io/elm-diagnostics/`
- Updated automatically on push to `main`
- Versioned (show current version from `pyproject.toml`)

**Local build:**
```bash
cd docs
make html              # Build HTML
make doctest           # Run doctest
open _build/html/index.html
```

## Implementation Notes

**Sphinx extensions to enable:**
- `sphinx.ext.autodoc` (extract from docstrings)
- `sphinx.ext.napoleon` (NumPy docstring style)
- `sphinx.ext.viewcode` (link to source)
- `sphinx.ext.doctest` (test examples)
- `sphinx.ext.intersphinx` (link to xarray, numpy docs)
- `sphinx_autodoc_typehints` (type hint rendering)

**GitHub Actions workflow key steps:**
1. Checkout repo
2. Install package with `[dev]` deps
3. `sphinx-build -b html docs/ docs/_build/html`
4. Deploy `docs/_build/html/` to `gh-pages` branch (use `peaceiris/actions-gh-pages`)

**Integration with existing docs:**
- Keep markdown tutorials in `docs/*.md`
- Link from Sphinx `tutorials.rst` to GitHub raw/rendered markdown
- Or: convert markdown to RST if full integration desired (later phase)

## Risks / Open Questions

- **Docstring coverage unknown:** May need to add/improve docstrings for complete API reference. Plan to audit during implementation.
- **GitHub Pages not enabled:** Repo settings must enable Pages from `gh-pages` branch (one-time manual step).
- **Large API surface:** `elm_diagnostics` has ~20 modules. Prioritize user-facing API (`Run`, `Balance` classes, plot functions) first if time-constrained.

## Follow-On Work (Out of Scope)

- Convert markdown tutorials to RST for unified navigation
- Add "Getting Started" quick reference in Sphinx
- Version-switching (multiple doc versions for releases)
- Search functionality (enabled by default in RTD theme)
- Jupyter notebook examples embedded in docs
