import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pandas as pd
import streamlit as st

from src.db import get_all_settings, list_commission_quotes, list_stones, save_commission_quote
from src.pricing import calculate_commission, calculate_estimate_range
from src.providers.metals_api import get_prices_with_cache

SYMBOLS = ["XAG", "XAU", "XPT"]


def _build_quote_html(payload: dict, breakdown: dict) -> str:
    created = datetime.now().strftime("%Y-%m-%d %H:%M")
    document_type = str(payload.get("quote_type", "quote")).capitalize()
    stone_rows = ""
    for line in breakdown.get("stone_lines", []):
        stone_rows += (
            f"<tr><td>{line['label']}</td><td>{line['qty']}</td>"
            f"<td>£{line['unit_cost_gbp']:.2f}</td><td>{line['markup_pct']:.1f}%</td>"
            f"<td>£{line['line_cost_gbp']:.2f}</td></tr>"
        )

    return f"""
<!doctype html>
<html>
<head>
<meta charset='utf-8' />
<title>Commission Quote</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 30px; color: #1f2937; }}
h1, h2 {{ margin-bottom: 8px; }}
.small {{ color: #6b7280; font-size: 0.9em; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; }}
.total {{ font-size: 1.2em; font-weight: bold; margin-top: 16px; }}
</style>
</head>
<body>
    <h1>Commission {document_type}</h1>
  <div class='small'>Generated: {created}</div>
  <p><strong>Customer:</strong> {payload.get('customer_name') or 'N/A'}<br/>
     <strong>Metal:</strong> {payload.get('metal_symbol')}<br/>
     <strong>Alloy:</strong> {payload.get('alloy_label') or 'N/A'}<br/>
     <strong>Weight:</strong> {payload.get('weight_grams')} g</p>

  <h2>Stones</h2>
  <table>
    <tr><th>Stone</th><th>Qty</th><th>Unit Cost</th><th>Markup</th><th>Line Cost</th></tr>
    {stone_rows or '<tr><td colspan="5">No stones</td></tr>'}
  </table>

  <h2>Breakdown</h2>
  <table>
    <tr><td>Metal Cost</td><td>£{breakdown['metal_cost_gbp']:.2f}</td></tr>
    <tr><td>Stone Cost</td><td>£{breakdown['stone_cost_gbp']:.2f}</td></tr>
        <tr><td>Supplier Markup ({breakdown.get('supplier_markup_pct', 0):.1f}%)</td><td>£{breakdown.get('supplier_markup_cost_gbp', 0):.2f}</td></tr>
    <tr><td>Labour Cost</td><td>£{breakdown['labour_cost_gbp']:.2f}</td></tr>
    <tr><td>Overhead</td><td>£{breakdown['overhead_cost_gbp']:.2f}</td></tr>
    <tr><td>Profit</td><td>£{breakdown['profit_cost_gbp']:.2f}</td></tr>
    <tr><td>VAT</td><td>£{breakdown['vat_amount_gbp']:.2f}</td></tr>
        <tr><td>Deposit Due Now ({breakdown['deposit_pct']:.1f}%)</td><td>£{breakdown['deposit_due_gbp']:.2f}</td></tr>
        <tr><td>Remaining Balance</td><td>£{breakdown['remaining_balance_gbp']:.2f}</td></tr>
  </table>

    {f"<p><strong>Estimate Range:</strong> £{breakdown['estimate_min_gbp']:.2f} - £{breakdown['estimate_max_gbp']:.2f}<br/><strong>Valid Until:</strong> {breakdown.get('estimate_valid_until','')}</p>" if payload.get('quote_type') == 'estimate' else ""}

  <p class='total'>Final Price: £{breakdown['final_price_gbp']:.2f}</p>
</body>
</html>
"""


