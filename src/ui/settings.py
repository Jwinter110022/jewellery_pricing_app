import sqlite3

import streamlit as st

from src.db import get_all_settings, save_settings


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Settings")

    current = get_all_settings(conn)

    with st.form("settings_form"):
        col1, col2 = st.columns(2)
        with col1:
            labour_rate = st.number_input(
                "Labour rate (GBP/hr)",
                min_value=0.0,
                value=float(current["labour_rate_gbp_per_hr"]),
                step=1.0,
            )
            vat_enabled = st.checkbox("Enable VAT", value=bool(current["vat_enabled"]))
            vat_rate = st.number_input(
                "VAT rate (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(current["vat_rate_pct"]),
                step=0.5,
            )
            supplier_markup_pct = st.number_input(
                "Supplier markup on materials (%)",
                min_value=0.0,
                max_value=500.0,
                value=float(current["supplier_markup_pct"]),
                step=0.5,
            )
            commission_deposit_pct = st.number_input(
                "Commission deposit (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(current["commission_deposit_pct"]),
                step=1.0,
            )
            estimate_variance_pct = st.number_input(
                "Estimate variance (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(current["estimate_variance_pct"]),
                step=1.0,
                help="Used to show an estimate range (± variance %).",
            )
            estimate_valid_days = st.number_input(
                "Estimate validity (days)",
                min_value=1,
                max_value=90,
                value=int(current["estimate_valid_days"]),
                step=1,
            )
            metal_waste_pct = st.number_input(
                "Metal waste (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(current["metal_waste_pct"]),
                step=0.5,
            )

        with col2:
            overhead_pct = st.number_input(
                "Overhead (%)",
                min_value=0.0,
                max_value=300.0,
                value=float(current["overhead_pct"]),
                step=0.5,
            )
            profit_pct = st.number_input(
                "Target profit margin (%)",
                min_value=0.0,
                max_value=500.0,
                value=float(current["target_profit_margin_pct"]),
                step=0.5,
            )
            troy_oz_to_grams = st.number_input(
                "Troy oz to grams conversion",
                min_value=0.0001,
                value=float(current["troy_oz_to_grams"]),
                step=0.0001,
                format="%.7f",
            )
            cache_ttl = st.number_input(
                "Price cache refresh age (minutes)",
                min_value=1,
                max_value=1440,
                value=int(current["price_cache_ttl_minutes"]),
                step=1,
            )

        submitted = st.form_submit_button("Save settings", type="primary")

    if submitted:
        save_settings(
            conn,
            {
                "labour_rate_gbp_per_hr": labour_rate,
                "vat_enabled": vat_enabled,
                "vat_rate_pct": vat_rate,
                "supplier_markup_pct": supplier_markup_pct,
                "commission_deposit_pct": commission_deposit_pct,
                "estimate_variance_pct": estimate_variance_pct,
                "estimate_valid_days": estimate_valid_days,
                "metal_waste_pct": metal_waste_pct,
                "overhead_pct": overhead_pct,
                "target_profit_margin_pct": profit_pct,
                "troy_oz_to_grams": troy_oz_to_grams,
                "price_cache_ttl_minutes": cache_ttl,
            },
        )
        st.success("Settings saved.")
