import hmac
import os

import pandas as pd
import streamlit as st

from sales_core import (
    CHANNELS,
    DISPLAY_COLUMNS,
    INBOUND_CHANNELS,
    REPS,
    STAGE_WEIGHT,
    STAGES,
    TIERS,
    csv_safe,
    delete_lead,
    first_name,
    insert_lead_if_new,
    load_leads,
    options_with,
    reset_leads,
    score_lead,
    tier_for,
    update_lead,
)

try:
    from google import genai
except ImportError:
    genai = None

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

ADMIN_USER = "admin"
# Used only when no accounts are configured; see auth_users().
DEMO_USERS = {
    "admin": "sales123",
    "tanvir": "sales123",
    "nadia": "sales123",
    "farhan": "sales123",
}

REBUTTALS = {
    "Price / Budget": (
        "That makes sense—budget matters, and you need to be confident the investment is justified. What outcomes would you need to see for this to feel worthwhile?",
        "Let's compare the cost with the time spent on manual follow-up and the value of opportunities that currently go unanswered, using your actual numbers rather than assumed returns.",
        "Would a small, time-boxed pilot with agreed success measures help you evaluate the value before a broader commitment?",
    ),
    "Bad Timing / Next Quarter": (
        "I understand—the timing may not be right. What is changing next quarter that would make this more relevant?",
        "If useful, we can estimate how much follow-up time is being spent today and revisit when your planning window opens.",
        "Would it help if I sent a concise summary now and followed up on a date you choose?",
    ),
    "Already Using Competitor": (
        "That makes sense. If your current setup is working well, there may be no reason to replace it. What is it doing particularly well for your team?",
        "A fair comparison would focus on any gaps in response time, qualification, or workflow—not on replacing tools that already serve you.",
        "Would a short gap analysis be useful? Your current system stays in place and we only look at areas where you want improvement.",
    ),
    "Need Manager Approval": (
        "Of course—bringing the right people into the decision is important. What will your manager need to understand to evaluate this?",
        "I can prepare a brief summary of the problem, options, estimated costs, and measurable success criteria for your internal discussion.",
        "Would you prefer a short briefing you can share, or a conversation with both of you?",
    ),
}


# ---------- Auth ----------

def configured_users():
    """Accounts from st.secrets["users"] or NEXUSAI_USERS="name:password,name2:password2"."""
    users = {}
    try:
        if st.secrets.load_if_toml_exists() and "users" in st.secrets:
            users = {str(name).strip().lower(): str(password) for name, password in st.secrets["users"].items()}
    except Exception:
        users = {}
    if not users:
        for pair in os.getenv("NEXUSAI_USERS", "").split(","):
            name, separator, password = pair.strip().partition(":")
            if separator and name.strip() and password:
                users[name.strip().lower()] = password
    return users


def auth_users():
    """Returns (users, demo_mode). Demo accounts apply only when nothing is configured."""
    users = configured_users()
    return (users, False) if users else (DEMO_USERS, True)


def check_login(username, password):
    users, _ = auth_users()
    expected = users.get(username.strip().lower())
    return expected is not None and hmac.compare_digest(expected.encode(), password.encode())


def is_admin():
    return st.session_state.get("username") == ADMIN_USER


def current_rep():
    return st.session_state.get("username", "").title()


def rep_choices():
    users, _ = auth_users()
    return sorted(set(REPS) | {name.title() for name in users if name != ADMIN_USER})


# ---------- Gemini ----------

def get_gemini_key():
    key = st.session_state.get("gemini_api_key") or os.getenv("GEMINI_API_KEY")
    return key.strip() if isinstance(key, str) else key


def generate_live_reply(in_name, in_company, in_channel, in_msg):
    """Returns (reply, error). Both are None when no API key is set."""
    api_key = get_gemini_key()
    if not api_key:
        return None, None
    if genai is None:
        return None, "The google-genai package is not installed."
    prompt = (
        f"Write a concise, helpful sales reply to {in_name} at {in_company}. "
        f"They reached out via {in_channel} and said: '{in_msg}'. "
        "Do not make unsupported performance promises. Include a subject line, a short greeting, and one clear next step."
    )
    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        text = (response.text or "").strip()
    except Exception as error:
        return None, f"Gemini request failed ({type(error).__name__}: {error})."
    if not text:
        return None, "Gemini returned an empty response."
    return text, None