def render(conn: sqlite3.Connection, fixed_quote_type: str | None = None) -> None:
    normalized_mode = (fixed_quote_type or "").strip().lower()
    if normalized_mode == "estimate":
        st.subheader("Commission Estimate Builder")
    else:
        st.subheader("Commission Quote Builder")

    settings = get_all_settings(conn)
    prices, warning = get_prices_with_cache(conn, SYMBOLS)
    if warning:
        st.warning(warning)

    available_metals = [s for s in SYMBOLS if s in prices]
    if not available_metals:
        st.error("No metal prices available yet. Open Dashboard and refresh prices.")
        return

    stones_rows = list_stones(conn)
    stone_options = {
        int(row["id"]): f"{row['stone_type']} | {row['size_mm_or_carat']} | {row['grade']} | £{float(row['cost_gbp']):.2f}"
        for row in stones_rows
    }

    with st.form("commission_form"):
        col1, col2 = st.columns(2)

        with col1:
            if normalized_mode in {"quote", "estimate"}:
                document_type = "Estimate" if normalized_mode == "estimate" else "Quote"
                st.caption(f"Document type: {document_type}")
            else:
                document_type = st.radio(
                    "Document type",
                    options=["Quote", "Estimate"],
                    horizontal=True,
                )
            customer_name = st.text_input("Customer name (optional)")
            metal_symbol = st.selectbox("Metal", available_metals)
            alloy_label = st.text_input("Alloy label")
            metal_multiplier = st.number_input(
                "Metal multiplier (alloy factor)",
                min_value=0.1,
                value=1.0,
                step=0.05,
            )
            weight_grams = st.number_input("Weight (grams)", min_value=0.0, value=10.0, step=0.1)
            labour_hours = st.number_input("Labour hours", min_value=0.0, value=2.0, step=0.25)

        with col2:
            selected_ids = st.multiselect(
                "Stones",
                options=list(stone_options.keys()),
                format_func=lambda sid: stone_options[sid],
            )
            qty_map: dict[int, int] = {}
            markup_map: dict[int, float] = {}
            for stone_id in selected_ids:
                row = next(r for r in stones_rows if int(r["id"]) == int(stone_id))
                q_col, m_col = st.columns(2)
                with q_col:
                    qty_map[stone_id] = int(
                        st.number_input(
                            f"Qty for #{stone_id}",
                            min_value=1,
                            value=1,
                            key=f"qty_{stone_id}",
                        )
                    )
                with m_col:
                    markup_map[stone_id] = float(
                        st.number_input(
                            f"Markup % for #{stone_id}",
                            min_value=0.0,
                            value=float(row["default_markup_pct"]),
                            key=f"markup_{stone_id}",
                        )
                    )

            apply_vat_override = st.checkbox("Override VAT for this quote", value=False)
            quote_vat_enabled = settings["vat_enabled"]
            quote_vat_rate = settings["vat_rate_pct"]
            if apply_vat_override:
                quote_vat_enabled = st.checkbox("Apply VAT", value=settings["vat_enabled"])
                quote_vat_rate = st.number_input(
                    "VAT rate %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(settings["vat_rate_pct"]),
                )

            deposit_pct = st.number_input(
                "Deposit due now (%)",
                min_value=0.0,
                max_value=100.0,
                value=float(settings["commission_deposit_pct"]),
                step=1.0,
            )

            estimate_variance_pct = float(settings["estimate_variance_pct"])
            if document_type == "Estimate":
                estimate_variance_pct = st.number_input(
                    "Estimate variance (%)",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(settings["estimate_variance_pct"]),
                    step=1.0,
                )

        calculate_label = "Calculate estimate" if document_type == "Estimate" else "Calculate quote"
        calculate = st.form_submit_button(calculate_label, type="primary")

    if calculate:
        spot = float(prices[metal_symbol]["price_gbp_per_oz"])

        stone_items = []
        for stone_id in selected_ids:
            row = next(r for r in stones_rows if int(r["id"]) == int(stone_id))
            stone_items.append(
                {
                    "stone_id": int(stone_id),
                    "qty": int(qty_map.get(stone_id, 1)),
                    "applied_markup_pct": float(markup_map.get(stone_id, row["default_markup_pct"])),
                    "unit_cost_gbp": float(row["cost_gbp"]),
                    "label": f"{row['stone_type']} {row['size_mm_or_carat']} {row['grade']}",
                }
            )

        breakdown = calculate_commission(
            weight_grams=weight_grams,
            spot_gbp_per_oz=spot,
            troy_oz_to_grams=settings["troy_oz_to_grams"],
            metal_multiplier=metal_multiplier,
            waste_pct=settings["metal_waste_pct"],
            stone_items=stone_items,
            labour_hours=labour_hours,
            labour_rate_gbp_per_hr=settings["labour_rate_gbp_per_hr"],
            supplier_markup_pct=settings["supplier_markup_pct"],
            overhead_pct=settings["overhead_pct"],
            target_profit_margin_pct=settings["target_profit_margin_pct"],
            vat_enabled=quote_vat_enabled,
            vat_rate_pct=quote_vat_rate,
            deposit_pct=deposit_pct,
        )

        if document_type == "Estimate":
            estimate_range = calculate_estimate_range(
                breakdown["final_price_gbp"],
                estimate_variance_pct,
            )
            valid_until = (datetime.now(UTC) + timedelta(days=int(settings["estimate_valid_days"]))).strftime(
                "%Y-%m-%d"
            )
            breakdown.update(estimate_range)
            breakdown["estimate_valid_until"] = valid_until

        if document_type == "Estimate":
            st.success(
                f"Estimate Range: £{breakdown['estimate_min_gbp']:.2f} - £{breakdown['estimate_max_gbp']:.2f}"
            )
            st.info(
                f"Reference Price: £{breakdown['final_price_gbp']:.2f} | "
                f"Valid until: {breakdown['estimate_valid_until']}"
            )
        else:
            st.success(f"Final Price: £{breakdown['final_price_gbp']:.2f}")
            st.info(
                f"Deposit Due Now: £{breakdown['deposit_due_gbp']:.2f} | "
                f"Remaining Balance: £{breakdown['remaining_balance_gbp']:.2f}"
            )

        breakdown_table = pd.DataFrame(
            [
                ["Metal", breakdown["metal_cost_gbp"]],
                ["Stones", breakdown["stone_cost_gbp"]],
                [f"Supplier Markup ({breakdown.get('supplier_markup_pct', 0):.1f}%)", breakdown.get("supplier_markup_cost_gbp", 0.0)],
                ["Labour", breakdown["labour_cost_gbp"]],
                ["Overhead", breakdown["overhead_cost_gbp"]],
                ["Profit", breakdown["profit_cost_gbp"]],
                ["VAT", breakdown["vat_amount_gbp"]],
                [f"Deposit ({breakdown['deposit_pct']:.1f}%)", breakdown["deposit_due_gbp"]],
                ["Remaining Balance", breakdown["remaining_balance_gbp"]],
                ["Final", breakdown["final_price_gbp"]],
            ],
            columns=["Item", "GBP"],
        )
        if document_type == "Estimate":
            breakdown_table = pd.concat(
                [
                    breakdown_table,
                    pd.DataFrame(
                        [
                            [
                                f"Estimate Min (-{breakdown['estimate_variance_pct']:.1f}%)",
                                breakdown["estimate_min_gbp"],
                            ],
                            [
                                f"Estimate Max (+{breakdown['estimate_variance_pct']:.1f}%)",
                                breakdown["estimate_max_gbp"],
                            ],
                        ],
                        columns=["Item", "GBP"],
                    ),
                ],
                ignore_index=True,
            )
        st.dataframe(breakdown_table, width="stretch", hide_index=True)

        quote_payload = {
            "quote_type": "estimate" if document_type == "Estimate" else "quote",
            "customer_name": customer_name.strip() or None,
            "metal_symbol": metal_symbol,
            "alloy_label": alloy_label.strip(),
            "weight_grams": float(weight_grams),
            "labour_hours": float(labour_hours),
            "settings_snapshot": {
                "labour_rate_gbp_per_hr": settings["labour_rate_gbp_per_hr"],
                "metal_waste_pct": settings["metal_waste_pct"],
                "supplier_markup_pct": settings["supplier_markup_pct"],
                "overhead_pct": settings["overhead_pct"],
                "target_profit_margin_pct": settings["target_profit_margin_pct"],
                "vat_enabled": quote_vat_enabled,
                "vat_rate_pct": quote_vat_rate,
                "commission_deposit_pct": deposit_pct,
                "estimate_variance_pct": estimate_variance_pct,
                "estimate_valid_days": settings["estimate_valid_days"],
                "troy_oz_to_grams": settings["troy_oz_to_grams"],
                "metal_multiplier": metal_multiplier,
                "spot_gbp_per_oz": spot,
            },
            "breakdown": breakdown,
        }

        save_button_label = (
            "Save estimate to history" if document_type == "Estimate" else "Save quote to history"
        )
        if st.button(save_button_label):
            quote_id = save_commission_quote(conn, quote_payload, stone_items)
            st.success(f"{document_type} saved with ID #{quote_id}")

        html = _build_quote_html(quote_payload, breakdown)
        st.download_button(
            f"Download printable {document_type.lower()} (HTML)",
            data=html.encode("utf-8"),
            file_name=f"commission_{document_type.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html",
            mime="text/html",
        )

    st.divider()
    st.markdown("### Quote History")
    history_rows = list_commission_quotes(conn)
    if history_rows:
        history_df = pd.DataFrame([dict(r) for r in history_rows])
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
        filtered_df["quote_type"] = filtered_df["quote_type"].fillna("quote").str.capitalize()
        filtered_df["created_at"] = filtered_df["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        csv_bytes = filtered_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Export quote history CSV",
            data=csv_bytes,
            file_name="commission_quote_history.csv",
            mime="text/csv",
        )
        st.dataframe(filtered_df, width="stretch", hide_index=True)
    else:
        st.caption("No saved quotes yet.")
