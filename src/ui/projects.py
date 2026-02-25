import json
import sqlite3
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import streamlit as st

from src.db import (
    add_completed_project,
    get_commission_quote,
    get_completed_project,
    list_commission_logs,
    list_completed_project_cost_rows,
    list_completed_projects,
)


def _safe_json(payload: str | None) -> dict[str, Any]:
    if not payload:
        return {}
    try:
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _build_quote_label(row: sqlite3.Row) -> str:
    created = pd.to_datetime(row["created_at"], errors="coerce", utc=True)
    created_text = created.strftime("%Y-%m-%d") if pd.notna(created) else "Unknown date"
    quote_type = str(row["quote_type"] or "quote").capitalize()
    customer = str(row["customer_name"] or "No customer")
    total = float(row["final_price_gbp"])
    return f"#{int(row['id'])} | {created_text} | {quote_type} | {customer} | £{total:,.2f}"


def _prefill_cost_rows_from_breakdown(breakdown: dict[str, Any], fallback_total: float) -> pd.DataFrame:
    mapping = [
        ("Metal", "metal_cost_gbp"),
        ("Stones", "stone_cost_gbp"),
        ("Supplier Markup", "supplier_markup_cost_gbp"),
        ("Labour", "labour_cost_gbp"),
        ("Overhead", "overhead_cost_gbp"),
        ("Profit", "profit_cost_gbp"),
        ("VAT", "vat_amount_gbp"),
    ]

    rows: list[dict[str, Any]] = []
    for label, key in mapping:
        value = breakdown.get(key)
        if isinstance(value, (int, float)):
            rows.append(
                {
                    "category": label,
                    "quoted_cost_gbp": float(value),
                    "actual_cost_gbp": float(value),
                }
            )

    if not rows:
        rows.append(
            {
                "category": "Total",
                "quoted_cost_gbp": float(fallback_total),
                "actual_cost_gbp": float(fallback_total),
            }
        )

    return pd.DataFrame(rows)


def _ensure_cost_rows_state(selected_quote_id: int | None, quote_lookup: dict[int, sqlite3.Row]) -> None:
    if "completed_project_cost_rows" not in st.session_state:
        st.session_state["completed_project_cost_rows"] = pd.DataFrame(
            [{"category": "Total", "quoted_cost_gbp": 0.0, "actual_cost_gbp": 0.0}]
        )

    if "completed_project_last_quote_id" not in st.session_state:
        st.session_state["completed_project_last_quote_id"] = None

    if st.session_state["completed_project_last_quote_id"] != selected_quote_id:
        quote_row = quote_lookup.get(selected_quote_id) if selected_quote_id is not None else None
        if quote_row is not None:
            breakdown = _safe_json(quote_row["breakdown_json"])
            fallback_total = float(quote_row["final_price_gbp"])
            st.session_state["completed_project_cost_rows"] = _prefill_cost_rows_from_breakdown(
                breakdown,
                fallback_total,
            )
        else:
            st.session_state["completed_project_cost_rows"] = pd.DataFrame(
                [{"category": "Total", "quoted_cost_gbp": 0.0, "actual_cost_gbp": 0.0}]
            )

        st.session_state["completed_project_last_quote_id"] = selected_quote_id


