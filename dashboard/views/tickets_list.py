import math
import streamlit as st

from dashboard.api_client import APIConnectionError, APIError, HelpdeskAPIClient, SessionExpiredError


def render_tickets_list(client: HelpdeskAPIClient) -> None:
    """Render tickets list with server-side filters, search, and pagination."""
    st.subheader("📋 Tickets")

    if "tickets_page" not in st.session_state:
        st.session_state.tickets_page = 1

    # Filters row
    col1, col2, col3, col4 = st.columns([2, 2, 3, 2])
    with col1:
        status_filter = st.selectbox(
            "Status",
            ["All", "open", "in_progress", "resolved", "closed"],
            index=0,
            key="filter_status",
        )
    with col2:
        priority_filter = st.selectbox(
            "Priority",
            ["All", "low", "medium", "high", "urgent"],
            index=0,
            key="filter_priority",
        )
    with col3:
        search_query = st.text_input("Search keyword", placeholder="Title or description...", key="filter_q").strip()
    with col4:
        st.write("")
        st.write("")
        overdue_filter = st.checkbox("Overdue only", key="filter_overdue")

    # Wire to API query parameters (no client-side filtering)
    status_param = status_filter if status_filter != "All" else None
    priority_param = priority_filter if priority_filter != "All" else None
    overdue_param = True if overdue_filter else None
    q_param = search_query if search_query else None

    page_size = 10
    current_page = st.session_state.tickets_page

    try:
        data = client.list_tickets(
            page=current_page,
            page_size=page_size,
            status=status_param,
            priority=priority_param,
            overdue=overdue_param,
            q=q_param,
        )
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

    items = data.get("items", [])
    total = data.get("total", 0)
    total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1

    if current_page > total_pages:
        st.session_state.tickets_page = total_pages
        st.rerun()

    start_idx = (current_page - 1) * page_size + 1 if total > 0 else 0
    end_idx = min(current_page * page_size, total)

    st.markdown(f"**Showing {start_idx}–{end_idx} of {total} tickets** (Page {current_page} of {total_pages})")

    if not items:
        st.info("No tickets match the selected filters.")
    else:
        # Render tickets
        for t in items:
            ticket_id = t["id"]
            title = t["title"]
            status_val = t["status"].upper()
            prio_val = t["priority"].upper()
            assignee = f"User #{t['assignee_id']}" if t.get("assignee_id") else "Unassigned"
            is_overdue = t.get("is_overdue", False)
            due_at = t.get("due_at", "No due date")

            due_display = f"<span style='color: #e53e3e; font-weight: bold;'>⚠️ {due_at} (OVERDUE)</span>" if is_overdue else f"<span>{due_at}</span>"

            with st.container():
                c1, c2, c3, c4, c5, c6 = st.columns([1, 4, 2, 2, 3, 2])
                c1.markdown(f"**#{ticket_id}**")
                c2.markdown(f"**{title}**")
                c3.markdown(f"`{status_val}`")
                c4.markdown(f"*{prio_val}*")
                c5.markdown(due_display, unsafe_allow_html=True)
                if c6.button("View", key=f"btn_ticket_{ticket_id}", use_container_width=True):
                    st.session_state.selected_ticket_id = ticket_id
                    st.session_state.current_page = "Ticket Detail"
                    st.rerun()
                st.divider()

    # Pagination controls
    p_col1, p_col2, p_col3 = st.columns([2, 4, 2])
    with p_col1:
        if st.button("⬅️ Previous", disabled=(current_page <= 1), use_container_width=True):
            st.session_state.tickets_page -= 1
            st.rerun()
    with p_col2:
        st.markdown(
            f"<div style='text-align: center; padding-top: 6px;'>Page {current_page} of {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with p_col3:
        if st.button("Next ➡️", disabled=(current_page >= total_pages), use_container_width=True):
            st.session_state.tickets_page += 1
            st.rerun()
