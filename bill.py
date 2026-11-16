# Residential (A-1) bill estimate, WAPDA DISCO tariff 2026 (includes SEPCO).
# Edit these two values using your own electricity bill.
SANCTIONED_LOAD_KW = 1       # "Sanctioned load" printed on your bill
FPA_PER_UNIT = 2.3673        # Fuel charges adjustment, Rs per unit (November 2026 bills; changes monthly)

FC_SURCHARGE = 0.43          # Rs per unit
NJ_SURCHARGE = 0.10          # Rs per unit
ED_RATE = 0.015              # Electricity duty
GST_RATE = 0.18
TV_FEE = 35                  # Rs per month

# (upper limit of units, Rs per unit, fixed charge Rs per kW per month)
# The rate of the slab in which the period's total units fall applies to all units.
PROTECTED = [(100, 10.54, 0), (200, 13.01, 300)]
UNPROTECTED = [(100, 22.44, 200), (200, 28.91, 300), (300, 33.10, 350), (400, 36.46, 400),
               (500, 38.95, 500), (600, 40.22, 675), (700, 41.85, 675), (float("inf"), 47.20, 675)]


def estimate(units, previous_units=()):
    if units is None:
        return None
    protected = units <= 200 and all((u is None or u <= 200) for u in previous_units)
    table = PROTECTED if protected else UNPROTECTED
    rate, fixed_kw = table[-1][1], table[-1][2]
    for limit, r, f in table:
        if units <= limit:
            rate, fixed_kw = r, f
            break
    energy = units * rate
    fixed = fixed_kw * SANCTIONED_LOAD_KW
    fpa = 0 if protected else units * FPA_PER_UNIT      # protected consumers are exempt from FCA
    surcharges = units * (FC_SURCHARGE + NJ_SURCHARGE)
    duty = (energy + fpa) * ED_RATE
    gst = (energy + fixed + fpa + surcharges) * GST_RATE
    total = energy + fixed + fpa + surcharges + duty + gst + TV_FEE
    return {"units": units, "rate": rate, "category": "Protected" if protected else "Unprotected",
            "energy": round(energy, 2), "fixed": round(fixed, 2), "fpa": round(fpa, 2),
            "surcharges": round(surcharges, 2), "duty": round(duty, 2), "gst": round(gst, 2),
            "tv_fee": TV_FEE, "amount": round(total, 2)}