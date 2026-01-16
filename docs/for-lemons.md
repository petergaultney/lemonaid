# Lemonaid for Lemons

Programmatic access to lemonaid for LLMs and other automated tools.

## Inbox Commands

### List notifications

```bash
# List all unread notifications as JSON
lemonaid inbox list --json
```

Output:
```json
[
  {
    "id": 42,
    "channel": "claude:abc123",
    "title": "Permission needed in my-project",
    "message": null,
    "metadata": {"cwd": "/path/to/project", "tty": "/dev/ttys001"},
    "status": "unread",
    "created_at": 1768578211.645825,
    "read_at": null
  }
]
```

### Get a specific notification

```bash
lemonaid inbox get 42 --json
```

Returns a single notification object, or `null` if not found.

### Mark as read

```bash
lemonaid inbox read 42
```

### Add a notification

```bash
lemonaid inbox add "channel-name" "Title" -m "Optional message" --metadata '{"key": "value"}'
```

## Notification Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Unique identifier |
| `channel` | string | Source identifier (e.g., `claude:<session_id>`) |
| `title` | string | Short description |
| `message` | string? | Optional longer message |
| `metadata` | object | Arbitrary JSON metadata |
| `status` | string | `unread` or `read` |
| `created_at` | float | Unix timestamp |
| `read_at` | float? | Unix timestamp when marked read |
