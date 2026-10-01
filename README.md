# URL Shortener

A small Flask API that stores short-code mappings in SQLite and redirects short URLs to their original destinations.

## Setup

In PowerShell, from the project directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m flask --app app run
```

By default, the database is created at `instance/urls.db`. Set `DATABASE_URL` in `.env` to use another SQLAlchemy-supported database URL. Set `BASE_URL` if generated links should use a public host; otherwise, links use the current request host.

## API

Create a short URL:

```powershell
curl.exe -X POST http://127.0.0.1:5000/api/urls `
  -H "Content-Type: application/json" `
  -d '{"url":"https://example.com/page"}'
```

The response includes `code`, `short_url`, and the original `url`. Open the returned short URL to receive a `302` redirect. Invalid URLs return `400`; unknown codes return `404`.

Run tests with:

```powershell
python -m pytest -q
```