import streamlit as st

from dashboard.api_client import (
    APIConnectionError,
    APIError,
    HelpdeskAPIClient,
    SessionExpiredError,
)
from dashboard.formatting import format_datetime


def render_new_ticket(client: HelpdeskAPIClient) -> None:
    """Render the Create New Ticket form."""
    st.subheader("➕ Create a New Ticket")

    with st.form("new_ticket_form"):
        title = st.text_input("Title", placeholder="e.g. Cannot access corporate VPN").strip()

        col_prio, col_cat = st.columns(2)
        with col_prio:
            priority = st.selectbox("Priority", ["low", "medium", "high", "urgent"], index=1)
        with col_cat:
            category = st.selectbox(
                "Category",
                ["network", "hardware", "software", "access", "email", "other"],
                index=5,
            )

        description = st.text_area("Description", placeholder="Provide detailed steps or context...", height=150).strip()

        submitted = st.form_submit_button("Submit Ticket", use_container_width=True)

        if submitted:
            if not title:
                st.error("Title cannot be empty.")
            elif not description:
                st.error("Description cannot be empty.")
            else:
                try:
                    ticket = client.create_ticket(
                        title=title,
                        description=description,
                        priority=priority,
                        category=category,
                    )
                    due_date = format_datetime(ticket.get("due_at"))
                    st.success(
                        f"🎉 Ticket **#{ticket['id']}** created successfully!\n\n"
                        f"**Category:** {ticket.get('category', 'other').capitalize()} | "
                        f"**Priority:** {ticket['priority'].upper()} | "
                        f"**SLA Due Date:** {due_date}"
                    )
                    st.session_state.last_created_ticket_id = ticket["id"]
                except SessionExpiredError:
                    st.session_state.clear()
                    st.session_state.session_expired_message = "Session expired, please log in again"
                    st.rerun()
                except APIConnectionError as e:
                    st.error(e.message)
                except APIError as e:
                    st.error(e.message)

    if st.session_state.get("last_created_ticket_id"):
        created_id = st.session_state.last_created_ticket_id
        if st.button(f"Go to Ticket #{created_id}", key="go_to_created_ticket"):
            st.session_state.selected_ticket_id = created_id
            st.session_state.current_page = "Ticket Detail"
            del st.session_state["last_created_ticket_id"]
            st.rerun()
