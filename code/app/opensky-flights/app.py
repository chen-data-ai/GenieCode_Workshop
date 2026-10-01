"""OpenSky Flights — flight-phase predictor (Databricks App, Streamlit).

Enter an aircraft's state → predict its flight phase via the `opensky-flight-phase` Model Serving
endpoint → the prediction is logged to Lakebase, and users can leave feedback.
"""

import streamlit as st

import backend

st.set_page_config(page_title="OpenSky Flights", page_icon="✈️", layout="wide")

PHASE = {
    "Ground":  {"emoji": "🛬", "color": "#6B7280", "desc": "On the ground"},
    "Climb":   {"emoji": "🛫", "color": "#16A34A", "desc": "Climbing out"},
    "Cruise":  {"emoji": "✈️", "color": "#2563EB", "desc": "Cruising"},
    "Descent": {"emoji": "🛩️", "color": "#EA580C", "desc": "Descending"},
}

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.6rem; max-width: 1120px;}
      #MainMenu, footer, header {visibility: hidden;}
      html, body, [class*="css"] {font-family: 'Inter', -apple-system, sans-serif;}
      .hero {background: linear-gradient(100deg,#0B2A4A,#1D4E89); color:#fff;
             padding:1.3rem 1.6rem; border-radius:16px; box-shadow:0 6px 20px rgba(13,42,74,.25);}
      .hero h1 {margin:0; font-size:1.65rem; letter-spacing:-.02em;}
      .hero p  {margin:.4rem 0 0; opacity:.85; font-size:.92rem;}
      .chips {margin:.9rem 0 1.3rem; display:flex; gap:.5rem; flex-wrap:wrap;}
      .chip {display:inline-flex; align-items:center; gap:.35rem; padding:.28rem .7rem;
             border-radius:999px; font-size:.82rem; font-weight:600; color:#fff;}
      .result {border-radius:16px; padding:1.6rem 1.4rem; color:#fff; text-align:center;
               box-shadow:0 8px 24px rgba(0,0,0,.18);}
      .result .emoji {font-size:3.2rem; line-height:1;}
      .result .phase {font-size:2.3rem; font-weight:800; margin:.3rem 0 .1rem; letter-spacing:-.02em;}
      .result .desc  {opacity:.92; font-size:.95rem;}
      .result .stats {display:flex; justify-content:center; gap:1.4rem; margin-top:1rem;
                      padding-top:.9rem; border-top:1px solid rgba(255,255,255,.25); font-size:.85rem;}
      .result .stats b {display:block; font-size:1.05rem;}
      code {background:rgba(255,255,255,.18); color:#fff; padding:.05rem .35rem; border-radius:5px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>✈️ OpenSky Flights — flight-phase predictor</h1>
      <p>Model <b>flight_phase_model_fs@prod</b> via Model Serving · operational store <b>Lakebase</b>
      · aircraft features auto-joined by <code>icao24</code></p>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    '<div class="chips">'
    + "".join(f'<span class="chip" style="background:{m["color"]}">{m["emoji"]} {p}</span>'
              for p, m in PHASE.items())
    + "</div>",
    unsafe_allow_html=True,
)

USER = st.context.headers.get("X-Forwarded-Email", "local") if hasattr(st, "context") else "local"

db_ready = backend.lakebase_configured()
if db_ready:
    try:
        backend.init_schema()
    except Exception as e:  # noqa: BLE001
        db_ready = False
        st.warning(f"Lakebase not ready yet (predictions won't be logged): {e}")

left, right = st.columns([1, 1], gap="large")

# --- Input --------------------------------------------------------------
with left:
    with st.container(border=True):
        st.markdown("#### 🛩️ Aircraft state")
        icao24 = st.text_input("Aircraft id (icao24)", value="a05ab3")
        c1, c2 = st.columns(2)
        with c1:
            baro_altitude = st.number_input("Baro altitude (m)", value=5000.0, step=100.0)
            velocity = st.number_input("Velocity (m/s)", value=200.0, step=10.0)
        with c2:
            geo_altitude = st.number_input("Geo altitude (m)", value=5200.0, step=100.0)
            true_track = st.number_input("True track (°)", value=90.0, min_value=0.0, max_value=360.0)
        predict = st.button("Predict flight phase", type="primary", use_container_width=True)

if predict:
    features = {"baro_altitude": baro_altitude, "geo_altitude": geo_altitude,
                "velocity": velocity, "true_track": true_track}
    try:
        phase = backend.predict_phase(icao24, features)
        st.session_state["last"] = {"icao24": icao24, "features": features, "phase": phase}
        if db_ready:
            try:
                st.session_state["last"]["prediction_id"] = backend.log_prediction(icao24, features, phase, USER)
            except Exception as e:  # noqa: BLE001
                st.warning(f"Prediction made but not logged: {e}")
    except Exception as e:  # noqa: BLE001
        st.session_state.pop("last", None)
        with right:
            st.error(f"Prediction failed (is the serving endpoint READY?): {e}")

# --- Result + feedback --------------------------------------------------
with right:
    last = st.session_state.get("last")
    if last:
        m = PHASE.get(last["phase"], {"emoji": "❓", "color": "#334155", "desc": last["phase"]})
        f = last["features"]
        st.markdown(
            f"""<div class="result" style="background:{m['color']}">
                  <div class="emoji">{m['emoji']}</div>
                  <div class="phase">{last['phase']}</div>
                  <div class="desc">{m['desc']} · aircraft <code>{last['icao24']}</code></div>
                  <div class="stats">
                    <div>altitude<b>{f['baro_altitude']:,.0f} m</b></div>
                    <div>velocity<b>{f['velocity']:,.0f} m/s</b></div>
                    <div>track<b>{f['true_track']:,.0f}°</b></div>
                  </div>
                </div>""",
            unsafe_allow_html=True,
        )
        if db_ready and last.get("prediction_id"):
            st.markdown("")
            with st.container(border=True):
                st.markdown("###### Was this right?")
                b1, b2, b3 = st.columns([1, 1, 1.3])
                with b1:
                    if st.button("👍 Correct", use_container_width=True):
                        backend.log_feedback(last["prediction_id"], True, last["phase"])
                        st.toast("Thanks for the feedback!")
                with b2:
                    actual = st.selectbox("Actual", list(PHASE), label_visibility="collapsed")
                with b3:
                    if st.button("👎 Wrong", use_container_width=True):
                        backend.log_feedback(last["prediction_id"], False, actual)
                        st.toast("Logged the correction.")
    else:
        st.markdown(
            """<div class="result" style="background:#334155">
                 <div class="emoji">🛰️</div>
                 <div class="phase">Ready</div>
                 <div class="desc">Enter a state on the left and hit Predict.</div>
               </div>""",
            unsafe_allow_html=True,
        )

# --- Recent activity ----------------------------------------------------
st.divider()
if db_ready:
    try:
        rows = backend.recent_predictions(50)
        k1, k2, k3 = st.columns(3)
        k1.metric("Predictions (recent)", len(rows))
        k2.metric("Distinct aircraft", len({r["icao24"] for r in rows}))
        k3.metric("Serving model", "flight_phase_model_fs")

        if rows:
            # Phase mix chips
            from collections import Counter
            counts = Counter(r["predicted_phase"] for r in rows)
            mix = "".join(
                f'<span class="chip" style="background:{PHASE.get(p,{}).get("color","#334155")}">'
                f'{PHASE.get(p,{}).get("emoji","❓")} {p} · {n}</span>'
                for p, n in counts.most_common()
            )
            st.markdown(f'<div class="chips">{mix}</div>', unsafe_allow_html=True)

            st.markdown("#### Recent predictions")
            display = [{
                "Aircraft": r["icao24"],
                "Phase": f'{PHASE.get(r["predicted_phase"],{}).get("emoji","❓")} {r["predicted_phase"]}',
                "Velocity (m/s)": round(r["velocity"], 1) if r["velocity"] is not None else None,
                "Baro alt (m)": round(r["baro_altitude"], 0) if r["baro_altitude"] is not None else None,
                "By": r["created_by"],
                "When (UTC)": r["created_at"].strftime("%H:%M:%S") if r["created_at"] else None,
            } for r in rows[:12]]
            st.dataframe(display, use_container_width=True, hide_index=True)
        else:
            st.caption("No predictions logged yet — make one above.")
    except Exception as e:  # noqa: BLE001
        st.caption(f"Could not load recent predictions: {e}")
else:
    st.info("Lakebase isn't attached yet, so predictions aren't being logged. Predictions still work.")
