import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from src.db import clear_commission_logs, get_quote_stone_lines, list_commission_logs


def _parse_json(payload: str | None) -> dict:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Estimate & Quote Logs")
    st.caption("All saved estimates and quotes for your signed-in account.")

    rows = list_commission_logs(conn, limit=5000)
    if not rows:
        st.info("No saved estimates or quotes yet.")
        return

    logs_df = pd.DataFrame([dict(row) for row in rows])
    logs_df["created_at"] = pd.to_datetime(logs_df["created_at"], errors="coerce", utc=True)
    logs_df["quote_type"] = logs_df["quote_type"].fillna("quote").str.lower()

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        search_text = st.text_input("Search customer / metal")
    with col2:
        type_filter = st.selectbox("Type", options=["All", "Quote", "Estimate"])
    with col3:
        range_filter = st.selectbox("Range", options=["All", "7 days", "30 days", "90 days"], index=2)

    filtered_df = logs_df.copy()

    if search_text.strip():
        search_term = search_text.strip().lower()
        customer = filtered_df["customer_name"].fillna("").str.lower()
        metal = filtered_df["metal_symbol"].fillna("").str.lower()
        filtered_df = filtered_df[customer.str.contains(search_term) | metal.str.contains(search_term)]

    if type_filter != "All":
        filtered_df = filtered_df[filtered_df["quote_type"] == type_filter.lower()]

    days_map = {"7 days": 7, "30 days": 30, "90 days": 90}
    if range_filter in days_map:
        cutoff = datetime.now(UTC) - timedelta(days=days_map[range_filter])
        filtered_df = filtered_df[filtered_df["created_at"] >= cutoff]

    filtered_df = filtered_df.sort_values("created_at", ascending=False)

    display_df = filtered_df.copy()
    display_df["quote_type"] = display_df["quote_type"].str.capitalize()
    display_df["created_at"] = display_df["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

    if not display_df.empty:
        export_df = display_df[
            [
                "id",
                "created_at",
                "quote_type",
                "customer_name",
                "metal_symbol",
                "alloy_label",
                "weight_grams",
                "labour_hours",
                "final_price_gbp",
            ]
        ]
        csv_bytes = export_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export filtered logs CSV",
            data=csv_bytes,
            file_name="estimate_quote_logs.csv",
            mime="text/csv",
        )

        st.dataframe(export_df, hide_index=True, width="stretch")

        st.markdown("### Log details")
        selected_id = st.selectbox(
            "Select log entry",
            options=[int(value) for value in filtered_df["id"].tolist()],
            format_func=lambda entry_id: f"#{entry_id}",
        )
        selected = filtered_df[filtered_df["id"] == selected_id].iloc[0]

        breakdown = _parse_json(selected.get("breakdown_json"))
        settings_snapshot = _parse_json(selected.get("settings_json"))

        st.write(
            {
                "id": int(selected["id"]),
                "created_at": selected["created_at"].strftime("%Y-%m-%d %H:%M:%S UTC")
                if pd.notna(selected["created_at"])
                else "",
                "type": str(selected.get("quote_type", "")).capitalize(),
                "customer_name": selected.get("customer_name"),
                "metal_symbol": selected.get("metal_symbol"),
                "alloy_label": selected.get("alloy_label"),
                "weight_grams": selected.get("weight_grams"),
                "labour_hours": selected.get("labour_hours"),
                "final_price_gbp": selected.get("final_price_gbp"),
            }
        )

        if breakdown:
            st.markdown("**Breakdown**")
            breakdown_rows = []
            for key, value in breakdown.items():
                if isinstance(value, (int, float, str, bool)):
                    breakdown_rows.append({"field": key, "value": value})
            if breakdown_rows:
                st.dataframe(pd.DataFrame(breakdown_rows), hide_index=True, width="stretch")

        if settings_snapshot:
            st.markdown("**Settings snapshot**")
            settings_rows = [{"field": key, "value": value} for key, value in settings_snapshot.items()]
            st.dataframe(pd.DataFrame(settings_rows), hide_index=True, width="stretch")

        stone_lines = get_quote_stone_lines(conn, int(selected_id))
        if stone_lines:
            st.markdown("**Stones in this log**")
            stone_df = pd.DataFrame(
                [
                    {
                        "stone_id": int(row["stone_id"]),
                        "stone": (
                            f"{row['stone_type']} {row['size_mm_or_carat']} {row['grade']}"
                            if row["stone_type"]
                            else f"Stone #{int(row['stone_id'])}"
                        ),
                        "qty": int(row["qty"]),
                        "unit_cost_gbp": float(row["unit_cost_gbp"]),
                        "markup_pct": float(row["applied_markup_pct"]),
                    }
                    for row in stone_lines
                ]
            )
            st.dataframe(stone_df, hide_index=True, width="stretch")
    else:
        st.caption("No logs match your filters.")

    st.divider()
    with st.expander("Danger zone: clear logs"):
        st.caption("This permanently deletes all saved estimates and quotes for your account only.")
        with st.form("clear_logs_form"):
            confirm_text = st.text_input("Type CLEAR LOGS to confirm")
            clear_submit = st.form_submit_button("Clear all estimate & quote logs")

        if clear_submit:
            if confirm_text.strip().upper() != "CLEAR LOGS":
                st.error("Type CLEAR LOGS exactly to confirm.")
            else:
                deleted = clear_commission_logs(conn)
                st.success(f"Deleted {deleted} log entries.")
                st.rerun()
