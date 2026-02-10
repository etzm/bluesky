# Bluesky Social Graph Explorer

Fetch and analyze the social graph (followers, follows, mutuals) for any Bluesky / AT Protocol account.

## Features

- Fetch **followers** and **follows** for any public Bluesky account
- Compute **mutuals**, **fans**, and **not-following-back** lists
- Works **without authentication** for public data
- Export to **JSON** or **CSV**
- Respects API rate limits with built-in pagination and delays

## Setup

```bash
pip install -r requirements.txt
```

## Usage

### Public access (no auth needed)

```bash
python bluesky_social_graph.py --actor alice.bsky.social
```

### Authenticated access

Create an [App Password](https://bsky.app/settings/app-passwords) in Bluesky settings, then:

```bash
python bluesky_social_graph.py \
  --actor alice.bsky.social \
  --handle your.bsky.social \
  --password your-app-password
```

### Export to JSON

```bash
python bluesky_social_graph.py --actor alice.bsky.social --export json --output graph.json
```

### Export to CSV

```bash
python bluesky_social_graph.py --actor alice.bsky.social --export csv --output graph.csv
```

## API Endpoints Used

| Endpoint | Auth Required | Description |
|---|---|---|
| `app.bsky.actor.getProfile` | No | Profile metadata |
| `app.bsky.graph.getFollowers` | No | List of followers |
| `app.bsky.graph.getFollows` | No | List of follows |

## Rate Limits

- 3,000 requests / 5 minutes (per IP)
- Built-in 0.4s delay between paginated requests
- Accounts with 10k followers take ~40 seconds to fully fetch

## License

MIT
