import io
import sqlite3

import pandas as pd
import streamlit as st

from src.db import add_stone, delete_stone, import_stones_from_df, list_stones, update_stone

CSV_COLUMNS = [
    "stone_type",
    "size_mm_or_carat",
    "grade",
    "supplier",
    "cost_gbp",
    "default_markup_pct",
    "notes",
]


def _empty_stone() -> dict[str, object]:
    return {
        "stone_type": "",
        "size_mm_or_carat": "",
        "grade": "",
        "supplier": "",
        "cost_gbp": 0.0,
        "default_markup_pct": 0.0,
        "notes": "",
    }


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Stone Catalog")

    tab1, tab2, tab3 = st.tabs(["Catalog", "Add stone", "CSV import/export"])

    with tab1:
        rows = list_stones(conn)
        if not rows:
            st.info("No stones yet. Add your first stone in the next tab.")
        else:
            df = pd.DataFrame([dict(row) for row in rows])
            st.dataframe(
                df[
                    [
                        "id",
                        "stone_type",
                        "size_mm_or_carat",
                        "grade",
                        "supplier",
                        "cost_gbp",
                        "default_markup_pct",
                        "notes",
                    ]
                ],
                width="stretch",
                hide_index=True,
            )

            selected_id = st.selectbox(
                "Select stone to edit/delete",
                options=[int(row["id"]) for row in rows],
                format_func=lambda sid: f"#{sid} - {next(r['stone_type'] for r in rows if r['id'] == sid)}",
            )
            selected = next(row for row in rows if row["id"] == selected_id)

            with st.form("edit_stone_form"):
                col1, col2 = st.columns(2)
                with col1:
                    stone_type = st.text_input("Stone type", value=selected["stone_type"])
                    size = st.text_input("Size (mm or carat)", value=selected["size_mm_or_carat"])
                    grade = st.text_input("Grade", value=selected["grade"])
                    supplier = st.text_input("Supplier", value=selected["supplier"])
                with col2:
                    cost = st.number_input("Cost (GBP)", min_value=0.0, value=float(selected["cost_gbp"]))
                    markup = st.number_input(
                        "Default markup (%)",
                        min_value=0.0,
                        value=float(selected["default_markup_pct"]),
                    )
                    notes = st.text_area("Notes", value=selected["notes"] or "")

                save_edit = st.form_submit_button("Save changes", type="primary")

            col_a, col_b = st.columns([1, 4])
            with col_a:
                delete_click = st.button("Delete stone", type="secondary")

            if save_edit:
                update_stone(
                    conn,
                    selected_id,
                    {
                        "stone_type": stone_type,
                        "size_mm_or_carat": size,
                        "grade": grade,
                        "supplier": supplier,
                        "cost_gbp": cost,
                        "default_markup_pct": markup,
                        "notes": notes,
                    },
                )
                st.success("Stone updated.")
                st.rerun()

            if delete_click:
                delete_stone(conn, selected_id)
                st.success("Stone deleted.")
                st.rerun()

    with tab2:
        with st.form("add_stone_form"):
            col1, col2 = st.columns(2)
            empty = _empty_stone()
            with col1:
                stone_type = st.text_input("Stone type", value=str(empty["stone_type"]))
                size = st.text_input("Size (mm or carat)", value=str(empty["size_mm_or_carat"]))
                grade = st.text_input("Grade", value=str(empty["grade"]))
                supplier = st.text_input("Supplier", value=str(empty["supplier"]))
            with col2:
                cost = st.number_input("Cost (GBP)", min_value=0.0, value=float(empty["cost_gbp"]))
                markup = st.number_input(
                    "Default markup (%)",
                    min_value=0.0,
                    value=float(empty["default_markup_pct"]),
                )
                notes = st.text_area("Notes", value=str(empty["notes"]))

            submit_add = st.form_submit_button("Add stone", type="primary")

        if submit_add:
            if not stone_type.strip():
                st.error("Stone type is required.")
            else:
                add_stone(
                    conn,
                    {
                        "stone_type": stone_type,
                        "size_mm_or_carat": size,
                        "grade": grade,
                        "supplier": supplier,
                        "cost_gbp": cost,
                        "default_markup_pct": markup,
                        "notes": notes,
                    },
                )
                st.success("Stone added.")
                st.rerun()

    with tab3:
        template_df = pd.DataFrame(
            [
                {
                    "stone_type": "Sapphire",
                    "size_mm_or_carat": "2.5mm",
                    "grade": "AA",
                    "supplier": "Example Gems Ltd",
                    "cost_gbp": 12.5,
                    "default_markup_pct": 40,
                    "notes": "Round cut",
                }
            ],
            columns=CSV_COLUMNS,
        )

        template_csv = template_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download CSV template",
            data=template_csv,
            file_name="stone_catalog_template.csv",
            mime="text/csv",
        )

        uploaded = st.file_uploader("Import stones CSV", type=["csv"])
        if uploaded is not None:
            try:
                import_df = pd.read_csv(uploaded)
                count = import_stones_from_df(conn, import_df)
                st.success(f"Imported {count} stones.")
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to import CSV: {exc}")

        rows = list_stones(conn)
        if rows:
            export_df = pd.DataFrame([dict(row) for row in rows])
            csv_bytes = export_df[CSV_COLUMNS].to_csv(index=False).encode("utf-8")
            st.download_button(
                "Export current catalog CSV",
                data=csv_bytes,
                file_name="stone_catalog_export.csv",
                mime="text/csv",
            )
