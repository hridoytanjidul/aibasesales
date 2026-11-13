import json
import os
import sqlite3
from pathlib import Path

import streamlit as st
import pandas as pd

try:
    import google.generativeai as genai
except ImportError:
    genai = None

DB_PATH = Path(__file__).with_name("sales_pipeline.db")
AUTH_USERS = {
    "admin": "sales123",
    "tanvir": "sales123",
    "nadia": "sales123",
    "farhan": "sales123",
}
REPS = ["Tanvir", "Nadia", "Farhan", "Sales Team"]
STAGES = ["New", "Qualified", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
TIERS = ["Hot 🔥", "Warm 🌤️", "Cold ❄️"]
CHANNELS = [
    "Inbound Demo",
    "Website Demo Request",
    "WhatsApp / Live Chat",
    "Customer Referral",
    "LinkedIn Outbound",
    "LinkedIn Inbound",
    "Outbound Email",
]


def normalize_lead(raw_lead):
    return {
        "Company": (raw_lead or {}).get("Company", "Untitled Account"),
        "Contact": (raw_lead or {}).get("Contact", "Unknown Contact"),
        "Channel": (raw_lead or {}).get("Channel", "Inbound Demo"),
        "Budget ($)": int((raw_lead or {}).get("Budget ($)", 0) or 0),
        "Score": int((raw_lead or {}).get("Score", 0) or 0),
        "Tier": (raw_lead or {}).get("Tier", "Warm 🌤️"),
        "Rep": (raw_lead or {}).get("Rep", "Sales Team"),
        "Stage": (raw_lead or {}).get("Stage", "New"),
        "Next Action": (raw_lead or {}).get("Next Action", "Follow up"),
    }


def default_leads():
    return [
        {"Company": "Nexus Retail Ltd.", "Contact": "Tanvir Ahmed", "Channel": "Inbound Demo", "Budget ($)": 12000, "Score": 92, "Tier": "Hot 🔥", "Rep": "Tanvir", "Stage": "Qualified", "Next Action": "Book Executive ROI Demo"},
        {"Company": "FinEdge Payments", "Contact": "Nadia Islam", "Channel": "Referral", "Budget ($)": 18500, "Score": 95, "Tier": "Hot 🔥", "Rep": "Nadia", "Stage": "Proposal", "Next Action": "Send Enterprise Proposal"},
        {"Company": "EdVantage BD", "Contact": "Farhan Kabir", "Channel": "LinkedIn Outbound", "Budget ($)": 4500, "Score": 68, "Tier": "Warm 🌤️", "Rep": "Farhan", "Stage": "Demo Scheduled", "Next Action": "3-Touch Case Study Sequence"},
    ]


def get_user_visible_leads(leads):
    user = st.session_state.get("username", "")
    normalized = [normalize_lead(lead) for lead in leads]
    if not user or user == "admin":
        return normalized
    return [lead for lead in normalized if lead.get("Rep", "Sales Team") == user.title()]


def init_db():
    connection = sqlite3.connect(DB_PATH)
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
    try:
        connection.execute("ALTER TABLE leads ADD COLUMN rep TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        connection.execute("ALTER TABLE leads ADD COLUMN stage TEXT")
    except sqlite3.OperationalError:
        pass
    if connection.execute("SELECT COUNT(*) FROM leads").fetchone()[0] == 0:
        connection.executemany(
            "INSERT INTO leads (company, contact, channel, budget, score, tier, rep, stage, next_action) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    lead["Company"],
                    lead["Contact"],
                    lead["Channel"],
                    lead["Budget ($)"],
                    lead["Score"],
                    lead["Tier"],
                    lead.get("Rep", "Sales Team"),
                    lead.get("Stage", "New"),
                    lead["Next Action"],
                )
                for lead in default_leads()
            ],
        )
    connection.execute("UPDATE leads SET rep = COALESCE(rep, 'Sales Team') WHERE rep IS NULL")
    connection.execute("UPDATE leads SET stage = COALESCE(stage, 'New') WHERE stage IS NULL")
    connection.commit()
    connection.close()


def load_leads():
    init_db()
    connection = sqlite3.connect(DB_PATH)
    rows = connection.execute(
        "SELECT company, contact, channel, budget, score, tier, rep, stage, next_action FROM leads ORDER BY rowid DESC"
    ).fetchall()
    connection.close()
    return [normalize_lead({
        "Company": company,
        "Contact": contact,
        "Channel": channel,
        "Budget ($)": budget,
        "Score": score,
        "Tier": tier,
        "Rep": rep,
        "Stage": stage,
        "Next Action": next_action,
    }) for company, contact, channel, budget, score, tier, rep, stage, next_action in rows]


