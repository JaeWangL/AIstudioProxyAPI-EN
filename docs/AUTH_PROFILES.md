# Authentication Profiles Guide

This project persists browser auth state as JSON files so headless runs can reuse sessions.

## Directories

- `auth_profiles/saved/` — stored profiles
- `auth_profiles/active/` — active profiles (used by some workflows)
- `auth_profiles/key.txt` — optional API keys for HTTP auth

## Create a new profile

```bash
poetry run python launch_camoufox.py --debug --auto-save-auth --save-auth-as my_account
```

This opens a visible browser, lets you login, and saves auth data.

## Use a profile in headless mode

```bash
poetry run python launch_camoufox.py --headless --active-auth-json auth_profiles/saved/my_account.json
```

## API key file behavior (`auth_profiles/key.txt`)

- One key per line
- Empty file = API key checks disabled
- Non-empty file = `/v1/*` endpoints require key header

Example file:

```text
my-secret-key-1
my-secret-key-2
```

## Rotation and quota-related settings

Relevant `.env` options:

- `AUTO_ROTATE_AUTH_PROFILE=true`
- `AUTO_AUTH_ROTATION_ON_STARTUP=false`
- `QUOTA_SOFT_LIMIT=850000`
- `QUOTA_HARD_LIMIT=950000`

These settings help rotate profiles when usage approaches quota thresholds.

## Security recommendations

- Never commit `auth_profiles/saved/*.json` to public repositories
- Keep `auth_profiles/key.txt` private
- Rotate API keys periodically
