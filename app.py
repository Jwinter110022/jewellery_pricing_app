from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.db import get_connection, init_db
from src.ui import commissions, dashboard, settings, stones, workshops


# Load environment variables from local .env file.
load_dotenv(dotenv_path=Path(__file__).parent / ".env")


st.set_page_config(page_title="Jewellery Pricing", page_icon="💍", layout="wide")


def main() -> None:
    st.title("💍 Jewellery Pricing App")
    st.caption("Local-only pricing for commissions and workshops")

    conn = get_connection()
    init_db(conn)

    page = st.sidebar.radio(
        "Navigate",
        ["Dashboard", "Settings", "Stone Catalog", "Commission Quotes", "Workshop Pricing"],
    )

    if page == "Dashboard":
        dashboard.render(conn)
    elif page == "Settings":
        settings.render(conn)
    elif page == "Stone Catalog":
        stones.render(conn)
    elif page == "Commission Quotes":
        commissions.render(conn)
    elif page == "Workshop Pricing":
        workshops.render(conn)


if __name__ == "__main__":
    main()
