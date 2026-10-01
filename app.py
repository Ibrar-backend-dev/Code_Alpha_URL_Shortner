import os
import secrets
import string
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError


load_dotenv(Path(__file__).resolve().with_name(".env"))

db = SQLAlchemy()


class URLMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    short_code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    original_url = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


def generate_short_code():
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(6))


def upgrade_created_at_column():
    columns = inspect(db.engine).get_columns(URLMapping.__tablename__)
    if any(column["name"] == "created_at" for column in columns):
        return

    preparer = db.engine.dialect.identifier_preparer
    table_name = preparer.quote(URLMapping.__tablename__)
    column_name = preparer.quote("created_at")
    column_type = db.DateTime(timezone=True).compile(dialect=db.engine.dialect)
    with db.engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
        connection.execute(
            URLMapping.__table__.update()
            .where(URLMapping.created_at.is_(None))
            .values(created_at=datetime.now(timezone.utc))
        )


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL") or "sqlite:///urls.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        BASE_URL=os.getenv("BASE_URL", "").rstrip("/"),
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        upgrade_created_at_column()

    @app.post("/api/urls")
    def create_short_url():
        payload = request.get_json(silent=True)
        original_url = payload.get("url") if isinstance(payload, dict) else None
        if not isinstance(original_url, str) or not original_url.strip():
            return jsonify(error="A URL is required."), 400

        original_url = original_url.strip()
        try:
            parsed_url = urlsplit(original_url)
            valid_url = (
                parsed_url.scheme.lower() in {"http", "https"}
                and parsed_url.hostname is not None
                and not any(character.isspace() for character in original_url)
            )
        except ValueError:
            valid_url = False
        if not valid_url:
            return jsonify(error="URL must be a valid HTTP or HTTPS URL."), 400

        for _ in range(5):
            short_code = generate_short_code()
            if db.session.query(URLMapping.id).filter_by(short_code=short_code).first():
                continue

            mapping = URLMapping(short_code=short_code, original_url=original_url)
            db.session.add(mapping)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                continue

            base_url = app.config["BASE_URL"] or request.host_url.rstrip("/")
            return jsonify(
                code=short_code,
                short_url=f"{base_url}/{short_code}",
                url=original_url,
                created_at=mapping.created_at.isoformat(),
            ), 201

        return jsonify(error="Could not generate a unique short code. Try again."), 503

    @app.get("/api/urls")
    @app.get("/api/urls/<short_code>")
    def get_short_url(short_code=None):
        short_code = short_code or request.args.get("short_code")
        if not short_code:
            return jsonify(error="A short_code parameter is required."), 400

        mapping = URLMapping.query.filter_by(short_code=short_code).first()
        if mapping is None:
            return jsonify(error="Short URL not found."), 404

        base_url = app.config["BASE_URL"] or request.host_url.rstrip("/")
        return jsonify(
            code=mapping.short_code,
            short_url=f"{base_url}/{mapping.short_code}",
            url=mapping.original_url,
            created_at=mapping.created_at.isoformat(),
        )

    @app.get("/<short_code>")
    def redirect_short_url(short_code):
        mapping = URLMapping.query.filter_by(short_code=short_code).first()
        if mapping is None:
            return jsonify(error="Short URL not found."), 404
        return redirect(mapping.original_url, code=302)

    return app


app = create_app()