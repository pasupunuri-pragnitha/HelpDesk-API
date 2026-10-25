from typing import Any
import streamlit as st

from dashboard.api_client import APIConnectionError, APIError, HelpdeskAPIClient, SessionExpiredError

# Workflow transitions allowed by Helpdesk API
ALLOWED_STATUS_TRANSITIONS: dict[str, list[str]] = {
    "open": ["in_progress"],
    "in_progress": ["resolved"],
    "resolved": ["closed", "in_progress"],
    "closed": [],
}


def render_ticket_detail(client: HelpdeskAPIClient) -> None:
    """Render ticket detail view with badges, comments, history, and actions panel."""
    ticket_id = st.session_state.get("selected_ticket_id")
    if not ticket_id:
        st.warning("No ticket selected.")
        if st.button("⬅️ Return to Tickets"):
            st.session_state.current_page = "Tickets"
            st.rerun()
        return

    user = st.session_state.get("user", {})
    user_role = user.get("role", "requester")

    # Header & Back button
    col_back, _ = st.columns([2, 8])
    with col_back:
        if st.button("⬅️ Back to Tickets", key="btn_back_to_list"):
            st.session_state.current_page = "Tickets"
            st.rerun()

    # Fetch ticket details
    try:
        ticket = client.get_ticket(ticket_id)
        comments = client.get_comments(ticket_id)
        history = client.get_history(ticket_id)
    except SessionExpiredError:
        st.session_state.clear()
        st.session_state.session_expired_message = "Session expired, please log in again"
        st.rerun()
    except APIConnectionError as e:
        st.error(e.message)
        return
    except APIError as e:
        st.error(e.message)
        return

    # Title & Badges
    st.markdown(f"## #{ticket['id']} — {ticket['title']}")

    badge_cols = st.columns([2, 2, 2, 4])
    with badge_cols[0]:
        st.markdown(f"**Status:** `{ticket['status'].upper()}`")
    with badge_cols[1]:
        st.markdown(f"**Priority:** *{ticket['priority'].upper()}*")
    with badge_cols[2]:
        if ticket.get("is_overdue"):
            st.markdown("<span style='background-color: #e53e3e; color: white; padding: 4px 8px; border-radius: 4px; font-weight: bold;'>🚨 OVERDUE</span>", unsafe_allow_html=True)
        else:
            st.markdown("<span style='background-color: #38a169; color: white; padding: 4px 8px; border-radius: 4px;'>ON TIME</span>", unsafe_allow_html=True)
    with badge_cols[3]:
        due_at = ticket.get("due_at") or "None"
        if ticket.get("is_overdue"):
            st.markdown(f"**SLA Due Date:** <span style='color: #e53e3e; font-weight: bold;'>{due_at}</span>", unsafe_allow_html=True)
        else:
            st.markdown(f"**SLA Due Date:** {due_at}")

    # Metadata & Description
    with st.expander("📄 Ticket Description & Metadata", expanded=True):
        st.write(ticket["description"])
        st.divider()
        m_col1, m_col2, m_col3 = st.columns(3)
        m_col1.caption(f"Requester ID: #{ticket['requester_id']}")
        assignee_txt = f"User #{ticket['assignee_id']}" if ticket.get("assignee_id") else "Unassigned"
        m_col2.caption(f"Assignee: {assignee_txt}")
        m_col3.caption(f"Created: {ticket['created_at']}")

    # Main content layout: Left = Comments & History, Right = Actions (if agent/admin)
    if user_role in ("agent", "admin"):
        left_col, right_col = st.columns([6, 4])
    else:
        left_col = st.container()
        right_col = None

    with left_col:
        st.markdown("### 💬 Comments")
        if not comments:
            st.info("No comments yet.")
        else:
            for c in comments:
                is_internal = c.get("is_internal", False)
                author_label = f"User #{c['author_id']}"
                created_label = c.get("created_at", "")

                if is_internal:
                    st.warning(f"🔒 **[Internal]** *{author_label}* on {created_label}\n\n{c['body']}")
                else:
                    with st.chat_message("user"):
                        st.markdown(f"**{author_label}** · *{created_label}*\n\n{c['body']}")

        # Add comment box
        st.markdown("#### Add a Comment")
        with st.form(f"comment_form_{ticket_id}"):
            comment_body = st.text_area("Your comment", placeholder="Type a response...", height=90).strip()
            is_internal_flag = False
            if user_role in ("agent", "admin"):
                is_internal_flag = st.checkbox("Internal note (visible to staff only)", key=f"internal_{ticket_id}")

            post_btn = st.form_submit_button("Post Comment")
            if post_btn:
                if not comment_body:
                    st.error("Comment cannot be empty.")
                else:
                    try:
                        client.add_comment(
                            ticket_id=ticket_id,
                            body=comment_body,
                            is_internal=is_internal_flag,
                        )
                        st.success("Comment added!")
                        st.rerun()
                    except SessionExpiredError:
                        st.session_state.clear()
                        st.session_state.session_expired_message = "Session expired, please log in again"
                        st.rerun()
                    except APIConnectionError as e:
                        st.error(e.message)
                    except APIError as e:
                        st.error(e.message)

        # Status History Timeline
        st.markdown("### 📜 Status History")
        if not history:
            st.caption("No status transitions recorded.")
        else:
            for h in history:
                from_st = h.get("from_status") or "Initial Creation"
                to_st = h.get("to_status", "")
                by_user = f"User #{h['changed_by_id']}" if h.get("changed_by_id") else "System"
                h_date = h.get("created_at", "")
                st.markdown(f"- **{from_st.upper()}** ➔ **{to_st.upper()}** by *{by_user}* on `{h_date}`")

    # Actions panel (Staff only)
    if right_col is not None:
        with right_col:
            st.markdown("### ⚙️ Actions Panel")
            st.caption("Manage ticket lifecycle and assignment")

            # 1. Update Status
            st.markdown("#### Change Status")
            current_status = ticket["status"]
            allowed_next = ALLOWED_STATUS_TRANSITIONS.get(current_status, [])

            if not allowed_next:
                st.info(f"Ticket is `{current_status.upper()}`. No further transitions allowed.")
            else:
                with st.form(f"status_form_{ticket_id}"):
                    new_status = st.selectbox("Select next status", allowed_next, format_func=lambda s: s.upper())
                    status_submit = st.form_submit_button("Update Status", use_container_width=True)

                    if status_submit:
                        try:
                            client.update_ticket_status(ticket_id=ticket_id, status=new_status)
                            st.success(f"Status changed to {new_status.upper()}!")
                            st.rerun()
                        except SessionExpiredError:
                            st.session_state.clear()
                            st.session_state.session_expired_message = "Session expired, please log in again"
                            st.rerun()
                        except APIConnectionError as e:
                            st.error(e.message)
                        except APIError as e:
                            # Shows 409 message if API rejects invalid transition
                            st.error(f"Status update failed: {e.message}")

            st.divider()

            # 2. Assign Ticket
            st.markdown("#### Assign Ticket")
            agents_list: list[dict[str, Any]] = []

            # Try loading agents from users endpoint if permitted (admin role)
            if user_role == "admin":
                try:
                    all_users = client.list_users()
                    agents_list = [u for u in all_users if u.get("role") == "agent" and u.get("is_active")]
                except APIError:
                    agents_list = []

            with st.form(f"assign_form_{ticket_id}"):
                if agents_list:
                    agent_options = {f"{u['full_name']} (ID: {u['id']})": u['id'] for u in agents_list}
                    selected_agent_label = st.selectbox("Select Agent", list(agent_options.keys()))
                    chosen_agent_id = agent_options[selected_agent_label]
                else:
                    st.caption("Enter Agent User ID (listing users requires Admin role):")
                    chosen_agent_id = st.number_input("Agent ID", min_value=1, step=1, value=1)

                assign_submit = st.form_submit_button("Assign to Agent", use_container_width=True)

                if assign_submit:
                    try:
                        client.assign_ticket(ticket_id=ticket_id, assignee_id=int(chosen_agent_id))
                        st.success(f"Assigned to agent #{chosen_agent_id}!")
                        st.rerun()
                    except SessionExpiredError:
                        st.session_state.clear()
                        st.session_state.session_expired_message = "Session expired, please log in again"
                        st.rerun()
                    except APIConnectionError as e:
                        st.error(e.message)
                    except APIError as e:
                        st.error(f"Assignment failed: {e.message}")
