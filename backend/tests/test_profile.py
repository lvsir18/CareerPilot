from __future__ import annotations

from fastapi.testclient import TestClient

from tests.factories import register_user


def test_profile_defaults_to_empty_state(client: TestClient) -> None:
    register_user(client)

    response = client.get("/api/v1/profile/me")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["skills"] == []
    assert data["version"] == 0
    assert data["verified_by_user"] is False
    assert data["preferences"]["cities"] == []


def test_profile_update_normalizes_and_versions(client: TestClient) -> None:
    register_user(client)

    response = client.patch(
        "/api/v1/profile/me",
        json={
            "headline": "LLM / Agent 算法实习",
            "skills": ["Python", " python ", "LLM", ""],
            "education": [
                {"school": "示例大学", "degree": "硕士", "major": "计算机", "graduation_year": 2029}
            ],
            "preferences": {
                "cities": ["北京", " 上海 ", "北京"],
                "job_types": ["internship", "campus"],
                "keywords": ["LLM", "Agent"],
                "excluded_keywords": ["销售"],
                "target_companies": [],
            },
            "verified_by_user": True,
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["version"] == 1
    assert data["skills"] == ["Python", "LLM"]
    assert data["preferences"]["cities"] == ["北京", "上海"]
    assert data["preferences"]["job_types"] == ["internship", "campus"]
    assert data["verified_by_user"] is True

    second = client.patch("/api/v1/profile/me", json={"headline": "算法实习"})
    assert second.status_code == 200
    assert second.json()["data"]["version"] == 2
    assert second.json()["data"]["skills"] == ["Python", "LLM"]
    # Editing confirmed content invalidates the confirmation.
    assert second.json()["data"]["verified_by_user"] is False


def test_confirmation_survives_noop_patch(client: TestClient) -> None:
    register_user(client)
    client.patch(
        "/api/v1/profile/me",
        json={"headline": "算法实习", "verified_by_user": True},
    )

    same = client.patch("/api/v1/profile/me", json={"headline": "算法实习"})

    assert same.status_code == 200
    assert same.json()["data"]["verified_by_user"] is True


def test_empty_patch_is_rejected(client: TestClient) -> None:
    register_user(client)

    response = client.patch("/api/v1/profile/me", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_job_type_is_rejected(client: TestClient) -> None:
    register_user(client)

    response = client.patch(
        "/api/v1/profile/me",
        json={"preferences": {"job_types": ["freelance"]}},
    )

    assert response.status_code == 422
