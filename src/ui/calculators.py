import math
import sqlite3

import streamlit as st

UK_RING_SIZES_MM = {
    "A": 37.8,
    "B": 39.1,
    "C": 40.4,
    "D": 41.7,
    "E": 42.9,
    "F": 44.2,
    "G": 45.5,
    "H": 46.8,
    "I": 48.0,
    "J": 49.3,
    "K": 50.6,
    "L": 51.9,
    "M": 53.1,
    "N": 54.4,
    "O": 55.7,
    "P": 57.0,
    "Q": 58.3,
    "R": 59.5,
    "S": 60.8,
    "T": 62.1,
    "U": 63.4,
    "V": 64.6,
    "W": 65.9,
    "X": 67.2,
    "Y": 68.5,
    "Z": 69.7,
}

SILVER_DENSITY_G_CM3 = 10.36


def _build_size_options() -> list[tuple[str, float]]:
    options: list[tuple[str, float]] = []
    for label, circumference in UK_RING_SIZES_MM.items():
        options.append((label, circumference))
        half_label = f"{label} 1/2"
        options.append((half_label, circumference + 0.6))
    return options


def _format_mm(value: float) -> str:
    return f"{value:,.2f} mm"


def _format_cm(value: float) -> str:
    return f"{value:,.2f} cm"


def _format_g(value: float) -> str:
    return f"{value:,.2f} g"


def render(_: sqlite3.Connection) -> None:
    st.subheader("🧮 Essential Ring-Making Calculators & Tools")
    st.caption("Estimate wire length and metal weight from ring size and cross-section.")

    st.markdown("### Ring Size to Wire Length")

    size_options = _build_size_options()
    size_labels = [option[0] for option in size_options]
    size_map = {option[0]: option[1] for option in size_options}

    col1, col2, col3 = st.columns(3)
    with col1:
        ring_size = st.selectbox("UK ring size", options=size_labels, index=size_labels.index("L"))
        inner_circumference_mm = size_map[ring_size]
    with col2:
        shape = st.selectbox("Wire shape", options=["Round", "Square", "Half-round"])
    with col3:
        density = st.number_input(
            "Silver density (g/cm^3)",
            min_value=1.0,
            max_value=30.0,
            value=float(SILVER_DENSITY_G_CM3),
            step=0.01,
        )

    col4, col5 = st.columns(2)
    with col4:
        width_mm = st.number_input("Cross-section width (mm)", min_value=0.1, value=1.8, step=0.1)
    with col5:
        height_mm = st.number_input("Cross-section height (mm)", min_value=0.1, value=1.8, step=0.1)

    inner_diameter_mm = inner_circumference_mm / math.pi
    neutral_axis_mm = inner_diameter_mm + height_mm
    wire_length_mm = math.pi * neutral_axis_mm

    if shape == "Square":
        area_mm2 = width_mm * height_mm
    elif shape == "Half-round":
        area_mm2 = (math.pi * (width_mm / 2) * height_mm) / 2
    else:
        area_mm2 = math.pi * (width_mm / 2) * (height_mm / 2)

    area_cm2 = area_mm2 / 100.0
    length_cm = wire_length_mm / 10.0
    volume_cm3 = area_cm2 * length_cm
    weight_g = volume_cm3 * density

    st.markdown("### Results")
    r1, r2, r3 = st.columns(3)
    r1.metric("Wire length", _format_mm(wire_length_mm), _format_cm(length_cm))
    r2.metric("Estimated weight", _format_g(weight_g))
    r3.metric("Inner circumference", _format_mm(inner_circumference_mm))

    st.caption(
        "Length is based on UK ring size inner circumference plus one material height for neutral axis. "
        "Weight assumes solid silver and the selected cross-section shape."
    )

    st.divider()
    st.markdown("### Ring Size Converter")

    size_options = _build_size_options()
    size_labels = [option[0] for option in size_options]
    size_map = {option[0]: option[1] for option in size_options}

    system = st.selectbox("Input system", options=["UK", "US", "EU", "JP"])
    if system == "UK":
        input_size = st.selectbox("UK size", options=size_labels, index=size_labels.index("L"))
        circumference_mm = float(size_map[input_size])
    elif system == "US":
        us_size = st.number_input("US size", min_value=1.0, max_value=16.0, value=7.0, step=0.25)
        diameter_mm = 11.63 + (us_size * 0.8128)
        circumference_mm = diameter_mm * math.pi
    elif system == "JP":
        jp_size = st.number_input("JP size", min_value=1.0, max_value=30.0, value=12.0, step=0.5)
        circumference_mm = jp_size + 40.0
    else:
        circumference_mm = st.number_input(
            "EU size (circumference mm)",
            min_value=35.0,
            max_value=75.0,
            value=52.0,
            step=0.1,
        )

    diameter_mm = circumference_mm / math.pi
    us_calc = (diameter_mm - 11.63) / 0.8128
    jp_calc = circumference_mm - 40.0

    closest_uk = min(size_options, key=lambda item: abs(item[1] - circumference_mm))
    eu_size = circumference_mm

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("UK (nearest)", f"{closest_uk[0]} ({closest_uk[1]:.1f} mm)")
    c2.metric("US (approx)", f"{round(us_calc * 4) / 4:.2f}")
    c3.metric("EU (mm)", f"{eu_size:.1f}")
    c4.metric("JP (approx)", f"{round(jp_calc * 2) / 2:.1f}")

    st.caption("US/JP conversions are approximate; verify with a ring mandrel for exact sizing.")
