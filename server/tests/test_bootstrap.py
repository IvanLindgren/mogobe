from fastapi.testclient import TestClient
from test_multiplayer import account

from src.config import Settings
from src.main import create_app


def server_with_defaults(app):
    return create_app(
        Settings(database_url=app.state.settings.database_url, bootstrap_defaults=True)
    )


def test_first_start_creates_default_admin_and_complete_private_shop(app):
    application = server_with_defaults(app)
    with TestClient(application) as client:
        login = client.post("/api/admin/login", json={"username": "admin", "password": "admin"})
        assert login.status_code == 200
        overview = client.get("/api/admin/overview").json()
        assert overview["accounts"] == overview["administrators"] == 1
        assert overview["shops"] == 17
        assert overview["items"] == 2456
        catalog = client.get("/api/shops/admin1").json()
        assert catalog["admin_only"] and len(catalog["items"]) == 1958
        assert all(item["price"] == 0 for item in catalog["items"])
        shop = client.get("/api/admin/shops/admin1/catalog").json()
        assert all(offer["experience"] == 0 for offer in shop["offers"])
        offer = next(o for o in shop["offers"] if o["item_id"] == 100)
        body = {k: v for k, v in offer.items() if k not in ("id", "shop_id")}
        body["price"] = 17
        assert client.put("/api/admin/shops/admin1/offers/100", json=body).status_code == 200
    # A repeated startup preserves the single account, sessions and edited prices.
    with TestClient(server_with_defaults(app)) as client:
        assert (
            client.post(
                "/api/admin/login", json={"username": "admin", "password": "admin"}
            ).status_code
            == 200
        )
        assert client.get("/api/admin/overview").json()["accounts"] == 1
        data = client.get("/api/admin/shops/admin1/catalog").json()
        assert len(data["offers"]) == 1958
        assert next(o for o in data["offers"] if o["item_id"] == 100)["price"] == 17


def test_startup_does_not_reset_existing_admin_name_password_or_role(app):
    with TestClient(app) as client:
        account(client, "Admin", 7)
    with TestClient(server_with_defaults(app)) as client:
        assert (
            client.post(
                "/api/admin/login", json={"username": "admin", "password": "admin"}
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/auth/login", json={"username": "Admin", "password": "Pass1234"}
            ).status_code
            == 200
        )
        assert client.get("/api/admin/me").status_code == 403
        assert client.get("/api/auth/me").json()["username"] == "Admin"
