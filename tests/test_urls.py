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
    assert response.json == {
        "code": "abc123",
        "short_url": "https://sho.rt/abc123",
        "url": "https://example.com/page",
    }
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