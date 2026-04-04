# snc – Sierra Nevada Construction CLI

Equipment tracking CLI for Sierra Nevada Construction.

## Install

```bash
pip install -e .
```

## Configuration

Set environment variables before use:

```bash
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_KEY="your-service-role-key"
```

Never hardcode credentials in code or scripts.

## Usage

```bash
snc --help
snc business-unit list
snc equipment list --business-unit <uuid>
snc equipment create --business-unit <uuid> --code EX-001 --make CAT --model 320 --year 2023
snc telemetry update --gps-device-tag TAG-01 --hour-meter 1500
```

All commands output JSON by default. Add `--human` for readable output.
