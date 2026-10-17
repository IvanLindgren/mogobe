"""Shared administration entry point, routes and access controls."""

from fastapi.testclient import TestClient
from test_multiplayer import account, auth
from test_shops import setup_shop


def test_unified_admin_overview_and_account_routes(app):
    with TestClient(app) as client:
        ident, token, _ = setup_shop(client, app)
        headers = auth(token)
        summary = client.get("/api/admin/overview", headers=headers)
        assert summary.status_code == 200
        assert summary.json() == {
            "server_name": app.state.settings.server_name,
            "online": 0,
            "accounts": 1,
            "administrators": 1,
            "rooms": 50,
            "shops": 1,
            "items": 1,
        }
        assert client.get("/api/admin/me", headers=headers).json()["username"] == "ShopAdmin"
        directory = client.get("/api/admin/accounts", headers=headers).json()
        assert directory["accounts"][0]["id"] == ident
        assert (
            client.post(
                "/api/admin/accounts/ShopAdmin/balance", headers=headers, json={"coins": 123}
            ).status_code
            == 200
        )
        assert (
            client.get("/api/admin/accounts", headers=headers).json()["accounts"][0]["coins"] == 123
        )
        assert client.get("/api/admin/items", headers=headers).json()[0]["id"] == 1
        assert len(client.get("/api/admin/assets", headers=headers).json()) > 2000
        assert client.get("/api/admin/items/category-icons", headers=headers).status_code == 200
        # Compatibility routes share the same authorization/state.
        assert (
            client.get("/api/admin/shops/accounts", headers=headers).json()
            == client.get("/api/admin/accounts", headers=headers).json()
        )
        client.cookies.clear()
        login = client.post(
            "/api/admin/login", json={"username": "ShopAdmin", "password": "Pass1234"}
        )
        assert login.status_code == 200
        assert client.get("/api/admin/overview").status_code == 200
        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/admin/overview").status_code == 401


def test_unified_admin_rejects_non_admin_and_revoked_permissions(app):
    with TestClient(app) as client:
        _, token, _ = setup_shop(client, app)
        other, regular = account(client, "RegularAdmin", 7)
        for path in (
            "/api/admin/overview",
            "/api/admin/me",
            "/api/admin/accounts",
            "/api/admin/items",
            "/api/admin/assets",
            "/api/admin/shops",
        ):
            assert client.get(path, headers=auth(regular)).status_code == 403
        client.cookies.clear()
        assert (
            client.post(
                "/api/admin/login", json={"username": "RegularAdmin", "password": "Pass1234"}
            ).status_code
            == 403
        )
        assert (
            client.put(
                f"/api/admin/accounts/{other}/admin", headers=auth(token), json={"is_admin": True}
            ).status_code
            == 200
        )
        assert client.get("/api/admin/overview", headers=auth(regular)).status_code == 200
        assert (
            client.put(
                f"/api/admin/accounts/{other}/admin", headers=auth(token), json={"is_admin": False}
            ).status_code
            == 200
        )
        assert client.get("/api/admin/overview", headers=auth(regular)).status_code == 403


def test_shared_admin_page_and_documented_api(app):
    with TestClient(app) as client:
        page = client.get("/admin")
        assert page.status_code == 200
        assert "Могоби — администрирование" in page.text
        assert 'data-tab="overview"' in page.text
        assert client.get("/admin/").status_code == 200
        old = client.get("/admin/shops", follow_redirects=False)
        assert old.status_code == 307 and old.headers["location"] == "/admin"
        paths = client.get("/openapi.json").json()["paths"]
        assert "/api/admin/accounts" in paths and "/api/admin/items" in paths
        assert "/api/admin/shops/accounts" not in paths
        assert "/api/admin/shops/login" not in paths
