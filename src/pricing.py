from typing import Any


def round_money(value: float) -> float:
    return round(value, 2)


def calculate_estimate_range(final_price: float, variance_pct: float) -> dict[str, float]:
    delta = final_price * (variance_pct / 100)
    return {
        "estimate_min_gbp": round_money(max(0.0, final_price - delta)),
        "estimate_max_gbp": round_money(final_price + delta),
        "estimate_variance_pct": round(variance_pct, 2),
    }


def calculate_commission(
    *,
    weight_grams: float,
    spot_gbp_per_oz: float,
    troy_oz_to_grams: float,
    metal_multiplier: float,
    waste_pct: float,
    stone_items: list[dict[str, Any]],
    labour_hours: float,
    labour_rate_gbp_per_hr: float,
    supplier_markup_pct: float,
    overhead_pct: float,
    target_profit_margin_pct: float,
    vat_enabled: bool,
    vat_rate_pct: float,
    deposit_pct: float,
) -> dict[str, Any]:
    spot_gbp_per_gram = spot_gbp_per_oz / troy_oz_to_grams

    metal_base = weight_grams * spot_gbp_per_gram * metal_multiplier
    metal_cost = metal_base * (1 + waste_pct / 100)

    stone_cost = 0.0
    stone_lines = []
    for item in stone_items:
        line_cost = item["unit_cost_gbp"] * item["qty"] * (1 + item["applied_markup_pct"] / 100)
        stone_cost += line_cost
        stone_lines.append(
            {
                "stone_id": item["stone_id"],
                "label": item["label"],
                "qty": item["qty"],
                "unit_cost_gbp": round_money(item["unit_cost_gbp"]),
                "markup_pct": item["applied_markup_pct"],
                "line_cost_gbp": round_money(line_cost),
            }
        )

    supplier_markup_cost = (metal_cost + stone_cost) * (supplier_markup_pct / 100)
    labour_cost = labour_hours * labour_rate_gbp_per_hr
    base_subtotal = metal_cost + stone_cost + supplier_markup_cost + labour_cost

    overhead_cost = base_subtotal * (overhead_pct / 100)
    subtotal_plus_overhead = base_subtotal + overhead_cost

    profit_cost = subtotal_plus_overhead * (target_profit_margin_pct / 100)
    subtotal_before_vat = subtotal_plus_overhead + profit_cost

    vat_amount = subtotal_before_vat * (vat_rate_pct / 100) if vat_enabled else 0.0
    final_price = subtotal_before_vat + vat_amount
    deposit_due = final_price * (deposit_pct / 100)
    remaining_balance = final_price - deposit_due

    return {
        "spot_gbp_per_oz": round_money(spot_gbp_per_oz),
        "spot_gbp_per_gram": round_money(spot_gbp_per_gram),
        "metal_base_cost_gbp": round_money(metal_base),
        "metal_cost_gbp": round_money(metal_cost),
        "stone_cost_gbp": round_money(stone_cost),
        "supplier_markup_pct": round(supplier_markup_pct, 2),
        "supplier_markup_cost_gbp": round_money(supplier_markup_cost),
        "stone_lines": stone_lines,
        "labour_cost_gbp": round_money(labour_cost),
        "base_subtotal_gbp": round_money(base_subtotal),
        "overhead_cost_gbp": round_money(overhead_cost),
        "profit_cost_gbp": round_money(profit_cost),
        "subtotal_before_vat_gbp": round_money(subtotal_before_vat),
        "vat_amount_gbp": round_money(vat_amount),
        "deposit_pct": round(deposit_pct, 2),
        "deposit_due_gbp": round_money(deposit_due),
        "remaining_balance_gbp": round_money(remaining_balance),
        "final_price_gbp": round_money(final_price),
    }


def calculate_workshop_price(
    *,
    attendees: int,
    grams_included_per_person: float,
    waste_pct: float,
    spot_gbp_per_oz: float,
    troy_oz_to_grams: float,
    tutor_hours: float,
    labour_rate_gbp_per_hr: float,
    consumables_per_person: float,
    venue_cost: float,
    supplier_markup_pct: float,
    overhead_pct: float,
    target_profit_margin_pct: float,
    vat_enabled: bool,
    vat_rate_pct: float,
) -> dict[str, float]:
    total_grams = attendees * grams_included_per_person
    spot_gbp_per_gram = spot_gbp_per_oz / troy_oz_to_grams

    metal_base = total_grams * spot_gbp_per_gram
    metal_cost = metal_base * (1 + waste_pct / 100)
    tutor_cost = tutor_hours * labour_rate_gbp_per_hr
    consumables_total = attendees * consumables_per_person
    supplier_markup_cost = (metal_cost + consumables_total) * supplier_markup_pct / 100

    base_subtotal = metal_cost + consumables_total + supplier_markup_cost + tutor_cost + venue_cost
    overhead_cost = base_subtotal * overhead_pct / 100
    subtotal_plus_overhead = base_subtotal + overhead_cost
    profit_cost = subtotal_plus_overhead * target_profit_margin_pct / 100
    subtotal_before_vat = subtotal_plus_overhead + profit_cost
    vat_amount = subtotal_before_vat * vat_rate_pct / 100 if vat_enabled else 0.0

    final_total = subtotal_before_vat + vat_amount
    per_person = final_total / attendees if attendees > 0 else 0.0

    return {
        "total_grams": round_money(total_grams),
        "spot_gbp_per_gram": round_money(spot_gbp_per_gram),
        "metal_cost_gbp": round_money(metal_cost),
        "supplier_markup_pct": round(supplier_markup_pct, 2),
        "supplier_markup_cost_gbp": round_money(supplier_markup_cost),
        "tutor_cost_gbp": round_money(tutor_cost),
        "consumables_total_gbp": round_money(consumables_total),
        "venue_cost_gbp": round_money(venue_cost),
        "base_subtotal_gbp": round_money(base_subtotal),
        "overhead_cost_gbp": round_money(overhead_cost),
        "profit_cost_gbp": round_money(profit_cost),
        "subtotal_before_vat_gbp": round_money(subtotal_before_vat),
        "vat_amount_gbp": round_money(vat_amount),
        "final_total_gbp": round_money(final_total),
        "per_person_gbp": round_money(per_person),
    }
