# Shared Contracts

Frozen interfaces for Worker A and Worker B integration.

## 1. Converter Interface

```python
from dataclasses import dataclass, field

@dataclass
class ConversionResult:
    links: list[str]          # ordered share URIs, one per line
    warnings: list[str]       # per-proxy warnings for malformed entries
    proxy_count: int          # number of successfully converted proxies

def convert_clash_yaml(raw: bytes) -> ConversionResult:
    """Convert Clash YAML bytes into share links.

    Raises:
        ConversionError: on malformed YAML or zero usable proxies.
    """
```

`ConversionError` is a typed exception with `message: str` and optional `detail: str`.

## 2. Provider CRUD

### Create / Update Request

```json
{
  "name": "string (1-128 chars, required)",
  "source_url": "string (http/https, required)",
  "schedule": {
    "type": "disabled|monthly|weekly|daily|interval",
    "day_of_month": "int 1-31 (monthly only)",
    "day_of_week": "int 0-6, 0=Sunday (weekly only)",
    "time_of_day": "HH:MM (monthly|weekly|daily)",
    "interval_hours": "int 1-168 (interval only)"
  }
}
```

### Provider Response

```json
{
  "id": "int",
  "name": "string",
  "source_url": "string (management API only, never in public responses)",
  "public_token": "string (opaque, 32-char hex)",
  "enabled": "bool",
  "schedule": { "type": "...", ... },
  "last_check_at": "ISO8601|null",
  "last_success_at": "ISO8601|null",
  "last_error": "string|null",
  "current_version": "int|null",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### Validation Errors

```json
{
  "error": "validation",
  "details": {
    "field_name": ["error message", ...]
  }
}
```

## 3. Update Run Event Schema

```json
{
  "run_id": "int",
  "provider_id": "int",
  "provider_name": "string",
  "trigger": "manual|scheduled|request",
  "stage": "querying|waiting|received|comparing|converting|storing|finished|failed",
  "status": "running|success|failure",
  "message": "string|null",
  "created_at": "ISO8601",
  "completed_at": "ISO8601|null"
}
```

SSE event format:
```
event: update
data: {"run_id": 1, "provider_id": 1, ...}
```

## 4. Public Endpoint Behavior

| Condition | Response |
|---|---|
| Unknown/invalid token | `404 Not Found` |
| No versions exist | `503 Service Unavailable` |
| Last success < 3 hours | Serve latest converted file, `200 OK` |
| Last success >= 3 hours, refresh succeeds | Serve new converted file, `200 OK` |
| Last success >= 3 hours, refresh fails, versions exist | Serve last good file + `Warning` + `X-Subscription-Stale: true`, `200 OK` |
| HEAD request | Same headers as GET, no body |

Response headers:
- `Content-Type: text/plain; charset=utf-8`
- `ETag: "<sha256-of-content>"`
- `Last-Modified: <rfc7231-date>`
- `Cache-Control: no-cache`

## 5. Schedule Types

| Type | Fields |
|---|---|
| `disabled` | none |
| `monthly` | `day_of_month` (1-31), `time_of_day` (HH:MM) |
| `weekly` | `day_of_week` (0-6), `time_of_day` (HH:MM) |
| `daily` | `time_of_day` (HH:MM) |
| `interval` | `interval_hours` (1-168) |

All times are in the configured timezone (default `Asia/Hong_Kong`).
