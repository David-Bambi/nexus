def test_home_page_returns_200(client):
    """The empty home page responds successfully."""
    response = client.get("/")
    assert response.status_code == 200
