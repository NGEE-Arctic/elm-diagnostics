# PyPI Publishing Setup Guide

This document explains how to set up automated PyPI publishing for `elm-diagnostics` using GitHub Actions and PyPI Trusted Publishing.

## Overview

The `.github/workflows/publish.yml` workflow automatically publishes new releases to PyPI when a GitHub release is published. It uses **PyPI Trusted Publishing** (OpenID Connect authentication), which is more secure than API tokens and requires no secrets in GitHub.

## One-Time Setup Required

### 1. Configure PyPI Trusted Publishing

Before the first release, a PyPI account owner for the `elm-diagnostics` package must configure trusted publishing:

1. **Go to PyPI account settings:**
   - Visit https://pypi.org/manage/account/publishing/
   - Log in with a PyPI account that has ownership of the `elm-diagnostics` project

2. **Add a pending publisher:**
   - Click "Add a new pending publisher"
   - Fill in the form:
     - **PyPI Project Name:** `elm-diagnostics`
     - **Owner:** `NGEE-Arctic`
     - **Repository name:** `elm-diagnostics`
     - **Workflow filename:** `publish.yml`
     - **Environment name:** `pypi` (optional but recommended if using deployment environment)

3. **Save:**
   - Click "Add"
   - The publisher will show as "pending" until the first successful publish
   - After the first successful release, it will activate automatically

**Note:** If the package doesn't exist on PyPI yet, you can add a "pending publisher" before the first upload. PyPI will create the project automatically on first publish.

### 2. (Optional) Configure GitHub Deployment Environment

For additional safety and control, you can create a deployment environment in GitHub:

1. **Go to repository settings:**
   - Navigate to https://github.com/NGEE-Arctic/elm-diagnostics/settings/environments
   - Click "New environment"

2. **Create `pypi` environment:**
   - Name: `pypi`
   - Add protection rules:
     - ✅ **Required reviewers:** Add team members who should approve releases
     - ✅ **Wait timer:** Optional delay before deployment
     - ✅ **Deployment branches:** Restrict to specific branches (e.g., `main`)

3. **Enable in workflow:**
   - Uncomment the `environment:` section in `.github/workflows/publish.yml`:
     ```yaml
     environment:
       name: pypi
     ```

## How to Publish a New Release

### 1. Update Version

Before creating a release, update the version in `pyproject.toml`:

```bash
# Edit pyproject.toml and update the version field
version = "0.2.0"  # Or whatever the new version is
```

Commit and push this change:

```bash
git add pyproject.toml
git commit -m "Bump version to 0.2.0"
git push origin main
```

### 2. Create a GitHub Release

1. **Go to the releases page:**
   - Visit https://github.com/NGEE-Arctic/elm-diagnostics/releases/new

2. **Create a new release:**
   - **Tag:** `v0.2.0` (must match the version in `pyproject.toml`)
   - **Title:** `v0.2.0` or "Release 0.2.0"
   - **Description:** Document what's new, changed, or fixed
   - **Pre-release:** Check this box for alpha/beta/rc versions
   - Click "Publish release"

3. **Workflow triggers automatically:**
   - The publish workflow starts immediately
   - Monitor progress at: https://github.com/NGEE-Arctic/elm-diagnostics/actions/workflows/publish.yml

### 3. Verify Publication

After the workflow completes successfully:

1. **Check PyPI:**
   - Visit https://pypi.org/project/elm-diagnostics/
   - Verify the new version appears

2. **Test installation:**
   ```bash
   pip install --upgrade elm-diagnostics
   python -c "import elm_diagnostics; print(elm_diagnostics.__version__)"
   ```

## Workflow Jobs

The publish workflow has two jobs:

### 1. Build Job
- Checks out the code
- Sets up Python 3.12
- Installs `build` and `twine`
- Builds wheel (`.whl`) and source distribution (`.tar.gz`)
- Validates packages with `twine check`
- Uploads build artifacts

### 2. Publish Job
- Downloads build artifacts
- Publishes to PyPI using trusted publishing (OIDC)
- No secrets required (authentication via OpenID Connect)

## Troubleshooting

### "Trusted publisher already configured for another repository"
- This means the PyPI project is already linked to a different GitHub repository
- The PyPI project owner needs to update the trusted publisher configuration

### "Trusted publisher not configured"
- Complete the one-time setup steps above
- Ensure the repository owner, name, and workflow filename match exactly

### "Environment 'pypi' not found"
- Either create the `pypi` environment in GitHub repository settings, OR
- Comment out the `environment:` section in the workflow file

### Build fails
- Ensure `pyproject.toml` is valid
- Run locally: `python -m build` and `twine check dist/*`
- Check that required files are included in the package

### Version mismatch
- Ensure the git tag matches the version in `pyproject.toml`
- Example: tag `v0.2.0` should match `version = "0.2.0"` in pyproject.toml

## Security Considerations

**Why Trusted Publishing is safer than API tokens:**
- ✅ No long-lived secrets stored in GitHub
- ✅ Automatic credential rotation
- ✅ Scoped to specific repository and workflow
- ✅ Audit trail via OpenID Connect
- ✅ Cannot be leaked or stolen from GitHub repository settings

**Additional protection with deployment environments:**
- Manual approval required before publishing
- Restrict which branches can trigger releases
- Audit log of who approved each release

## References

- [PyPI Trusted Publishers Documentation](https://docs.pypi.org/trusted-publishers/)
- [GitHub Actions OIDC Documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [Python Packaging User Guide](https://packaging.python.org/en/latest/guides/publishing-package-distribution-releases-using-github-actions-ci-cd-workflows/)
