from conftest import requires_mysql


def test_application_uses_testing_mode(app):
    assert app.config["TESTING"] is True


@requires_mysql
def test_health_reports_the_database(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["ok"] is True
    assert body["database"] == "up"


def test_unknown_paths_answer_in_json(client):
    response = client.get("/api/no-such-thing")

    assert response.status_code == 404
    assert response.get_json()["ok"] is False
