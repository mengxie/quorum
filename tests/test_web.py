import re

import httpx

QUESTION_ID = re.compile(r'id="q-([0-9a-f-]{36})"')
HOST_LINK = re.compile(r'id="host-link" readonly value="([^"]+)"')


async def create_session(client: httpx.AsyncClient, title: str = "Friday all-hands") -> str:
    response = await client.post("/events", data={"title": title})
    assert response.status_code == 303
    return response.headers["location"].split("/e/")[1].split("/")[0]


async def ask(client: httpx.AsyncClient, code: str, text: str) -> str:
    response = await client.post(
        f"/e/{code}/questions", data={"text": text}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    board = await client.get(f"/e/{code}/board")
    match = QUESTION_ID.search(board.text)
    assert match is not None
    return match.group(1)


async def test_the_start_page_renders_with_strict_security_headers(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert "Let the room ask." in response.text
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"


async def test_creating_a_session_shows_the_host_link_exactly_once(
    client: httpx.AsyncClient,
) -> None:
    code = await create_session(client)
    first = await client.get(f"/e/{code}/host")
    assert first.status_code == 200
    assert "Save your host link" in first.text
    assert "<svg" in first.text  # the QR code to join
    second = await client.get(f"/e/{code}/host")
    assert "Save your host link" not in second.text


async def test_joining_forgives_how_the_code_is_typed(client: httpx.AsyncClient) -> None:
    code = await create_session(client)
    typed = f"{code[:3]}-{code[3:]}".lower()
    response = await client.get("/join", params={"code": typed})
    assert response.status_code == 303
    assert response.headers["location"].endswith(f"/e/{code}")
    missing = await client.get("/join", params={"code": "ZZZ-ZZZ"})
    assert missing.status_code == 404
    assert "no session with that code" in missing.text


async def test_asking_and_voting_with_htmx(client: httpx.AsyncClient) -> None:
    code = await create_session(client)
    response = await client.post(
        f"/e/{code}/questions",
        data={"text": "How do you test migrations?", "author_name": "Aroha"},
        headers={"HX-Request": "true"},
    )
    assert "Sent." in response.text
    assert 'value="Aroha"' in response.text  # the name is kept for the next question

    board = await client.get(f"/e/{code}/board")
    question_id = QUESTION_ID.search(board.text)
    assert question_id is not None
    voted = await client.post(
        f"/e/{code}/questions/{question_id.group(1)}/vote", headers={"HX-Request": "true"}
    )
    assert 'aria-pressed="true"' in voted.text
    assert "Upvote, 1 vote" in voted.text


async def test_everything_works_without_javascript(client: httpx.AsyncClient) -> None:
    code = await create_session(client)
    asked = await client.post(f"/e/{code}/questions", data={"text": "Plain form post?"})
    assert asked.status_code == 303
    page = await client.get(f"/e/{code}")
    assert "Plain form post?" in page.text
    invalid = await client.post(f"/e/{code}/questions", data={"text": " "})
    assert invalid.status_code == 400
    assert "can&#39;t be empty" in invalid.text


async def test_validation_errors_come_back_inside_the_form(client: httpx.AsyncClient) -> None:
    code = await create_session(client)
    response = await client.post(
        f"/e/{code}/questions", data={"text": "x" * 281}, headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    assert "Keep it to 280 characters." in response.text
    assert 'aria-invalid="true"' in response.text


async def test_host_controls_need_the_host_link(client: httpx.AsyncClient) -> None:
    code = await create_session(client)
    host_page = await client.get(f"/e/{code}/host")
    host_link = HOST_LINK.search(host_page.text)
    assert host_link is not None
    question_id = await ask(client, code, "Can the audience moderate?")

    client.cookies.clear()  # now an audience member
    moderate = f"/e/{code}/questions/{question_id}/moderate"
    assert (await client.post(moderate, data={"action": "hide"})).status_code == 403
    assert (await client.get(f"/e/{code}/host")).status_code == 403
    assert (await client.get(f"/e/{code}/host/not-the-key")).status_code == 403

    claimed = await client.get(host_link.group(1).replace("http://testserver", ""))
    assert claimed.status_code == 303
    assert claimed.headers["location"].endswith(f"/e/{code}/host")
    hidden = await client.post(moderate, data={"action": "hide"}, headers={"HX-Request": "true"})
    assert "Hidden from the room" in hidden.text


async def test_cross_site_form_posts_are_refused(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/events", data={"title": "Hijack"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    same_site = await client.post(
        "/events", data={"title": "Fine"}, headers={"Origin": "http://testserver"}
    )
    assert same_site.status_code == 303


async def test_duplicate_suggestions_appear_while_typing(client: httpx.AsyncClient) -> None:
    code = await create_session(client)
    await ask(client, code, "How do you test database migrations before a release?")
    response = await client.get(
        f"/e/{code}/similar", params={"text": "testing database migrations"}
    )
    assert "Already asked?" in response.text
    nothing = await client.get(f"/e/{code}/similar", params={"text": "lunch"})
    assert "Already asked?" not in nothing.text


async def test_presenter_screen_shows_the_top_question_and_a_qr_code(
    client: httpx.AsyncClient,
) -> None:
    code = await create_session(client)
    await ask(client, code, "What surprised you most?")
    response = await client.get(f"/e/{code}/present")
    assert "What surprised you most?" in response.text
    assert "<svg" in response.text
    assert f"{code[:3]}-{code[3:]}" in response.text


async def test_errors_render_as_pages(client: httpx.AsyncClient) -> None:
    assert (await client.get("/e/ZZZZZZ/stream")).status_code == 404
    assert (await client.get("/no-such-page")).status_code == 404
    assert (await client.get("/healthz")).json() == {"status": "ok"}