def save_leads(leads):
    normalized = [normalize_lead(lead) for lead in leads]
    connection = sqlite3.connect(DB_PATH)
    connection.execute("DELETE FROM leads")
    connection.executemany(
        "INSERT INTO leads (company, contact, channel, budget, score, tier, rep, stage, next_action) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                lead.get("Company", ""),
                lead.get("Contact", ""),
                lead.get("Channel", ""),
                lead.get("Budget ($)", 0),
                lead.get("Score", 0),
                lead.get("Tier", ""),
                lead.get("Rep", "Sales Team"),
                lead.get("Stage", "New"),
                lead.get("Next Action", ""),
            )
            for lead in normalized
        ],
    )
    connection.commit()
    connection.close()


def get_gemini_key():
    key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    return key.strip() if isinstance(key, str) else key


def generate_live_reply(in_name, in_company, in_channel, in_msg):
    api_key = get_gemini_key()
    if not api_key or genai is None:
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-2.0-flash")
        prompt = (
            f"Write a polished sales outreach email for a prospect named {in_name} at {in_company}. "
            f"The customer reached out via {in_channel} and said: '{in_msg}'. "
            "Keep it concise, professional, and persuasive. Include a subject line and a short greeting."
        )
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception:
        return None


st.set_page_config(
    page_title="NexusAI — Inbound & Outbound Sales Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize session state for CRM leads
if "crm_leads" not in st.session_state:
    st.session_state.crm_leads = load_leads()
if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = ""
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "username" not in st.session_state:
    st.session_state.username = ""
if "selected_rep" not in st.session_state:
    st.session_state.selected_rep = "All reps"
if "selected_tier" not in st.session_state:
    st.session_state.selected_tier = "All tiers"
if "selected_stage" not in st.session_state:
    st.session_state.selected_stage = "All stages"

st.title("⚡ NexusAI — Inbound & Outbound Sales Growth Agent")
st.caption("AI-Powered Lead Qualification, Multi-Channel Outbound Generation, and Real-Time Objection Handling")

if not st.session_state.logged_in:
    st.warning("Sign in to access the sales workspace.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if username in AUTH_USERS and AUTH_USERS[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.session_state.selected_rep = "All reps" if username == "admin" else username.title()
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()

with st.sidebar:
    st.subheader(f"Welcome, {st.session_state.username.title()}")
    if st.button("Log out"):
        st.session_state.logged_in = False
        st.session_state.username = ""
        st.session_state.selected_rep = "All reps"
        st.rerun()

    st.markdown("---")
    st.subheader("AI settings")
    st.session_state.gemini_api_key = st.text_input(
        "Gemini API key",
        value=st.session_state.gemini_api_key,
        type="password",
        help="Optional: enable live AI-generated replies using Google Gemini.",
    )
    if st.session_state.gemini_api_key:
        st.caption("Live LLM generation enabled.")
    else:
        st.caption("No API key set — app will use the built-in draft reply.")

    st.markdown("---")
    st.subheader("Team filters")
    rep_options = ["All reps"] + sorted({lead.get("Rep", "Sales Team") for lead in get_user_visible_leads(st.session_state.crm_leads)})
    if st.session_state.username != "admin":
        rep_options = ["All reps", st.session_state.username.title()] + [rep for rep in rep_options if rep not in ["All reps", st.session_state.username.title()]]
    st.session_state.selected_rep = st.selectbox("Sales rep", rep_options, index=rep_options.index(st.session_state.get("selected_rep", "All reps")) if st.session_state.get("selected_rep", "All reps") in rep_options else 0)
    tier_options = ["All tiers", "Hot 🔥", "Warm 🌤️", "Cold ❄️"]
    st.session_state.selected_tier = st.selectbox("Lead tier", tier_options, index=tier_options.index(st.session_state.get("selected_tier", "All tiers")) if st.session_state.get("selected_tier", "All tiers") in tier_options else 0)
    stage_options = ["All stages", "New", "Qualified", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"]
    st.session_state.selected_stage = st.selectbox("Pipeline stage", stage_options, index=stage_options.index(st.session_state.get("selected_stage", "All stages")) if st.session_state.get("selected_stage", "All stages") in stage_options else 0)

    if st.button("Clear filters"):
        st.session_state.selected_rep = "All reps"
        st.session_state.selected_tier = "All tiers"
        st.session_state.selected_stage = "All stages"
        st.rerun()

filtered_leads = get_user_visible_leads(st.session_state.crm_leads)
if st.session_state.get("selected_rep", "All reps") != "All reps":
    filtered_leads = [lead for lead in filtered_leads if lead.get("Rep", "Sales Team") == st.session_state.selected_rep]
if st.session_state.get("selected_tier", "All tiers") != "All tiers":
    filtered_leads = [lead for lead in filtered_leads if lead.get("Tier", "") == st.session_state.selected_tier]
if st.session_state.get("selected_stage", "All stages") != "All stages":
    filtered_leads = [lead for lead in filtered_leads if lead.get("Stage", "New") == st.session_state.selected_stage]

# Responsive KPI Row
stage_weight = {
    "New": 0.08,
    "Qualified": 0.22,
    "Demo Scheduled": 0.45,
    "Proposal": 0.68,
    "Negotiation": 0.82,
    "Closed Won": 1.0,
    "Closed Lost": 0.0,
}

col1, col2, col3, col4 = st.columns(4)
total_pipeline = sum(item["Budget ($)"] for item in filtered_leads)
hot_leads_count = sum(1 for item in filtered_leads if "Hot" in item["Tier"])
forecast_value = sum(item["Budget ($)"] * stage_weight.get(item.get("Stage", "New"), 0.08) for item in filtered_leads)
weighted_close_rate = (forecast_value / total_pipeline * 100) if total_pipeline else 0

col1.metric("Total Pipeline Value", f"${total_pipeline:,}", "+28.4%")
col2.metric("Hot Leads (Score 80+)", str(hot_leads_count), "Immediate Priority")
col3.metric("Forecasted Revenue", f"${forecast_value:,.0f}", f"{weighted_close_rate:.1f}% close likelihood")
col4.metric("Inbound Response SLA", "14 sec", "3.4x Faster")

st.markdown("### Revenue Forecast")
forecast_df = pd.DataFrame(
    [
        {"Stage": stage, "Weighted Revenue": sum(lead["Budget ($)"] * weight for lead in filtered_leads if lead.get("Stage", "New") == stage)}
        for stage, weight in stage_weight.items()
    ]
)
forecast_df = forecast_df[forecast_df["Weighted Revenue"] > 0]
st.bar_chart(forecast_df.set_index("Stage"), y="Weighted Revenue", height=260)

tab_inbound, tab_outbound, tab_objection, tab_crm = st.tabs([
    "📥 Inbound AI Qualifier",
    "🚀 Outbound Pitch Studio",
    "🛡️ Objection Battlecards",
    "📊 Pipeline CRM"
])

with tab_inbound:
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Qualify Incoming Lead")
        in_name = st.text_input("Prospect Name & Title", "Ariful Islam (Head of Growth)")
        in_company = st.text_input("Company Name", "ShopSphere BD")
        in_budget = st.number_input("Estimated Budget ($)", min_value=500, value=10500, step=500)
        in_channel = st.selectbox("Inbound Channel", ["Website Demo Request", "WhatsApp / Live Chat", "Customer Referral", "LinkedIn Inbound"])
        in_msg = st.text_area("Customer Inquiry / Pain Point", "We receive 400+ daily inquiries on WhatsApp and web forms, and slow responses are hurting our sales conversion.")
        assigned_rep = st.selectbox("Assign rep", ["Tanvir", "Nadia", "Farhan", "Sales Team"], index=3)
        analyze_btn = st.button("⚡ Score Lead & Draft Instant Reply", width="stretch", type="primary")

    with right:
        st.subheader("AI Qualification Report")
        if analyze_btn:
            score = 25
            score += 35 if in_budget >= 10000 else (25 if in_budget >= 5000 else 10)
            keywords = ["conversion", "sales", "urgent", "whatsapp", "automate", "scale", "demo"]
            score += min(sum(8 for kw in keywords if kw in in_msg.lower()), 25)
            score += 15 if in_channel in ["Website Demo Request", "Customer Referral", "WhatsApp / Live Chat"] else 8
            score = min(score, 99)

            tier = "Hot 🔥" if score >= 80 else ("Warm 🌤️" if score >= 55 else "Cold ❄️")
            action = "Immediate closer outreach + custom ROI walkthrough" if score >= 80 else "Automated 3-step nurture sequence"

            m1, m2 = st.columns(2)
            m1.metric("Lead Conversion Score", f"{score}/100")
            m2.metric("Priority Tier", tier)
            st.info(f"**Recommended Playbook:** {action}")

            reply = (
                f"Subject: Accelerating conversion for {in_company}\n\n"
                f"Hi {in_name.split()[0]},\n\n"
                f"Thanks for reaching out via {in_channel}. I saw your note regarding '{in_msg[:70]}...'\n\n"
                f"Our AI Sales Growth Agent plugs directly into your inbound and outbound channels to qualify leads in under 15 seconds "
                f"and lift sales conversion by 35% within 60 days.\n\n"
                f"Are you open to a quick 10-minute walkthrough tomorrow at 11:00 AM?\n\nBest regards,\nSales Growth Team"
            )
            generated_live_reply = generate_live_reply(in_name, in_company, in_channel, in_msg)
            if generated_live_reply:
                reply = generated_live_reply
            st.text_area("Generated Instant Reply", reply, height=210)

            lead_rep = assigned_rep if st.session_state.username == "admin" else st.session_state.username.title()
            st.session_state.crm_leads.insert(0, {
                "Company": in_company,
                "Contact": in_name,
                "Channel": in_channel,
                "Budget ($)": in_budget,
                "Score": score,
                "Tier": tier,
                "Rep": lead_rep,
                "Stage": "Qualified" if score >= 80 else "New",
                "Next Action": action
            })
            save_leads(st.session_state.crm_leads)
            st.success(f"Added {in_company} to Pipeline CRM!")

with tab_outbound:
    st.subheader("Multi-Touch Outbound Campaign Generator")
    st.caption("Built for the selected sales team view and rep-specific pipeline follow-up.")
    c1, c2 = st.columns(2)
    with c1:
        out_contact = st.text_input("Target Decision Maker", "Mahmudul Hasan, Director of Sales")
        out_company = st.text_input("Target Company", "PrimeTech Solutions")
    with c2:
        out_industry = st.text_input("Industry", "B2B SaaS & IT")
        out_pain = st.text_input("Core Pain Point", "Low cold outreach reply rates and manual lead qualification")

    if st.button("🚀 Generate 3-Touch Campaign", type="primary"):
        first_name = out_contact.split()[0]
        st.markdown("#### 1. Cold Email")
        st.code(
            f"Subject: Solving {out_pain.lower()} at {out_company}\n\n"
            f"Hi {first_name},\n\nNoticed {out_company} is scaling rapidly in {out_industry}. "
            f"Many sales leaders we speak with are tackling {out_pain.lower()}.\n\n"
            f"We built an AI Inbound & Outbound Sales Agent that automates lead scoring and hyper-personalized follow-ups, "
            f"increasing qualified pipeline by 35% in 60 days.\n\nOpen to a 10-minute chat this Thursday?",
            language="markdown"
        )
        st.markdown("#### 2. WhatsApp / LinkedIn DM")
        st.code(
            f"Hi {first_name} 👋 — saw {out_company}'s growth in {out_industry}! How is your team currently handling {out_pain.lower()}? "
            f"We just helped a similar team boost conversion 35% with AI sales automation. Open to a 60-sec walkthrough?",
            language="markdown"
        )
        st.markdown("#### 3. Follow-Up Nurture")
        st.code(
            f"Hi {first_name},\n\nThanks again for your time. I know your team is focused on improving {out_pain.lower()} while scaling in {out_industry}. "
            f"I wanted to share a quick breakdown of how our system can reduce manual qualification time and improve response rates within the first 30 days. "
            f"Would it be worth sending a short case-study deck this week?",
            language="markdown"
        )

with tab_objection:
    st.subheader("Real-Time Objection Rebuttal Battlecards")
    objection_type = st.selectbox("Select Customer Pushback", ["Price / Budget", "Bad Timing / Next Quarter", "Already Using Competitor"])
    rebuttals = {
        "Price / Budget": "If our AI agent rescues just 4 missed inbound leads a month, it pays for itself 3x over. Let's start with a 30-day performance pilot so you see net revenue before scaling.",
        "Bad Timing / Next Quarter": "Because your team is busy right now, waiting 90 days means losing warm leads every week. Setup takes under 48 hours and saves each rep 8+ hours weekly.",
        "Already Using Competitor": "You don't need to rip and replace your current CRM—our AI Agent layers on top to reduce response times from hours to 14 seconds. Let's run a 14-day split test."
    }
    st.success(f"**Recommended Rebuttal Script:**\n\n\"{rebuttals[objection_type]}\"")

with tab_crm:
    st.subheader("Live Qualified Pipeline CRM")
    df = pd.DataFrame(filtered_leads)
    st.dataframe(df, width="stretch")

    rep_sales = (
        pd.DataFrame(filtered_leads)
        .groupby("Rep", dropna=False)["Budget ($)"].sum()
        .reset_index()
        .rename(columns={"Budget ($)": "Pipeline Value"})
    )
    if not rep_sales.empty:
        st.markdown("### Team Pipeline Snapshot")
        st.bar_chart(rep_sales.set_index("Rep"), y="Pipeline Value", height=250)

    stage_summary = pd.DataFrame(filtered_leads)
    if not stage_summary.empty:
        stage_summary = (
            stage_summary.groupby("Stage", dropna=False).size().reset_index(name="Count")
        )
        st.markdown("### Stage Distribution")
        st.bar_chart(stage_summary.set_index("Stage"), y="Count", height=220)

    st.markdown("### Lead Manager")
    if filtered_leads:
        lead_options = {f"{lead['Company']} — {lead['Contact']}": idx for idx, lead in enumerate(st.session_state.crm_leads)}
        selected_label = st.selectbox("Select lead to edit", options=list(lead_options.keys()))
        selected_index = lead_options[selected_label]
        lead = st.session_state.crm_leads[selected_index]

        with st.form("lead_editor"):
            company = st.text_input("Company", value=lead["Company"])
            contact = st.text_input("Contact", value=lead["Contact"])
            channel = st.selectbox("Channel", ["Inbound Demo", "Website Demo Request", "WhatsApp / Live Chat", "Customer Referral", "LinkedIn Outbound", "LinkedIn Inbound", "Outbound Email"], index=["Inbound Demo", "Website Demo Request", "WhatsApp / Live Chat", "Customer Referral", "LinkedIn Outbound", "LinkedIn Inbound", "Outbound Email"].index(lead.get("Channel", "Inbound Demo")))
            rep = st.selectbox("Assigned Rep", ["Tanvir", "Nadia", "Farhan", "Sales Team"], index=["Tanvir", "Nadia", "Farhan", "Sales Team"].index(lead.get("Rep", "Sales Team")))
            stage = st.selectbox("Pipeline Stage", ["New", "Qualified", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"], index=["New", "Qualified", "Demo Scheduled", "Proposal", "Negotiation", "Closed Won", "Closed Lost"].index(lead.get("Stage", "New")))
            budget = st.number_input("Budget ($)", min_value=0, value=int(lead.get("Budget ($)", 0)), step=500)
            score = st.slider("Score", 0, 100, int(lead.get("Score", 0)))
            tier = st.selectbox("Tier", ["Hot 🔥", "Warm 🌤️", "Cold ❄️"], index=["Hot 🔥", "Warm 🌤️", "Cold ❄️"].index(lead.get("Tier", "Warm 🌤️")))
            next_action = st.text_input("Next Action", value=lead.get("Next Action", ""))

            col_edit, col_delete = st.columns(2)
            with col_edit:
                submitted = st.form_submit_button("💾 Save Changes")
            with col_delete:
                delete_clicked = st.form_submit_button("🗑️ Delete Lead")

            if submitted:
                st.session_state.crm_leads[selected_index] = {
                    "Company": company,
                    "Contact": contact,
                    "Channel": channel,
                    "Budget ($)": budget,
                    "Score": score,
                    "Tier": tier,
                    "Rep": rep,
                    "Stage": stage,
                    "Next Action": next_action,
                }
                save_leads(st.session_state.crm_leads)
                st.success(f"Updated {company} successfully!")
                st.rerun()

            if delete_clicked:
                del st.session_state.crm_leads[selected_index]
                save_leads(st.session_state.crm_leads)
                st.success(f"Removed {lead['Company']} from the pipeline.")
                st.rerun()
    else:
        st.info("No leads in the pipeline yet.")

    c1, c2 = st.columns(2)
    with c1:
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Pipeline CSV", data=csv, file_name="sales_pipeline.csv", mime="text/csv")
    with c2:
        if st.button("🔄 Reset Demo Pipeline"):
            st.session_state.crm_leads = default_leads()
            save_leads(st.session_state.crm_leads)
            st.rerun()