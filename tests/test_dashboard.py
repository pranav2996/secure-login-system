from .conftest import login, register


def test_dashboard_requires_auth(client):
    response = client.get("/dashboard")
    assert response.status_code == 302
    assert "/login" in response.location


def test_logout_and_protected_route(client):
    register(client)
    login(client)
    assert client.get("/dashboard").status_code == 200
    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_protected_response_disables_caching(client):
    register(client)
    login(client)
    assert client.get("/dashboard").headers["Cache-Control"] == "no-store, max-age=0"
