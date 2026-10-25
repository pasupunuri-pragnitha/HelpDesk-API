"""Reports and analytics view for Agents and Admins."""

from typing import Any
import pandas as pd
import streamlit as st

from dashboard.api_client import APIConnectionError, APIError, HelpdeskAPIClient, SessionExpiredError


def render_reports(client: HelpdeskAPIClient) -> None:
    """Render the analytics and reports dashboard."""
    user = st.session_state.get("user") or {}
    role = user.get("role", "")

    if role not in ("agent", "admin"):
        st.error("Access denied: Reports are only available to Agents and Admins.")
        return

    st.title("📊 HelpDesk Reports & Analytics")
    st.markdown("Real-time performance metrics and operational analytics.")

    days_window = st.sidebar.slider("Daily Volume Window (Days)", min_value=7, max_value=90, value=30, step=7)

    try:
        with st.spinner("Loading report metrics..."):
            status_data = client.get_report_tickets_by_status()
            overdue_data = client.get_report_overdue()
            resolution_data = client.get_report_resolution_time()
            ranking_data = client.get_report_agent_ranking()
            daily_data = client.get_report_daily_volume(days=days_window)
    except SessionExpiredError:
        st.session_state.clear()
        st.session_state["session_expired_message"] = "Session expired, please log in again"
        st.rerun()
    except APIConnectionError as exc:
        st.error(str(exc))
        return
    except APIError as exc:
        st.error(f"Failed to load reports: {exc.message}")
        return

    # --- KPI Cards ---
    open_count = sum(item.get("count", 0) for item in status_data if item.get("status") == "open")
    in_progress_count = sum(item.get("count", 0) for item in status_data if item.get("status") == "in_progress")
    overdue_count = len(overdue_data)

    # Resolution hours calculation (weighted by ticket_count)
    total_resolved = sum(item.get("ticket_count", 0) for item in resolution_data)
    weighted_hours = sum(item.get("avg_resolution_hours", 0.0) * item.get("ticket_count", 0) for item in resolution_data)
    avg_resolution_hours = (weighted_hours / total_resolved) if total_resolved > 0 else None

    # Display KPI metrics
    kpi_cols = st.columns(4 if avg_resolution_hours is not None else 3)
    with kpi_cols[0]:
        st.metric("Open Tickets", f"{open_count}")
    with kpi_cols[1]:
        st.metric("In Progress", f"{in_progress_count}")
    with kpi_cols[2]:
        st.metric("Overdue Tickets", f"{overdue_count}")
    if avg_resolution_hours is not None and len(kpi_cols) > 3:
        with kpi_cols[3]:
            st.metric("Avg Resolution Time", f"{avg_resolution_hours:.1f} hrs")

    st.markdown("---")

    col_chart, col_rank = st.columns([1, 1], gap="large")

    # --- Bar Chart: Tickets by Status ---
    with col_chart:
        st.subheader("Tickets by Status")
        if status_data:
            # Aggregate total by status across all priorities
            status_totals: dict[str, int] = {}
            for item in status_data:
                s = item.get("status", "unknown")
                status_totals[s] = status_totals.get(s, 0) + item.get("count", 0)

            df_status = pd.DataFrame(
                [{"Status": k.replace("_", " ").title(), "Count": v} for k, v in status_totals.items()]
            ).set_index("Status")
            st.bar_chart(df_status)
        else:
            st.info("No ticket status data available.")

    # --- Table: Agent Ranking ---
    with col_rank:
        st.subheader("Agent Rankings")
        if ranking_data:
            df_ranking = pd.DataFrame(
                [
                    {
                        "Rank": item.get("rank"),
                        "Agent": item.get("agent_name"),
                        "Resolved Tickets": item.get("resolved_count"),
                    }
                    for item in ranking_data
                ]
            )
            st.dataframe(df_ranking, hide_index=True, use_container_width=True)
        else:
            st.info("No resolved tickets or agent rankings available.")

    st.markdown("---")

    # --- Line Chart: Daily Volume ---
    st.subheader(f"Tickets Created per Day (Last {days_window} Days)")
    if daily_data:
        df_daily = pd.DataFrame(daily_data)
        if not df_daily.empty and "date" in df_daily.columns:
            df_daily = df_daily.rename(columns={"date": "Date", "ticket_count": "Tickets Created"})
            df_daily = df_daily.set_index("Date")
            st.line_chart(df_daily)
        else:
            st.info("No volume records found for this period.")
    else:
        st.info("No daily volume data available.")
