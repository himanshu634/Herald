from herald_core.graph import build_graph
from herald_core.model import FakeModel, ModelError
from herald_core.schema import SPAM_TOPIC, RuleAction, RuleDraft, SetupDraft, Urgency
from herald_server.setup import FALLBACK_TOPICS, clean_draft

DESCRIPTION = "We bake custom cakes to order and deliver them. A missed delivery is a disaster."


def rule(name: str, action=RuleAction.ALERT, urgency=None) -> RuleDraft:
    return RuleDraft(name=name, when="It is about a cake", action=action, urgency=urgency)


def test_clean_draft_tidies_topics():
    draft = SetupDraft(
        topics=[" Orders ", "orders", SPAM_TOPIC, "", "Allergies"], guidance=[], rules=[]
    )
    assert [t.name for t in clean_draft(draft, DESCRIPTION).topics] == ["Orders", "Allergies"]


def test_clean_draft_falls_back_when_no_topics_are_left():
    draft = SetupDraft(topics=[SPAM_TOPIC, "  "], guidance=[], rules=[])
    assert [t.name for t in clean_draft(draft, DESCRIPTION).topics] == FALLBACK_TOPICS


def test_clean_draft_caps_counts():
    draft = SetupDraft(
        topics=[f"Topic {i}" for i in range(20)],
        guidance=[f"Line {i}" for i in range(20)],
        rules=[rule(f"Rule {i}") for i in range(20)],
    )
    config = clean_draft(draft, DESCRIPTION)
    assert (len(config.topics), len(config.guidance), len(config.rules)) == (12, 8, 8)


def test_clean_draft_fixes_rules():
    draft = SetupDraft(
        topics=["Orders"],
        guidance=[],
        rules=[
            rule("Same day"),
            rule("Same day"),
            rule("No urgency", RuleAction.SET_URGENCY),
            rule("Closes", RuleAction.CLOSE, Urgency.HIGH),
        ],
    )
    rules = clean_draft(draft, DESCRIPTION).rules
    assert [r.id for r in rules] == ["same-day", "same-day-2", "closes"]
    assert rules[2].urgency is None


async def start(client, name="Crumb", description=DESCRIPTION):
    response = await client.post(
        "/api/workspaces/setup", json={"name": name, "description": description}
    )
    assert response.status_code == 201
    return response.json()


async def test_setup_creates_a_draft_workspace(client):
    body = await start(client)
    workspace = body["workspace"]
    assert body["drafted"] is True
    assert workspace["setup_done"] is False
    assert workspace["config"]["business_profile"] == DESCRIPTION
    assert "Orders and delivery" in [t["name"] for t in workspace["config"]["topics"]]


async def test_setup_falls_back_when_the_ai_fails(app, client):
    class BrokenModel(FakeModel):
        async def suggest_setup(self, name, description):
            raise ModelError("AI service is down")

    app.state.services.model = BrokenModel()
    body = await start(client)
    assert body["drafted"] is False
    assert [t["name"] for t in body["workspace"]["config"]["topics"]] == FALLBACK_TOPICS


async def test_draft_workspace_takes_no_email_until_saved(app, client):
    workspace = (await start(client))["workspace"]
    ws = workspace["id"]
    email = {"sender": "riya@customer.in", "subject": "Order", "body": "Where is my cake?"}
    assert (await client.post(f"/api/workspaces/{ws}/emails", json=email)).status_code == 409

    config = workspace["config"] | {"guidance": ["Wedding cakes are always urgent."]}
    saved = await client.put(
        f"/api/workspaces/{ws}/config", json={"name": "Crumb", "config": config}
    )
    assert saved.status_code == 200
    assert saved.json()["setup_done"] is True
    assert saved.json()["config"]["guidance"] == ["Wedding cakes are always urgent."]
    assert (await client.post(f"/api/workspaces/{ws}/emails", json=email)).status_code == 202


async def test_saved_guidance_reaches_the_notes_model(app, client):
    seen = []

    class RecordingModel(FakeModel):
        async def write_notes(self, email, config):
            seen.append(config.guidance)
            return await super().write_notes(email, config)

    workspace = (await start(client))["workspace"]
    ws = workspace["id"]
    config = workspace["config"] | {"guidance": ["Wedding cakes are always urgent."]}
    await client.put(f"/api/workspaces/{ws}/config", json={"name": "Crumb", "config": config})

    app.state.services.graph = build_graph(RecordingModel())
    email = {"sender": "riya@customer.in", "subject": "Order", "body": "Where is my cake?"}
    await client.post(f"/api/workspaces/{ws}/emails", json=email)
    await app.state.queue.drain()
    assert seen == [["Wedding cakes are always urgent."]]


async def test_config_needs_a_topic(client):
    workspace = (await start(client))["workspace"]
    config = workspace["config"] | {"topics": []}
    response = await client.put(
        f"/api/workspaces/{workspace['id']}/config", json={"name": "Crumb", "config": config}
    )
    assert response.status_code == 422


async def test_suggest_saves_nothing(client):
    workspace = (await start(client))["workspace"]
    ws = workspace["id"]
    response = await client.post(
        f"/api/workspaces/{ws}/setup/suggest",
        json={"description": "We sell software subscriptions."},
    )
    assert response.status_code == 200
    assert "Accounts and subscriptions" in [t["name"] for t in response.json()["config"]["topics"]]
    stored = (await client.get(f"/api/workspaces/{ws}")).json()
    assert stored["config"] == workspace["config"]


async def test_demo_workspace_is_set_up(client):
    assert (await client.post("/api/workspaces/demo")).json()["setup_done"] is True


async def test_setup_routes_are_scoped_to_their_workspace(client):
    a = (await start(client, "A"))["workspace"]
    b = (await start(client, "B"))["workspace"]
    config = a["config"] | {"topics": ["Only A"]}
    await client.put(f"/api/workspaces/{a['id']}/config", json={"name": "A", "config": config})
    stored_b = (await client.get(f"/api/workspaces/{b['id']}")).json()
    assert [t["name"] for t in stored_b["config"]["topics"]] != ["Only A"]
    assert stored_b["setup_done"] is False
    missing = await client.put("/api/workspaces/nope/config", json={"name": "A", "config": config})
    assert missing.status_code == 404
