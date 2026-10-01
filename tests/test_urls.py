import sqlite3
from datetime import datetime, timezone

import app as url_shortener
from app import URLMapping, create_app, db


def make_app():
    return create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite://",
            "BASE_URL": "https://sho.rt",
        }
    )


def test_create_url_returns_short_link_and_persists_mapping(monkeypatch):
    app = make_app()
    monkeypatch.setattr(url_shortener, "generate_short_code", lambda: "abc123")

    with app.test_client() as client:
        response = client.post("/api/urls", json={"url": "https://example.com/page"})

    assert response.status_code == 201
    assert response.json["code"] == "abc123"
    assert response.json["short_url"] == "https://sho.rt/abc123"
    assert response.json["url"] == "https://example.com/page"
    created_at = datetime.fromisoformat(response.json["created_at"])
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    assert abs((datetime.now(timezone.utc) - created_at).total_seconds()) < 5
    with app.app_context():
        mapping = URLMapping.query.filter_by(short_code="abc123").one()
        assert mapping.original_url == "https://example.com/page"
        db.drop_all()


def test_create_url_rejects_missing_and_unsupported_urls():
    app = make_app()

    with app.test_client() as client:
        missing = client.post("/api/urls", json={})
        unsupported = client.post("/api/urls", json={"url": "javascript:alert(1)"})

    assert missing.status_code == 400
    assert unsupported.status_code == 400
    with app.app_context():
        db.drop_all()


def test_short_code_redirects_and_unknown_code_returns_404(monkeypatch):
    app = make_app()
    monkeypatch.setattr(url_shortener, "generate_short_code", lambda: "abc123")

    with app.test_client() as client:
        client.post("/api/urls", json={"url": "https://example.com"})
        redirect_response = client.get("/abc123")
        missing_response = client.get("/missing")

    assert redirect_response.status_code == 302
    assert redirect_response.headers["Location"] == "https://example.com"
    assert missing_response.status_code == 404
    with app.app_context():
        db.drop_all()


def test_short_code_lookup_returns_json_and_accepts_code_in_path(monkeypatch):
    app = make_app()
    monkeypatch.setattr(url_shortener, "generate_short_code", lambda: "abc123")

    with app.test_client() as client:
        client.post("/api/urls", json={"url": "https://example.com/page"})
        response = client.get("/api/urls/abc123")
        missing_response = client.get("/api/urls/unknown")

    assert response.status_code == 200
    assert response.is_json
    assert response.json["code"] == "abc123"
    assert response.json["short_url"] == "https://sho.rt/abc123"
    assert response.json["url"] == "https://example.com/page"
    assert response.json["created_at"]
    assert missing_response.status_code == 404
    with app.app_context():
        db.drop_all()


def test_code_collision_retries_with_another_code(monkeypatch):
    app = make_app()
    generated_codes = iter(["taken1", "fresh1"])
    monkeypatch.setattr(url_shortener, "generate_short_code", lambda: next(generated_codes))

    with app.test_client() as client:
        client.post("/api/urls", json={"url": "https://first.example"})
        response = client.post("/api/urls", json={"url": "https://second.example"})

    assert response.status_code == 201
    assert response.json["code"] == "fresh1"
    with app.app_context():
        db.drop_all()


def test_create_app_adds_creation_time_to_an_existing_sqlite_database(tmp_path):
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE url_mapping ("
            "id INTEGER PRIMARY KEY, short_code VARCHAR(16) NOT NULL UNIQUE, "
            "original_url TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO url_mapping (short_code, original_url) VALUES (?, ?)",
            ("old123", "https://example.com/old"),
        )

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )

    with app.app_context():
        mapping = URLMapping.query.filter_by(short_code="old123").one()
        assert mapping.created_at is not None