# ---------- Session callbacks ----------

def clear_filters():
    st.session_state.selected_rep = "All reps"
    st.session_state.selected_tier = "All tiers"
    st.session_state.selected_stage = "All stages"


def log_out():
    st.session_state.logged_in = False
    st.session_state.username = ""
    clear_filters()


def keep_valid(key, options):
    if st.session_state.get(key) not in options:
        st.session_state[key] = options[0]


st.set_page_config(
    page_title="NexusAI — Inbound & Outbound Sales Agent",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 1500px;
        }
        @media (max-width: 960px) {
            .block-container {
                padding-left: 0.5rem;
                padding-right: 0.5rem;
            }
            div[data-testid="stSidebar"] {
                width: 100% !important;
                max-width: 100% !important;
            }
            .stButton > button {
                width: 100%;
            }
        }
    </style>
    """,
    unsafe_allow_html=True,
)

for state_key, default in {
    "gemini_api_key": "",
    "logged_in": False,
    "username": "",
    "selected_rep": "All reps",
    "selected_tier": "All tiers",
    "selected_stage": "All stages",
}.items():
    st.session_state.setdefault(state_key, default)

st.title("⚡ NexusAI — Inbound & Outbound Sales Growth Agent")
st.caption("AI-Powered Lead Qualification, Multi-Channel Outbound Generation, and Real-Time Objection Handling")

if not st.session_state.logged_in:
    _, demo_mode = auth_users()
    st.warning("Sign in to access the sales workspace.")
    if demo_mode:
        st.info(
            "Demo accounts are active because no accounts are configured. "
            "Before deploying, set real accounts in `st.secrets['users']` or the `NEXUSAI_USERS` environment variable (see README)."
        )
    with st.form("login_form"):
        username = st.text_input("Username", key="login_username")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Sign in")

    if submitted:
        if check_login(username, password):
            st.session_state.logged_in = True
            st.session_state.username = username.strip().lower()
            st.session_state.selected_rep = "All reps"
            st.rerun()
        else:
            st.error("Invalid username or password.")
    st.stop()

leads = [lead for lead in load_leads() if is_admin() or lead["Rep"] == current_rep()]

with st.sidebar:
    st.subheader(f"Welcome, {current_rep()}")
    st.button("Log out", on_click=log_out)

    st.markdown("---")
    st.subheader("AI settings")
    st.text_input(
        "Gemini API key",
        type="password",
        key="gemini_api_key",
        help=f"Optional: enable live AI-generated replies using Google Gemini ({GEMINI_MODEL}).",
    )
    if get_gemini_key():
        st.caption("Live LLM generation enabled.")
    else:
        st.caption("No API key set — app will use the built-in draft reply.")

    st.markdown("---")
    st.subheader("Team filters")
    rep_options = ["All reps"] + sorted({lead["Rep"] for lead in leads} | ({current_rep()} if not is_admin() else set()))
    tier_options = ["All tiers", *TIERS]
    stage_options = ["All stages", *STAGES]
    keep_valid("selected_rep", rep_options)
    keep_valid("selected_tier", tier_options)
    keep_valid("selected_stage", stage_options)
    st.selectbox("Sales rep", rep_options, key="selected_rep")
    st.selectbox("Lead tier", tier_options, key="selected_tier")
    st.selectbox("Pipeline stage", stage_options, key="selected_stage")
    st.button("Clear filters", on_click=clear_filters)

filtered_leads = [
    lead for lead in leads
    if st.session_state.selected_rep in ("All reps", lead["Rep"])
    and st.session_state.selected_tier in ("All tiers", lead["Tier"])
    and st.session_state.selected_stage in ("All stages", lead["Stage"])
]

col1, col2, col3, col4 = st.columns(4)
total_pipeline = sum(item["Budget ($)"] for item in filtered_leads)
hot_leads_count = sum(1 for item in filtered_leads if "Hot" in item["Tier"])
forecast_value = sum(item["Budget ($)"] * STAGE_WEIGHT.get(item["Stage"], 0.08) for item in filtered_leads)
weighted_close_rate = (forecast_value / total_pipeline * 100) if total_pipeline else 0
average_score = sum(item["Score"] for item in filtered_leads) / len(filtered_leads) if filtered_leads else 0

col1.metric("Total Pipeline Value", f"${total_pipeline:,}")
col2.metric("Hot Leads (Score 80+)", str(hot_leads_count))
col3.metric("Forecasted Revenue", f"${forecast_value:,.0f}")
col4.metric("Average Lead Score", f"{average_score:.0f}/100" if filtered_leads else "—")
st.caption(
    f"{len(filtered_leads)} {'lead' if len(filtered_leads) == 1 else 'leads'} in view · "
    f"{weighted_close_rate:.1f}% weighted close likelihood (stage-weighted forecast ÷ pipeline value)"
)

st.markdown("### Revenue Forecast")
forecast_df = pd.DataFrame(
    [
        {"Stage": stage, "Weighted Revenue": sum(lead["Budget ($)"] * weight for lead in filtered_leads if lead["Stage"] == stage)}
        for stage, weight in STAGE_WEIGHT.items()
    ]
)
forecast_df = forecast_df[forecast_df["Weighted Revenue"] > 0]
if forecast_df.empty:
    st.caption("No weighted revenue for the current filters.")
else:
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
        in_name = st.text_input("Prospect Name & Title", "Ariful Islam (Head of Growth)", key="in_name")
        in_company = st.text_input("Company Name", "ShopSphere BD", key="in_company")
        in_budget = st.number_input("Estimated Budget ($)", min_value=500, value=10500, step=500, key="in_budget")
        in_channel = st.selectbox("Inbound Channel", INBOUND_CHANNELS, key="in_channel")
        in_msg = st.text_area("Customer Inquiry / Pain Point", "We receive 400+ daily inquiries on WhatsApp and web forms, and slow responses are hurting our sales conversion.", key="in_msg")
        if is_admin():
            assigned_rep = st.selectbox("Assign rep", rep_choices(), index=rep_choices().index("Sales Team"), key="in_rep")
        else:
            assigned_rep = current_rep()
            st.caption(f"Leads you add are assigned to {assigned_rep}.")
        analyze_btn = st.button("⚡ Score Lead & Draft Instant Reply", width="stretch", type="primary", key="analyze_btn")

    with right:
        st.subheader("AI Qualification Report")
        if analyze_btn:
            name, company, message = in_name.strip(), in_company.strip(), in_msg.strip()
            if not (name and company and message):
                st.error("Enter the prospect name, company, and inquiry first.")
            else:
                score = score_lead(in_budget, in_channel, message)
                tier = tier_for(score)
                action = "Same-day response + tailored ROI walkthrough" if score >= 80 else "Automated 3-step nurture sequence"

                m1, m2 = st.columns(2)
                m1.metric("Lead Conversion Score", f"{score}/100")
                m2.metric("Priority Tier", tier)
                st.info(f"**Recommended Playbook:** {action}")

                reply, ai_error = generate_live_reply(name, company, in_channel, message)
                if ai_error:
                    st.warning(f"{ai_error} Showing the built-in draft instead.")
                if not reply:
                    excerpt = message[:140] + ("…" if len(message) > 140 else "")
                    reply = (
                        f"Subject: Helping {company} respond to leads faster\n\n"
                        f"Hi {first_name(name)},\n\n"
                        f"Thanks for reaching out via {in_channel}. I saw your note: \"{excerpt}\"\n\n"
                        "We help sales teams qualify inquiries and follow up more consistently. "
                        "Would you be open to a short call this week to see whether it fits your workflow?\n\n"
                        "Best regards,\nSales Team"
                    )
                st.text_area("Generated Instant Reply", reply, height=210)

                added = insert_lead_if_new({
                    "Company": company,
                    "Contact": name,
                    "Channel": in_channel,
                    "Budget ($)": in_budget,
                    "Score": score,
                    "Tier": tier,
                    "Rep": assigned_rep,
                    "Stage": "Qualified" if score >= 80 else "New",
                    "Next Action": action,
                })
                if added:
                    st.success(f"Added {company} to Pipeline CRM!")
                else:
                    st.info(f"{company} — {name} is already in the pipeline, so it wasn't added again.")

with tab_outbound:
    st.subheader("Multi-Touch Outbound Campaign Generator")
    st.caption("Built for the selected sales team view and rep-specific pipeline follow-up.")
    c1, c2 = st.columns(2)
    with c1:
        out_contact = st.text_input("Target Decision Maker", "Mahmudul Hasan, Director of Sales", key="out_contact")
        out_company = st.text_input("Target Company", "PrimeTech Solutions", key="out_company")
    with c2:
        out_industry = st.text_input("Industry", "B2B SaaS & IT", key="out_industry")
        out_pain = st.text_input("Core Pain Point", "Low cold outreach reply rates and manual lead qualification", key="out_pain")

    if st.button("🚀 Generate 3-Touch Campaign", type="primary", key="outbound_btn"):
        if not all(value.strip() for value in (out_contact, out_company, out_industry, out_pain)):
            st.error("Fill in the decision maker, company, industry, and pain point first.")
        else:
            first = first_name(out_contact)
            company, industry, pain = out_company.strip(), out_industry.strip(), out_pain.strip().lower()
            st.markdown("#### 1. Cold Email")
            st.code(
                f"Subject: A practical way to improve {company}'s sales follow-up\n\n"
                f"Hi {first},\n\nI noticed {company} works in {industry}. Teams dealing with {pain} "
                "often find that timely, consistent follow-up makes a real difference.\n\n"
                "We help sales teams automate lead scoring and personalised follow-ups. "
                "Would a brief conversation next week be useful to see whether it fits your process?",
                language="markdown"
            )
            st.markdown("#### 2. WhatsApp / LinkedIn DM")
            st.code(
                f"Hi {first} 👋 — I'm reaching out because teams in {industry} are working through {pain}. "
                f"How is {company} handling it today? Happy to share what has worked for similar teams if useful.",
                language="markdown"
            )
            st.markdown("#### 3. Follow-Up Nurture")
            st.code(
                f"Hi {first},\n\nThanks again for your time. I know your team is focused on {pain} while growing in {industry}. "
                "I can share a short breakdown of how teams like yours reduce manual qualification time and respond faster. "
                "Would it be worth sending a brief case study this week?",
                language="markdown"
            )

with tab_objection:
    st.subheader("Real-Time Objection Rebuttal Battlecards")
    objection_type = st.selectbox("Select Customer Pushback", list(REBUTTALS), key="objection_type")
    pivot, value_frame, next_step = REBUTTALS[objection_type]
    o1, o2, o3 = st.columns(3)
    o1.info(f"**1. Empathetic Pivot**\n\n{pivot}")
    o2.success(f"**2. Value Frame**\n\n{value_frame}")
    o3.warning(f"**3. Next Step**\n\n{next_step}")

with tab_crm:
    flash = st.session_state.pop("crm_flash", None)
    if flash:
        (st.success if flash[0] == "success" else st.error)(flash[1])

    st.subheader("Live Qualified Pipeline CRM")
    df = pd.DataFrame(filtered_leads, columns=["id", *DISPLAY_COLUMNS])[DISPLAY_COLUMNS]
    st.dataframe(df, width="stretch", hide_index=True)

    if filtered_leads:
        rep_sales = (
            df.groupby("Rep", dropna=False)["Budget ($)"].sum()
            .reset_index()
            .rename(columns={"Budget ($)": "Pipeline Value"})
        )
        st.markdown("### Team Pipeline Snapshot")
        st.bar_chart(rep_sales.set_index("Rep"), y="Pipeline Value", height=250)

        stage_summary = df.groupby("Stage", dropna=False).size().reset_index(name="Count")
        st.markdown("### Stage Distribution")
        st.bar_chart(stage_summary.set_index("Stage"), y="Count", height=220)

    st.markdown("### Lead Manager")
    if filtered_leads:
        leads_by_id = {lead["id"]: lead for lead in filtered_leads}
        labels = {lead_id: f"{lead['Company']} — {lead['Contact']}" for lead_id, lead in leads_by_id.items()}
        label_counts = pd.Series(list(labels.values())).value_counts()
        selected_id = st.selectbox(
            "Select lead to edit",
            options=list(leads_by_id),
            format_func=lambda lead_id: labels[lead_id] + (f" (#{lead_id})" if label_counts[labels[lead_id]] > 1 else ""),
            key="lead_editor_choice",
        )
        lead = leads_by_id[selected_id]
        owner = None if is_admin() else current_rep()

        with st.form("lead_editor"):
            company = st.text_input("Company", value=lead["Company"])
            contact = st.text_input("Contact", value=lead["Contact"])
            channel_options = options_with(CHANNELS, lead["Channel"])
            channel = st.selectbox("Channel", channel_options, index=channel_options.index(lead["Channel"]))
            rep_options_edit = options_with(rep_choices(), lead["Rep"])
            rep = st.selectbox(
                "Assigned Rep", rep_options_edit, index=rep_options_edit.index(lead["Rep"]),
                disabled=not is_admin(), help=None if is_admin() else "Only an admin can reassign leads.",
            )
            stage_options_edit = options_with(STAGES, lead["Stage"])
            stage = st.selectbox("Pipeline Stage", stage_options_edit, index=stage_options_edit.index(lead["Stage"]))
            budget = st.number_input("Budget ($)", min_value=0, value=max(lead["Budget ($)"], 0), step=500)
            score = st.slider("Score", 0, 100, min(max(lead["Score"], 0), 100))
            tier_options_edit = options_with(TIERS, lead["Tier"])
            tier = st.selectbox("Tier", tier_options_edit, index=tier_options_edit.index(lead["Tier"]))
            next_action = st.text_input("Next Action", value=lead["Next Action"])

            col_edit, col_delete = st.columns(2)
            with col_edit:
                submitted = st.form_submit_button("💾 Save Changes")
            with col_delete:
                delete_clicked = st.form_submit_button("🗑️ Delete Lead")

        if submitted:
            updated = {
                "Company": company.strip() or lead["Company"],
                "Contact": contact.strip() or lead["Contact"],
                "Channel": channel,
                "Budget ($)": budget,
                "Score": score,
                "Tier": tier,
                "Rep": rep if is_admin() else lead["Rep"],
                "Stage": stage,
                "Next Action": next_action,
            }
            if update_lead(selected_id, updated, owner=owner):
                st.session_state.crm_flash = ("success", f"Updated {updated['Company']} successfully!")
            else:
                st.session_state.crm_flash = ("error", "That lead was changed or removed by someone else. Reload and try again.")
            st.rerun()

        if delete_clicked:
            if delete_lead(selected_id, owner=owner):
                st.session_state.crm_flash = ("success", f"Removed {lead['Company']} from the pipeline.")
            else:
                st.session_state.crm_flash = ("error", "That lead was already removed or isn't yours to delete.")
            st.rerun()
    else:
        st.info("No leads match the current view.")

    c1, c2 = st.columns(2)
    with c1:
        csv = df.map(csv_safe).to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download Pipeline CSV", data=csv, file_name="sales_pipeline.csv", mime="text/csv")
    with c2:
        if is_admin() and st.button("🔄 Reset Demo Pipeline", key="reset_pipeline"):
            reset_leads()
            st.session_state.crm_flash = ("success", "Pipeline reset to the demo leads.")
            st.rerun()
