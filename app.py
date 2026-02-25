from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from src.db import (
    authenticate_user,
    create_user,
    delete_user_account,
    get_auth_connection,
    get_user_db_path,
    get_user_connection,
    init_db,
    update_user_password,
)
from src.ui import commissions, dashboard, history_logs, projects, settings, stones, workshops


# Load environment variables from local .env file.
load_dotenv(dotenv_path=Path(__file__).parent / ".env")


st.set_page_config(page_title="Jewellery Pricing", page_icon="💍", layout="wide")


def _render_auth_gate() -> bool:
    if "auth_username" not in st.session_state:
        st.session_state["auth_username"] = None

    if st.session_state["auth_username"]:
        return True

    st.subheader("Sign in")
    st.caption("Create an account or log in to access your private pricing data.")

    auth_conn = get_auth_connection()
    login_tab, signup_tab = st.tabs(["Login", "Sign up"])

    with login_tab:
        with st.form("login_form"):
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password", type="password", key="login_password")
            login_submit = st.form_submit_button("Log in", type="primary")
        if login_submit:
            authenticated_username = authenticate_user(auth_conn, login_username, login_password)
            if authenticated_username:
                st.session_state["auth_username"] = authenticated_username
                st.success("Logged in successfully.")
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with signup_tab:
        with st.form("signup_form"):
            signup_username = st.text_input("Username", key="signup_username")
            signup_password = st.text_input("Password", type="password", key="signup_password")
            signup_submit = st.form_submit_button("Create account", type="primary")
        if signup_submit:
            created, message = create_user(auth_conn, signup_username, signup_password)
            if created:
                st.session_state["auth_username"] = message
                st.success("Account created and logged in.")
                st.rerun()
            else:
                st.error(message)

    return False


def main() -> None:
    st.title("💍 Jewellery Pricing App")
    st.caption("Local-only pricing for commissions and workshops")

    if not _render_auth_gate():
        return

    username = str(st.session_state["auth_username"])
    st.sidebar.caption(f"Signed in: {username}")

    with st.sidebar.expander("Security"):
        with st.form("change_password_form"):
            current_password = st.text_input("Current password", type="password")
            new_password = st.text_input("New password", type="password")
            confirm_password = st.text_input("Confirm new password", type="password")
            change_password_submit = st.form_submit_button("Change password")

        if change_password_submit:
            if new_password != confirm_password:
                st.sidebar.error("New passwords do not match.")
            else:
                auth_conn = get_auth_connection()
                updated, message = update_user_password(
                    auth_conn,
                    username,
                    current_password,
                    new_password,
                )
                if updated:
                    st.sidebar.success(message)
                else:
                    st.sidebar.error(message)

        st.caption("Danger zone")
        with st.form("delete_account_form"):
            delete_password = st.text_input("Password to confirm", type="password")
            delete_confirmation = st.text_input("Type DELETE to confirm")
            delete_submit = st.form_submit_button("Delete account")

        if delete_submit:
            if delete_confirmation.strip().upper() != "DELETE":
                st.sidebar.error("Type DELETE to confirm account removal.")
            else:
                auth_conn = get_auth_connection()
                deleted, message = delete_user_account(auth_conn, username, delete_password)
                if deleted:
                    user_db_path = get_user_db_path(username)
                    if user_db_path.exists():
                        user_db_path.unlink(missing_ok=True)
                    st.session_state["auth_username"] = None
                    st.success("Account and private data deleted.")
                    st.rerun()
                else:
                    st.sidebar.error(message)

    if st.sidebar.button("Log out"):
        st.session_state["auth_username"] = None
        st.rerun()

    conn = get_user_connection(username)
    init_db(conn)

    page = st.sidebar.radio(
        "Navigate",
        [
            "Dashboard",
            "Settings",
            "Stone Catalog",
            "Commission Quotes",
            "Commission Estimates",
            "Workshop Pricing",
            "History Logs",
            "Completed Projects",
        ],
    )

    if page == "Dashboard":
        dashboard.render(conn)
    elif page == "Settings":
        settings.render(conn)
    elif page == "Stone Catalog":
        stones.render(conn)
    elif page == "Commission Quotes":
        commissions.render(conn, fixed_quote_type="quote")
    elif page == "Commission Estimates":
        commissions.render(conn, fixed_quote_type="estimate")
    elif page == "Workshop Pricing":
        workshops.render(conn)
    elif page == "History Logs":
        history_logs.render(conn)
    elif page == "Completed Projects":
        projects.render(conn)


if __name__ == "__main__":
    main()
