from pathlib import Path

from app import main


def test_static_asset_version_changes_when_first_party_asset_changes(tmp_path, monkeypatch):
    asset_names = (
        "app.css",
        "app.js",
        "prometheus-connections.js",
        "backfill-jobs.js",
    )
    for name in asset_names:
        (tmp_path / name).write_text("initial:" + name, encoding="utf-8")

    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    first = main._static_asset_version()

    (tmp_path / "app.js").write_text("updated app bundle", encoding="utf-8")
    second = main._static_asset_version()

    assert first != second
    assert len(first) == 16
    assert len(second) == 16


def test_dashboard_html_uses_asset_version_and_requires_revalidation(tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text(
        '<link rel="stylesheet" href="/static/app.css?v=__ASSET_VERSION__">'
        '<script src="/static/app.js?v=__ASSET_VERSION__"></script>',
        encoding="utf-8",
    )
    for name in ("app.css", "app.js", "prometheus-connections.js", "backfill-jobs.js"):
        (tmp_path / name).write_text(name, encoding="utf-8")

    monkeypatch.setattr(main, "STATIC_DIR", tmp_path)
    response = main.dashboard_index()

    assert response.status_code == 200
    assert "__ASSET_VERSION__" not in response.body.decode("utf-8")
    assert b"/static/app.css?v=" in response.body
    assert b"/static/app.js?v=" in response.body
    assert response.headers["cache-control"] == "no-cache, must-revalidate"


def test_dashboard_root_route_is_registered_to_dashboard_index():
    root_routes = [
        route for route in main.app.routes
        if getattr(route, "path", None) == "/" and "GET" in getattr(route, "methods", set())
    ]

    assert len(root_routes) == 1
    assert root_routes[0].endpoint is main.dashboard_index
