def test_application_uses_testing_mode(app):
    assert app.config["TESTING"] is True


def test_health_endpoint_works_without_live_server(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.get_json() == {
        "ok": True,
        "service": "OFS spike API",
    }