def _normalise_cost_rows(df: pd.DataFrame) -> pd.DataFrame:
    normalised = df.copy()
    for column in ["quoted_cost_gbp", "actual_cost_gbp"]:
        normalised[column] = pd.to_numeric(normalised[column], errors="coerce").fillna(0.0)
    normalised["category"] = normalised["category"].astype(str).str.strip()
    normalised = normalised[normalised["category"] != ""].reset_index(drop=True)
    normalised["variance_gbp"] = normalised["actual_cost_gbp"] - normalised["quoted_cost_gbp"]
    return normalised


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Completed Projects")
    st.caption("Track final project outcomes against quoted estimates for this account.")

    tab_add, tab_list = st.tabs(["Add Completed Project", "Project List & Detail"])

    with tab_add:
        quote_rows = list_commission_logs(conn, limit=5000)
        quote_lookup = {int(row["id"]): row for row in quote_rows}

        quote_options: list[int | None] = [None] + list(quote_lookup.keys())
        selected_quote_id = st.selectbox(
            "Link to quote",
            options=quote_options,
            format_func=lambda quote_id: "(None)"
            if quote_id is None
            else _build_quote_label(quote_lookup[quote_id]),
            key="completed_project_quote_select",
        )

        _ensure_cost_rows_state(selected_quote_id, quote_lookup)

        col1, col2 = st.columns(2)
        with col1:
            project_name = st.text_input("Project name *", key="completed_project_name")
            customer_name = st.text_input("Customer name", key="completed_project_customer")
        with col2:
            finished_image = st.file_uploader(
                "Upload finished image",
                type=["png", "jpg", "jpeg", "webp"],
                key="completed_project_image",
            )
            notes = st.text_area("Notes", key="completed_project_notes")

        st.markdown("### Cost Variations")
        edited_rows = st.data_editor(
            st.session_state["completed_project_cost_rows"],
            hide_index=True,
            num_rows="dynamic",
            width="stretch",
            column_config={
                "category": st.column_config.TextColumn("Category", required=True),
                "quoted_cost_gbp": st.column_config.NumberColumn("Quoted £", min_value=0.0, format="£%.2f"),
                "actual_cost_gbp": st.column_config.NumberColumn("Actual £", min_value=0.0, format="£%.2f"),
            },
            key="completed_project_cost_rows_editor",
        )

        cost_rows_df = _normalise_cost_rows(pd.DataFrame(edited_rows))
        st.session_state["completed_project_cost_rows"] = cost_rows_df.drop(columns=["variance_gbp"])

        if not cost_rows_df.empty:
            st.dataframe(
                cost_rows_df[["category", "quoted_cost_gbp", "actual_cost_gbp", "variance_gbp"]],
                hide_index=True,
                width="stretch",
            )

        quoted_total = float(cost_rows_df["quoted_cost_gbp"].sum()) if not cost_rows_df.empty else 0.0
        actual_total = float(cost_rows_df["actual_cost_gbp"].sum()) if not cost_rows_df.empty else 0.0
        variance_gbp = actual_total - quoted_total
        variance_pct = (variance_gbp / quoted_total * 100.0) if quoted_total else None

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Quoted total", f"£{quoted_total:,.2f}")
        kpi2.metric("Actual total", f"£{actual_total:,.2f}")
        kpi3.metric("Variance", f"£{variance_gbp:,.2f}", None if variance_pct is None else f"{variance_pct:.2f}%")

        if st.button("Add completed project", type="primary"):
            if not project_name.strip():
                st.error("Project name is required.")
            elif cost_rows_df.empty:
                st.error("Add at least one cost variation row.")
            else:
                linked_quote = quote_lookup.get(selected_quote_id) if selected_quote_id is not None else None
                quote_summary = None
                quote_breakdown_json = None
                if linked_quote is not None:
                    quote_summary = _build_quote_label(linked_quote)
                    quote_breakdown_json = linked_quote["breakdown_json"]

                image_payload = {
                    "image_name": finished_image.name if finished_image is not None else None,
                    "image_mime": (finished_image.type or "application/octet-stream")
                    if finished_image is not None
                    else None,
                    "image_data": finished_image.getvalue() if finished_image is not None else None,
                }

                payload = {
                    "project_name": project_name.strip(),
                    "customer_name": customer_name.strip() or None,
                    "quote_id": int(selected_quote_id) if selected_quote_id is not None else None,
                    "quote_summary": quote_summary,
                    "quoted_total_gbp": quoted_total,
                    "actual_total_gbp": actual_total,
                    "variance_gbp": variance_gbp,
                    "variance_pct": variance_pct,
                    "notes": notes,
                    "quote_breakdown_json": quote_breakdown_json,
                    **image_payload,
                }

                cost_rows_payload = [
                    {
                        "category": row["category"],
                        "quoted_cost_gbp": float(row["quoted_cost_gbp"]),
                        "actual_cost_gbp": float(row["actual_cost_gbp"]),
                    }
                    for row in cost_rows_df.to_dict("records")
                ]

                project_id = add_completed_project(conn, payload, cost_rows_payload)
                st.success(f"Completed project saved with ID #{project_id}")

    with tab_list:
        project_rows = list_completed_projects(conn, limit=5000)
        if not project_rows:
            st.info("No completed projects saved yet.")
            return

        projects_df = pd.DataFrame([dict(row) for row in project_rows])
        projects_df["created_at"] = pd.to_datetime(projects_df["created_at"], errors="coerce", utc=True)

        min_dt = projects_df["created_at"].min()
        max_dt = projects_df["created_at"].max()
        default_start = min_dt.date() if pd.notna(min_dt) else date.today()
        default_end = max_dt.date() if pd.notna(max_dt) else date.today()

        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            project_search = st.text_input("Project name filter")
        with col2:
            customer_search = st.text_input("Customer filter")
        with col3:
            date_range = st.date_input(
                "Date range",
                value=(default_start, default_end),
            )

        filtered_df = projects_df.copy()
        if project_search.strip():
            filtered_df = filtered_df[
                filtered_df["project_name"].fillna("").str.lower().str.contains(project_search.strip().lower())
            ]
        if customer_search.strip():
            filtered_df = filtered_df[
                filtered_df["customer_name"].fillna("").str.lower().str.contains(customer_search.strip().lower())
            ]

        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
            start_dt = datetime.combine(start_date, datetime.min.time(), tzinfo=UTC)
            end_dt = datetime.combine(end_date, datetime.max.time(), tzinfo=UTC)
            filtered_df = filtered_df[
                (filtered_df["created_at"] >= start_dt) & (filtered_df["created_at"] <= end_dt)
            ]

        display_df = filtered_df.copy().sort_values("created_at", ascending=False)
        display_df["date"] = display_df["created_at"].dt.strftime("%Y-%m-%d")
        display_df["variance_pct"] = display_df["variance_pct"].map(
            lambda v: "" if pd.isna(v) else f"{float(v):.2f}%"
        )

        table_df = display_df[
            [
                "date",
                "project_name",
                "customer_name",
                "quote_summary",
                "quoted_total_gbp",
                "actual_total_gbp",
                "variance_gbp",
                "variance_pct",
            ]
        ].rename(
            columns={
                "customer_name": "customer",
                "quote_summary": "quote",
                "quoted_total_gbp": "quoted_total",
                "actual_total_gbp": "actual_total",
                "variance_gbp": "variance",
            }
        )

        if display_df.empty:
            st.caption("No projects match your filters.")
            return

        selected_project_id = int(display_df.iloc[0]["id"])
        try:
            selection_event = st.dataframe(
                table_df,
                hide_index=True,
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
                key="completed_projects_table",
            )
            selected_rows = selection_event.selection.rows
            if selected_rows:
                selected_project_id = int(display_df.iloc[int(selected_rows[0])]["id"])
            st.caption("Click a row to open that project detail.")
        except TypeError:
            st.dataframe(table_df, hide_index=True, width="stretch")
            selected_project_id = st.selectbox(
                "Open project detail",
                options=[int(pid) for pid in display_df["id"].tolist()],
                format_func=lambda pid: f"#{pid} - {display_df[display_df['id'] == pid]['project_name'].iloc[0]}",
            )

        project = get_completed_project(conn, int(selected_project_id))
        if project is None:
            st.error("Project not found.")
            return

        st.markdown("### Project Detail")
        st.write(
            {
                "project_name": project["project_name"],
                "customer_name": project["customer_name"],
                "linked_quote": project["quote_summary"],
                "created_at": project["created_at"],
            }
        )

        if project["image_data"]:
            st.image(project["image_data"], caption=project["image_name"] or "Finished project")

        cost_rows = list_completed_project_cost_rows(conn, int(selected_project_id))
        if cost_rows:
            cost_df = pd.DataFrame([dict(row) for row in cost_rows])
            cost_df["variance_gbp"] = cost_df["actual_cost_gbp"] - cost_df["quoted_cost_gbp"]
            st.markdown("**Cost Variance Table**")
            st.dataframe(
                cost_df[["category", "quoted_cost_gbp", "actual_cost_gbp", "variance_gbp"]],
                hide_index=True,
                width="stretch",
            )

            csv_bytes = cost_df[["category", "quoted_cost_gbp", "actual_cost_gbp", "variance_gbp"]].to_csv(
                index=False
            ).encode("utf-8")
            st.download_button(
                "Export to CSV",
                data=csv_bytes,
                file_name=f"project_{selected_project_id}_cost_rows.csv",
                mime="text/csv",
            )

            biggest_overrun_row = cost_df.sort_values("variance_gbp", ascending=False).iloc[0]
            biggest_overrun = (
                f"{biggest_overrun_row['category']} (£{float(biggest_overrun_row['variance_gbp']):,.2f})"
                if float(biggest_overrun_row["variance_gbp"]) > 0
                else "None"
            )
        else:
            biggest_overrun = "None"

        variance_value = float(project["variance_gbp"])
        variance_pct_value = project["variance_pct"]
        variance_pct_text = "N/A" if variance_pct_value is None else f"{float(variance_pct_value):.2f}%"

        k1, k2, k3 = st.columns(3)
        k1.metric("Variance (£)", f"£{variance_value:,.2f}")
        k2.metric("Variance (%)", variance_pct_text)
        k3.metric("Biggest overrun", biggest_overrun)

        st.markdown("**Linked quote breakdown (stored)**")
        stored_breakdown = _safe_json(project["quote_breakdown_json"])
        if stored_breakdown:
            breakdown_rows = [
                {"field": key, "value": value}
                for key, value in stored_breakdown.items()
                if isinstance(value, (str, int, float, bool))
            ]
            st.dataframe(pd.DataFrame(breakdown_rows), hide_index=True, width="stretch")
        else:
            if project["quote_id"] is not None:
                quote_row = get_commission_quote(conn, int(project["quote_id"]))
                if quote_row is not None:
                    quote_breakdown = _safe_json(quote_row["breakdown_json"])
                    if quote_breakdown:
                        breakdown_rows = [
                            {"field": key, "value": value}
                            for key, value in quote_breakdown.items()
                            if isinstance(value, (str, int, float, bool))
                        ]
                        st.dataframe(pd.DataFrame(breakdown_rows), hide_index=True, width="stretch")
                    else:
                        st.caption("No breakdown data available.")
                else:
                    st.caption("Linked quote not found.")
            else:
                st.caption("No linked quote.")

        st.markdown("**Notes**")
        st.write(project["notes"] or "-")
