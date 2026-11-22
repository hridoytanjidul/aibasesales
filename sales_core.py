"""Lead scoring, CSV safety, and SQLite storage for the Streamlit app (no Streamlit imports here)."""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).with_name("sales_pipeline.db")

REPS = ["Tanvir", "Nadia", "Farhan", "Sales Team"]
STAGES = ["New", "Qualified", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
TIERS = ["Hot 🔥", "Warm 🌤️", "Cold ❄️"]
INBOUND_CHANNELS = ["Website Demo Request", "WhatsApp / Live Chat", "Customer Referral", "LinkedIn Inbound", "Webinar Signup"]
CHANNELS = ["Inbound Demo", *INBOUND_CHANNELS, "LinkedIn Outbound", "Outbound Email"]
LEGACY_CHANNELS = {"Referral": "Customer Referral"}
STAGE_WEIGHT = {
    "New": 0.08,
    "Qualified": 0.22,
    "Demo Scheduled": 0.45,
    "Proposal": 0.68,
    "Negotiation": 0.82,
    "Closed Won": 1.0,
    "Closed Lost": 0.0,
}
DISPLAY_COLUMNS = ["Company", "Contact", "Channel", "Budget ($)", "Score", "Tier", "Rep", "Stage", "Next Action"]

# Keep the scoring rules identical to scoreLead() in index.html.
SCORING_KEYWORDS = ("conversion", "urgent", "automate", "automation", "scale", "demo", "budget", "sales", "today", "respond")
HIGH_INTENT_CHANNELS = {"Website Demo Request", "Customer Referral", "WhatsApp / Live Chat"}


def normalize_lead(raw_lead):
    raw_lead = raw_lead or {}
    channel = raw_lead.get("Channel") or "Inbound Demo"
    return {
        "id": raw_lead.get("id"),
        "Company": raw_lead.get("Company") or "Untitled Account",
        "Contact": raw_lead.get("Contact") or "Unknown Contact",
        "Channel": LEGACY_CHANNELS.get(channel, channel),
        "Budget ($)": int(raw_lead.get("Budget ($)") or 0),
        "Score": int(raw_lead.get("Score") or 0),
        "Tier": raw_lead.get("Tier") or "Warm 🌤️",
        "Rep": raw_lead.get("Rep") or "Sales Team",
        "Stage": raw_lead.get("Stage") or "New",
        "Next Action": raw_lead.get("Next Action") or "Follow up",
    }


def default_leads():
    return [
        {"Company": "Nexus Retail Ltd.", "Contact": "Tanvir Ahmed", "Channel": "Inbound Demo", "Budget ($)": 12000, "Score": 92, "Tier": "Hot 🔥", "Rep": "Tanvir", "Stage": "Qualified", "Next Action": "Book Executive ROI Demo"},
        {"Company": "FinEdge Payments", "Contact": "Nadia Islam", "Channel": "Customer Referral", "Budget ($)": 18500, "Score": 95, "Tier": "Hot 🔥", "Rep": "Nadia", "Stage": "Proposal", "Next Action": "Send Enterprise Proposal"},
        {"Company": "EdVantage BD", "Contact": "Farhan Kabir", "Channel": "LinkedIn Outbound", "Budget ($)": 4500, "Score": 68, "Tier": "Warm 🌤️", "Rep": "Farhan", "Stage": "Demo Scheduled", "Next Action": "3-Touch Case Study Sequence"},
    ]


def score_lead(budget, channel, message):
    text = message.lower()
    keyword_score = min(5 * sum(word in text for word in SCORING_KEYWORDS), 25)
    budget_score = 35 if budget >= 10000 else 25 if budget >= 5000 else 15 if budget >= 1000 else 8
    channel_score = 15 if channel in HIGH_INTENT_CHANNELS else 8
    return min(99, 25 + budget_score + keyword_score + channel_score)


def tier_for(score):
    return "Hot 🔥" if score >= 80 else "Warm 🌤️" if score >= 55 else "Cold ❄️"


def first_name(full_name):
    parts = full_name.split()
    return parts[0] if parts else "there"


def csv_safe(value):
    """Stop spreadsheet apps from running cell text as a formula."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def options_with(options, value):
    """Selectbox options that always include the lead's current value, so old data never crashes the editor."""
    return options if value in options else [*options, value]


# Storage: each change touches only its own row, so people working at the same time don't overwrite
# each other. Leads are identified by SQLite's rowid, which stays stable because the table is never VACUUMed.

INSERT_SQL = "INSERT INTO leads (company, contact, channel, budget, score, tier, rep, stage, next_action) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"


def db_path():
    return Path(os.getenv("SALES_DB_PATH") or DEFAULT_DB_PATH)


def connect():
    return closing(sqlite3.connect(db_path()))


def lead_values(lead):
    lead = normalize_lead(lead)
    return (
        lead["Company"], lead["Contact"], lead["Channel"], lead["Budget ($)"], lead["Score"],
        lead["Tier"], lead["Rep"], lead["Stage"], lead["Next Action"],
    )


def init_db():
    with connect() as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS leads (
                company TEXT,
                contact TEXT,
                channel TEXT,
                budget INTEGER,
                score INTEGER,
                tier TEXT,
                rep TEXT,
                stage TEXT,
                next_action TEXT
            )
            """
        )
        for column in ("rep", "stage"):
            try:
                connection.execute(f"ALTER TABLE leads ADD COLUMN {column} TEXT")
            except sqlite3.OperationalError:
                pass
        if connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 0:
            connection.executemany(INSERT_SQL, [lead_values(lead) for lead in default_leads()])
        connection.execute("UPDATE leads SET rep = 'Sales Team' WHERE rep IS NULL")
        connection.execute("UPDATE leads SET stage = 'New' WHERE stage IS NULL")
        for old, new in LEGACY_CHANNELS.items():
            connection.execute("UPDATE leads SET channel = ? WHERE channel = ?", (new, old))


def load_leads():
    init_db()
    with connect() as connection:
        rows = connection.execute(
            "SELECT rowid, company, contact, channel, budget, score, tier, rep, stage, next_action FROM leads ORDER BY rowid DESC"
        ).fetchall()
    return [normalize_lead({
        "id": lead_id,
        "Company": company,
        "Contact": contact,
        "Channel": channel,
        "Budget ($)": budget,
        "Score": score,
        "Tier": tier,
        "Rep": rep,
        "Stage": stage,
        "Next Action": next_action,
    }) for lead_id, company, contact, channel, budget, score, tier, rep, stage, next_action in rows]


def insert_lead_if_new(lead):
    """Adds the lead unless the same company and contact already exist. Returns True if it was added."""
    lead = normalize_lead(lead)
    init_db()
    with connect() as connection, connection:
        exists = connection.execute(
            "SELECT 1 FROM leads WHERE lower(company) = lower(?) AND lower(contact) = lower(?)",
            (lead["Company"], lead["Contact"]),
        ).fetchone()
        if exists:
            return False
        connection.execute(INSERT_SQL, lead_values(lead))
        return True


def update_lead(lead_id, lead, owner=None):
    """Updates one lead. With an owner, only that rep's lead can change. Returns True if a row changed."""
    sql = "UPDATE leads SET company = ?, contact = ?, channel = ?, budget = ?, score = ?, tier = ?, rep = ?, stage = ?, next_action = ? WHERE rowid = ?"
    params = [*lead_values(lead), lead_id]
    if owner is not None:
        sql += " AND rep = ?"
        params.append(owner)
    init_db()
    with connect() as connection, connection:
        return connection.execute(sql, params).rowcount == 1


def delete_lead(lead_id, owner=None):
    """Deletes one lead. With an owner, only that rep's lead can be deleted. Returns True if a row was removed."""
    sql = "DELETE FROM leads WHERE rowid = ?"
    params = [lead_id]
    if owner is not None:
        sql += " AND rep = ?"
        params.append(owner)
    init_db()
    with connect() as connection, connection:
        return connection.execute(sql, params).rowcount == 1


def reset_leads():
    init_db()
    with connect() as connection, connection:
        connection.execute("DELETE FROM leads")
        connection.executemany(INSERT_SQL, [lead_values(lead) for lead in default_leads()])
