import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from src.db import (
    get_all_settings,
    list_workshop_quotes,
    list_workshop_templates,
    save_workshop_quote,
    upsert_workshop_template,
    delete_workshop_template,
)
from src.pricing import calculate_workshop_price
from src.providers.metals_api import get_prices_with_cache

SYMBOLS = ["XAG", "XAU", "XPT"]


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Workshop Pricing")

    settings = get_all_settings(conn)
    prices, warning = get_prices_with_cache(conn, SYMBOLS)
    if warning:
        st.warning(warning)

    available_metals = [s for s in SYMBOLS if s in prices]
    if not available_metals:
        st.error("No metal prices available yet. Open Dashboard and refresh prices.")
        return

    templates = list_workshop_templates(conn)
    template_names = [row["name"] for row in templates]
    selected_template_name = st.selectbox(
        "Load template (optional)",
        options=["(None)"] + template_names,
    )

    template_defaults = {
        "attendees": 6,
        "grams_included_per_person": 8.0,
        "waste_pct": settings["metal_waste_pct"],
        "tutor_hours": 3.0,
        "consumables_per_person": 4.0,
        "venue_cost": 0.0,
        "metal_symbol": available_metals[0],
        "vat_enabled": settings["vat_enabled"],
        "vat_rate_pct": settings["vat_rate_pct"],
    }

    if selected_template_name != "(None)":
        selected_row = next((row for row in templates if row["name"] == selected_template_name), None)
        if selected_row is not None:
            try:
                parsed = json.loads(selected_row["template_json"])
                template_defaults.update(parsed)
            except json.JSONDecodeError:
                st.warning("Template data is invalid JSON and could not be loaded.")

    with st.form("workshop_form"):
        col1, col2 = st.columns(2)
        with col1:
            template_name_to_save = st.text_input(
                "Template name (for save/update)",
                value="" if selected_template_name == "(None)" else selected_template_name,
            )
            attendees = int(
                st.number_input(
                    "Attendees",
                    min_value=1,
                    value=int(template_defaults["attendees"]),
                )
            )
            grams_included = st.number_input(
                "Grams included per person",
                min_value=0.0,
                value=float(template_defaults["grams_included_per_person"]),
                step=0.1,
            )
            metal_symbol = st.selectbox(
                "Metal",
                options=available_metals,
                index=available_metals.index(template_defaults["metal_symbol"])
                if template_defaults["metal_symbol"] in available_metals
                else 0,
            )
            waste_pct = st.number_input(
                "Waste (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(template_defaults["waste_pct"]),
                step=0.5,
            )

        with col2:
            tutor_hours = st.number_input(
                "Tutor hours",
                min_value=0.0,
                value=float(template_defaults["tutor_hours"]),
                step=0.25,
            )
            consumables_per_person = st.number_input(
                "Consumables per person (GBP)",
                min_value=0.0,
                value=float(template_defaults["consumables_per_person"]),
                step=0.5,
            )
            venue_cost = st.number_input(
                "Venue cost (GBP, optional)",
                min_value=0.0,
                value=float(template_defaults["venue_cost"]),
                step=1.0,
            )
            vat_enabled = st.checkbox("Apply VAT", value=bool(template_defaults["vat_enabled"]))
            vat_rate_pct = st.number_input(
                "VAT rate (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(template_defaults["vat_rate_pct"]),
                step=0.5,
            )

        col_a, col_b, col_c = st.columns(3)
        calculate = col_a.form_submit_button("Calculate", type="primary")
        save_template = col_b.form_submit_button("Save/Update template")
        save_quote = col_c.form_submit_button("Save workshop quote")

    inputs_payload = {
        "attendees": attendees,
        "grams_included_per_person": grams_included,
        "waste_pct": waste_pct,
        "tutor_hours": tutor_hours,
        "consumables_per_person": consumables_per_person,
        "venue_cost": venue_cost,
        "metal_symbol": metal_symbol,
        "vat_enabled": vat_enabled,
        "vat_rate_pct": vat_rate_pct,
    }

    if save_template:
        if not template_name_to_save.strip():
            st.error("Template name is required to save.")
        else:
            upsert_workshop_template(conn, template_name_to_save.strip(), inputs_payload)
            st.success("Template saved.")
            st.rerun()

    if selected_template_name != "(None)":
        selected_row = next((row for row in templates if row["name"] == selected_template_name), None)
        if selected_row is not None:
            if st.button("Delete selected template"):
                delete_workshop_template(conn, int(selected_row["id"]))
                st.success("Template deleted.")
                st.rerun()

    if calculate or save_quote:
        spot = float(prices[metal_symbol]["price_gbp_per_oz"])
        breakdown = calculate_workshop_price(
            attendees=attendees,
            grams_included_per_person=grams_included,
            waste_pct=waste_pct,
            spot_gbp_per_oz=spot,
            troy_oz_to_grams=settings["troy_oz_to_grams"],
            tutor_hours=tutor_hours,
            labour_rate_gbp_per_hr=settings["labour_rate_gbp_per_hr"],
            consumables_per_person=consumables_per_person,
            venue_cost=venue_cost,
            supplier_markup_pct=settings["supplier_markup_pct"],
            overhead_pct=settings["overhead_pct"],
            target_profit_margin_pct=settings["target_profit_margin_pct"],
            vat_enabled=vat_enabled,
            vat_rate_pct=vat_rate_pct,
        )

        st.success(
            f"Per-person: £{breakdown['per_person_gbp']:.2f} | Total: £{breakdown['final_total_gbp']:.2f}"
        )
        st.dataframe(
            pd.DataFrame(
                [
                    ["Metal", breakdown["metal_cost_gbp"]],
                    ["Tutor", breakdown["tutor_cost_gbp"]],
                    ["Consumables", breakdown["consumables_total_gbp"]],
                    [f"Supplier Markup ({breakdown.get('supplier_markup_pct', 0):.1f}%)", breakdown.get("supplier_markup_cost_gbp", 0.0)],
                    ["Venue", breakdown["venue_cost_gbp"]],
                    ["Overhead", breakdown["overhead_cost_gbp"]],
                    ["Profit", breakdown["profit_cost_gbp"]],
                    ["VAT", breakdown["vat_amount_gbp"]],
                    ["Final Total", breakdown["final_total_gbp"]],
                    ["Per Person", breakdown["per_person_gbp"]],
                ],
                columns=["Item", "GBP"],
            ),
            hide_index=True,
            width="stretch",
        )

        if save_quote:
            quote_id = save_workshop_quote(
                conn,
                None if selected_template_name == "(None)" else selected_template_name,
                inputs_payload,
                breakdown,
            )
            st.success(f"Workshop quote saved with ID #{quote_id}")

    st.divider()
    st.markdown("### Recent Workshop Quotes")
    history_rows = list_workshop_quotes(conn)
    if history_rows:
        history_df = pd.DataFrame([dict(row) for row in history_rows])
        history_df["created_at"] = pd.to_datetime(history_df["created_at"], errors="coerce", utc=True)

        range_choice = st.selectbox(
            "History range",
            options=["All", "Last 7 days", "Last 30 days", "Last 90 days"],
            index=2,
        )

        filtered_df = history_df.copy()
        days_map = {"Last 7 days": 7, "Last 30 days": 30, "Last 90 days": 90}
        if range_choice in days_map:
            cutoff = datetime.now(UTC) - timedelta(days=days_map[range_choice])
            filtered_df = filtered_df[filtered_df["created_at"] >= cutoff]

        filtered_df = filtered_df.sort_values("created_at", ascending=False)
        filtered_df["created_at"] = filtered_df["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export workshop history CSV",
            data=csv_bytes,
            file_name="workshop_quote_history.csv",
            mime="text/csv",
        )
        st.dataframe(filtered_df, hide_index=True, width="stretch")
    else:
        st.caption("No saved workshop quotes yet.")
