"""Tests for the Streamlit app. Run `pytest` after `pip install -r requirements-dev.txt`."""

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import sales_core

APP = str(Path(__file__).resolve().parents[1] / "app.py")
SAMPLE_MESSAGE = "We receive 400+ daily inquiries on WhatsApp and web forms, and slow responses are hurting our sales conversion."


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "pipeline.db"))
    monkeypatch.delenv("NEXUSAI_USERS", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)


def sign_in(username, password="sales123"):
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="login_username").input(username)
    at.text_input(key="login_password").input(password)
    at.button[0].click().run()
    assert not at.exception, at.exception
    return at


def lead_count(company):
    with closing(sqlite3.connect(sales_core.db_path())) as connection:
        return connection.execute("SELECT COUNT(*) FROM leads WHERE company = ?", (company,)).fetchone()[0]


def selectbox_by_label(at, label):
    return next(box for box in at.selectbox if box.label == label)


# ---------- sales_core ----------

def test_sample_lead_scores_the_same_as_the_static_app():
    # index.html's scoreLead() gives this sample 85 too; the two apps must agree.
    score = sales_core.score_lead(10500, "Website Demo Request", SAMPLE_MESSAGE)
    assert score == 85
    assert sales_core.tier_for(score) == "Hot 🔥"


@pytest.mark.parametrize("value, expected", [
    ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"),
    ("+1", "'+1"),
    ("-1", "'-1"),
    ("@SUM(A1)", "'@SUM(A1)"),
    ("\t=1", "'\t=1"),
    ("Nexus Retail", "Nexus Retail"),
    (12000, 12000),
])
def test_csv_safe_neutralises_formulas(value, expected):
    assert sales_core.csv_safe(value) == expected


def test_first_name_handles_blank_input():
    assert sales_core.first_name("   ") == "there"
    assert sales_core.first_name("Ariful Islam (Head of Growth)") == "Ariful"


def test_old_database_is_migrated():
    with closing(sqlite3.connect(sales_core.db_path())) as connection, connection:
        connection.execute("CREATE TABLE leads (company TEXT, contact TEXT, channel TEXT, budget INTEGER, score INTEGER, tier TEXT, next_action TEXT)")
        connection.execute("INSERT INTO leads VALUES ('FinEdge Payments', 'Nadia Islam', 'Referral', 18500, 95, 'Hot 🔥', 'Send proposal')")

    [lead] = sales_core.load_leads()
    assert lead["Channel"] == "Customer Referral"
    assert lead["Rep"] == "Sales Team"
    assert lead["Stage"] == "New"


def test_update_and_delete_only_touch_the_owners_lead():
    nadia_lead = next(lead for lead in sales_core.load_leads() if lead["Rep"] == "Nadia")
    changed = {**nadia_lead, "Next Action": "Hijacked"}

    assert not sales_core.update_lead(nadia_lead["id"], changed, owner="Tanvir")
    assert not sales_core.delete_lead(nadia_lead["id"], owner="Tanvir")
    assert sales_core.update_lead(nadia_lead["id"], changed, owner="Nadia")
    assert sales_core.delete_lead(nadia_lead["id"], owner="Nadia")
    assert lead_count(nadia_lead["Company"]) == 0


# ---------- Streamlit UI ----------

def test_wrong_password_is_rejected():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="login_username").input("admin")
    at.text_input(key="login_password").input("wrong")
    at.button[0].click().run()
    assert not at.session_state.logged_in
    assert any("Invalid username or password" in error.value for error in at.error)


def test_configured_accounts_replace_demo_accounts(monkeypatch):
    monkeypatch.setenv("NEXUSAI_USERS", "admin:s3cret-pass")
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.text_input(key="login_username").input("admin")
    at.text_input(key="login_password").input("sales123")
    at.button[0].click().run()
    assert not at.session_state.logged_in

    assert sign_in("admin", "s3cret-pass").session_state.logged_in


def test_admin_sees_every_seed_lead():
    at = sign_in("admin")
    assert at.metric[0].value == "$35,000"


def test_filter_with_no_matching_leads_does_not_crash():
    at = sign_in("tanvir")
    at.selectbox(key="selected_tier").select("Cold ❄️").run()
    assert not at.exception, at.exception
    assert any("No leads match" in info.value for info in at.info)


def test_rep_can_only_pick_their_own_leads_to_edit():
    at = sign_in("nadia")
    assert at.selectbox(key="lead_editor_choice").options == ["FinEdge Payments — Nadia Islam"]


def test_lead_with_unlisted_channel_opens_in_editor():
    sales_core.insert_lead_if_new({"Company": "Expo Co", "Contact": "Rina Das", "Channel": "Trade Show", "Rep": "Tanvir"})
    at = sign_in("tanvir")
    editor = at.selectbox(key="lead_editor_choice")
    editor.select_index(editor.options.index("Expo Co — Rina Das")).run()
    assert not at.exception, at.exception
    assert selectbox_by_label(at, "Channel").value == "Trade Show"


def test_only_admin_can_reset_the_pipeline():
    assert not [button for button in sign_in("tanvir").button if button.key == "reset_pipeline"]
    assert [button for button in sign_in("admin").button if button.key == "reset_pipeline"]


def test_scoring_the_same_lead_twice_adds_it_once():
    at = sign_in("admin")
    at.button(key="analyze_btn").click().run()
    at.button(key="analyze_btn").click().run()
    assert not at.exception, at.exception
    assert lead_count("ShopSphere BD") == 1
    assert any("already in the pipeline" in info.value for info in at.info)


def test_blank_names_show_an_error_instead_of_crashing():
    at = sign_in("admin")
    at.text_input(key="in_name").input("  ")
    at.button(key="analyze_btn").click().run()
    assert not at.exception, at.exception
    assert any("Enter the prospect name" in error.value for error in at.error)
    assert lead_count("ShopSphere BD") == 0

    at.text_input(key="out_contact").input("")
    at.button(key="outbound_btn").click().run()
    assert not at.exception, at.exception
    assert any("Fill in the decision maker" in error.value for error in at.error)
