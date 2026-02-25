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


def _uploaded_image_payload(uploaded_file) -> dict[str, object] | None:
    if uploaded_file is None:
        return None
    return {
        "image_name": uploaded_file.name,
        "image_mime": uploaded_file.type or "application/octet-stream",
        "image_data": uploaded_file.getvalue(),
    }


def render(conn: sqlite3.Connection) -> None:
    st.subheader("Stone Catalog")

    tab1, tab2, tab3 = st.tabs(["Catalog", "Add stone", "CSV import/export"])

    with tab1:
        rows = list_stones(conn)
        if not rows:
            st.info("No stones yet. Add your first stone in the next tab.")
        else:
            df = pd.DataFrame(
                [
                    {
                        "id": int(row["id"]),
                        "stone_type": row["stone_type"],
                        "size_mm_or_carat": row["size_mm_or_carat"],
                        "grade": row["grade"],
                        "supplier": row["supplier"],
                        "cost_gbp": float(row["cost_gbp"]),
                        "default_markup_pct": float(row["default_markup_pct"]),
                        "notes": row["notes"],
                        "has_image": bool(row["image_data"]),
                    }
                    for row in rows
                ]
            )
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
                        "has_image",
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
                    if selected["image_data"]:
                        st.image(
                            selected["image_data"],
                            caption=selected["image_name"] or "Stone image",
                            width=180,
                        )
                    replace_image = st.file_uploader(
                        "Upload / replace image",
                        type=["png", "jpg", "jpeg", "webp"],
                        key=f"edit_image_{selected_id}",
                    )
                    remove_image = st.checkbox(
                        "Remove current image",
                        value=False,
                        key=f"remove_image_{selected_id}",
                    )

                save_edit = st.form_submit_button("Save changes", type="primary")

            col_a, col_b = st.columns([1, 4])
            with col_a:
                delete_click = st.button("Delete stone", type="secondary")

            if save_edit:
                existing_image_payload = {
                    "image_name": selected["image_name"],
                    "image_mime": selected["image_mime"],
                    "image_data": selected["image_data"],
                }
                uploaded_payload = _uploaded_image_payload(replace_image)
                if remove_image:
                    final_image_payload = {"image_name": None, "image_mime": None, "image_data": None}
                elif uploaded_payload is not None:
                    final_image_payload = uploaded_payload
                else:
                    final_image_payload = existing_image_payload

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
                        "image_name": final_image_payload["image_name"],
                        "image_mime": final_image_payload["image_mime"],
                        "image_data": final_image_payload["image_data"],
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
                add_image = st.file_uploader(
                    "Stone image (optional)",
                    type=["png", "jpg", "jpeg", "webp"],
                    key="add_stone_image",
                )

            submit_add = st.form_submit_button("Add stone", type="primary")

        if submit_add:
            if not stone_type.strip():
                st.error("Stone type is required.")
            else:
                add_image_payload = _uploaded_image_payload(add_image) or {
                    "image_name": None,
                    "image_mime": None,
                    "image_data": None,
                }
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
                        "image_name": add_image_payload["image_name"],
                        "image_mime": add_image_payload["image_mime"],
                        "image_data": add_image_payload["image_data"],
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
