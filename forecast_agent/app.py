"""
Subscription Forecast Agent — Streamlit UI
==========================================
Tab ① : Load historical data (NLP → BigQuery SQL)
Tab ② : Forecast setup (horizon + model)
Tab ③ : New customer plan (product mix % + monthly budget)
Tab ④ : Results (charts + table + CSV download)
"""

import io
import logging
from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dateutil.relativedelta import relativedelta

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

st.set_page_config(
    page_title="Subscription Forecast Agent",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Data Source")
    st.divider()

    demo_mode = st.toggle("Demo Mode (no BigQuery needed)", value=True)

    if not demo_mode:
        gcp_project = st.text_input("GCP Project ID", placeholder="my-gcp-project")
        bq_dataset  = st.text_input("BQ Dataset ID",  value="subscription_data")
        bq_table    = st.text_input("BQ Table ID",    value="customer_metrics")
        st.caption("Ensure `GOOGLE_APPLICATION_CREDENTIALS` is set in your environment.")
    else:
        gcp_project = bq_dataset = bq_table = "demo"
        st.info("Running with synthetic 5-year data — no credentials required.")

    st.divider()
    with st.expander("ℹ️ Data Schema"):
        st.markdown(
            """
| Column | Type | Values |
|---|---|---|
| `month` | DATE | Monthly grain |
| `customer_type` | STRING | `new` / `existing` |
| `product_line` | STRING | `classic` / `super` |
| `customer_count` | INTEGER | Head-count |
"""
        )
    st.caption("Subscription Forecast Agent · v1.0")

# ── Page Header ────────────────────────────────────────────────────────────────
st.title("📈 Subscription Forecast Agent")
st.caption(
    "Rolling forecast for new & existing subscribers by product line · "
    "Models: ARIMAX · Prophet"
)
st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([
    "① Historical Data",
    "② Forecast Setup",
    "③ New Customer Plan",
    "④ Results",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Historical Data
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.subheader("Load Historical Data (Last 5 Years)")

    st.info(
        "**What happens here:** Your natural-language request is converted to BigQuery SQL "
        "using the Claude API (or a canned query in demo mode). "
        "The query pulls **monthly customer counts** segmented by "
        "**customer type** (`new` / `existing`) and **product line** (`classic` / `super`) "
        "for the last 5 years. This history trains the forecasting models."
    )

    nl_query = st.text_area(
        "Describe the data you want to pull:",
        value=(
            "Get monthly customer counts segmented by customer type (new, existing) "
            "and product line (classic, super) for the last 5 years"
        ),
        height=90,
    )

    if st.button("🔍 Generate SQL & Load Data", type="primary", use_container_width=True):
        with st.spinner("Generating SQL and fetching data…"):
            try:
                from nlp2sql import generate_historical_query
                from bq_client import fetch_historical_data, get_demo_data

                sql = generate_historical_query(nl_query, gcp_project, bq_dataset, bq_table)
                st.session_state["generated_sql"] = sql

                if demo_mode:
                    st.session_state["hist_df"] = get_demo_data()
                else:
                    st.session_state["hist_df"] = fetch_historical_data(sql, gcp_project)

                st.success("✅ Data loaded successfully!")
            except Exception as exc:
                st.error(f"Failed to load data: {exc}")

    if "generated_sql" in st.session_state:
        with st.expander("🔎 View Generated SQL"):
            st.code(st.session_state["generated_sql"], language="sql")

    if "hist_df" in st.session_state:
        df: pd.DataFrame = st.session_state["hist_df"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Rows",    f"{len(df):,}")
        c2.metric("Date Range",    f"{df['month'].min().strftime('%Y-%m')} → {df['month'].max().strftime('%Y-%m')}")
        c3.metric("Product Lines", df["product_line"].nunique())
        c4.metric("Customer Types", df["customer_type"].nunique())

        # Line chart — one line per product × type combination
        chart_df = (
            df.groupby(["month", "product_line", "customer_type"])["customer_count"]
            .sum()
            .reset_index()
        )
        chart_df["series"] = chart_df["product_line"].str.capitalize() + " · " + chart_df["customer_type"].str.capitalize()

        fig = go.Figure()
        colours = {
            "Classic · New":      "#1E88E5",
            "Classic · Existing": "#90CAF9",
            "Super · New":        "#FB8C00",
            "Super · Existing":   "#FFCC80",
        }
        for series, grp in chart_df.groupby("series"):
            fig.add_trace(go.Scatter(
                x=grp["month"], y=grp["customer_count"],
                mode="lines", name=series,
                line=dict(color=colours.get(series), width=2),
            ))
        fig.update_layout(
            title="Historical Customer Counts by Product Line & Type",
            xaxis_title="Month", yaxis_title="Customer Count",
            height=400, legend_title="Series",
        )
        st.plotly_chart(fig, use_container_width=True)

        with st.expander("📋 Raw Data Preview (first 60 rows)"):
            st.dataframe(df.head(60), use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Forecast Setup
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Forecast Configuration")

    col_left, col_right = st.columns(2, gap="large")

    with col_left:
        st.markdown("### ⏱️ Forecast Horizon")
        st.info(
            "**Next 3 months** — short-term operational planning (billing cycle, inventory).\n\n"
            "**Next 3 years** — strategic / financial planning (headcount, infrastructure)."
        )
        horizon = st.radio(
            "Forecast period",
            options=["Next 3 months", "Next 3 years"],
            label_visibility="collapsed",
        )
        n_months   = 3 if horizon == "Next 3 months" else 36
        start_mth  = date.today().replace(day=1) + relativedelta(months=1)
        fut_months = [start_mth + relativedelta(months=i) for i in range(n_months)]

        st.session_state["n_months"]       = n_months
        st.session_state["forecast_months"] = fut_months

        st.success(
            f"📅 {n_months} months: "
            f"**{fut_months[0].strftime('%b %Y')}** → **{fut_months[-1].strftime('%b %Y')}**"
        )

    with col_right:
        st.markdown("### 🤖 Forecasting Model")
        st.info(
            "**ARIMAX** — Seasonal ARIMA with new-subscriber volume as an exogenous regressor. "
            "Best when existing-customer counts follow a predictable trend with monthly seasonality.\n\n"
            "**Prophet** — Meta's additive model with automatic trend changepoints and "
            "yearly seasonality. Better when the series has structural breaks or "
            "holiday-driven spikes."
        )
        model_choice = st.radio(
            "Model",
            options=["ARIMAX", "Prophet"],
            label_visibility="collapsed",
        )
        st.session_state["model_choice"] = model_choice

        if model_choice == "ARIMAX":
            st.caption(
                "Configuration: SARIMAX(1,1,1)(1,0,1,12) · "
                "exogenous = same-month new-subscriber count · "
                "80 % confidence interval"
            )
        else:
            st.caption(
                "Configuration: yearly seasonality enabled · "
                "new-subscriber count as additional regressor · "
                "80 % uncertainty interval"
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — New Customer Plan
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("New Customer Budget Plan")

    st.info(
        "**What this does:** Provide your **financial budget plan** — how many *total* new "
        "subscribers you expect (or plan to acquire) each future month. "
        "The product mix % distributes that total across Classic and Super lines.\n\n"
        "You can either fill in the table manually **or** upload a CSV "
        "with columns `month` (YYYY-MM) and `new_customers`."
    )

    # ── Product Mix ──────────────────────────────────────────────────────────
    st.markdown("### 🥧 Product Line Split for New Customers")

    col_c, col_s = st.columns(2)
    with col_c:
        classic_pct_int = st.number_input(
            "Classic %",
            min_value=0, max_value=100, value=40, step=5,
            help="What % of new customers choose the Classic product line?",
        )
    with col_s:
        super_pct_int = 100 - classic_pct_int
        st.number_input(
            "Super %",
            value=int(super_pct_int),
            disabled=True,
            help="Auto-calculated: 100 % − Classic %",
        )

    st.success(f"✅  Classic **{classic_pct_int} %**   |   Super **{super_pct_int} %**")

    st.session_state["classic_pct"] = classic_pct_int / 100
    st.session_state["super_pct"]   = super_pct_int   / 100

    st.divider()

    # ── Monthly Table ────────────────────────────────────────────────────────
    st.markdown("### 📅 Monthly New Customer Count")

    uploaded_csv = st.file_uploader(
        "Upload a CSV  (`month` YYYY-MM, `new_customers` integer)",
        type=["csv"],
    )

    if "forecast_months" not in st.session_state:
        st.warning("⚠️ Set the forecast horizon in **Tab ②** first.")
    else:
        fut_months = st.session_state["forecast_months"]

        # Seed from CSV upload if provided
        csv_lookup: dict[str, int] = {}
        if uploaded_csv is not None:
            try:
                csv_df = pd.read_csv(uploaded_csv)
                csv_df.columns = [c.strip().lower() for c in csv_df.columns]
                csv_lookup = dict(zip(csv_df["month"].astype(str), csv_df["new_customers"].astype(int)))
                st.success(f"CSV loaded — {len(csv_lookup)} rows imported.")
            except Exception as exc:
                st.error(f"Could not parse CSV: {exc}")

        default_plan = pd.DataFrame({
            "month":         [m.strftime("%Y-%m") for m in fut_months],
            "new_customers": [int(csv_lookup.get(m.strftime("%Y-%m"), 1_000)) for m in fut_months],
        })

        edited_plan = st.data_editor(
            default_plan,
            column_config={
                "month": st.column_config.TextColumn(
                    "Month", disabled=True, help="Future forecast month"
                ),
                "new_customers": st.column_config.NumberColumn(
                    "Total New Customers",
                    min_value=0, step=100, format="%d",
                    help="Budget-driven new subscriber target for this month",
                ),
            },
            use_container_width=True,
            hide_index=True,
            num_rows="fixed",
        )
        st.session_state["new_customer_plan"] = edited_plan

        # Live preview of split
        preview = edited_plan.copy()
        preview["classic"] = (preview["new_customers"] * (classic_pct_int / 100)).round().astype(int)
        preview["super"]   = (preview["new_customers"] * (super_pct_int   / 100)).round().astype(int)

        with st.expander("👁️ Preview: Applied Product Mix"):
            st.dataframe(
                preview.rename(columns={
                    "new_customers": "Total New",
                    "classic": f"Classic ({classic_pct_int}%)",
                    "super":   f"Super ({super_pct_int}%)",
                }),
                use_container_width=True,
                hide_index=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Results
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("Rolling Forecast Output")

    required_keys = ["hist_df", "model_choice", "new_customer_plan", "classic_pct"]
    missing = [k for k in required_keys if k not in st.session_state]

    if missing:
        st.warning(
            "⚠️ Complete the following steps before generating the forecast:\n"
            + "\n".join(f"- {k}" for k in missing)
        )
    else:
        model_label   = st.session_state["model_choice"]
        n_months_disp = st.session_state["n_months"]
        classic_pct_d = int(st.session_state["classic_pct"] * 100)
        super_pct_d   = 100 - classic_pct_d

        st.markdown(
            f"**Configuration summary:** "
            f"Model = `{model_label}` · "
            f"Horizon = `{n_months_disp} months` · "
            f"Product mix = Classic `{classic_pct_d}%` / Super `{super_pct_d}%`"
        )

        if st.button("▶  Generate Rolling Forecast", type="primary", use_container_width=True):
            with st.spinner(f"Fitting {model_label} and generating {n_months_disp}-month forecast…"):
                try:
                    from forecast_engine import run_forecast

                    result = run_forecast(
                        hist_df=st.session_state["hist_df"],
                        new_customer_plan=st.session_state["new_customer_plan"],
                        classic_pct=st.session_state["classic_pct"],
                        super_pct=st.session_state["super_pct"],
                        model_name=model_label,
                        n_months=n_months_disp,
                    )
                    st.session_state["forecast_result"] = result
                    st.success("✅ Forecast complete!")
                except Exception as exc:
                    st.error(f"Forecast failed: {exc}")
                    st.exception(exc)

        if "forecast_result" in st.session_state:
            res: pd.DataFrame = st.session_state["forecast_result"]

            # ── KPI Metrics ───────────────────────────────────────────────────
            st.divider()
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total New Subscribers",     f"{(res['new_classic'] + res['new_super']).sum():,.0f}")
            m2.metric("Total Existing (Retained)", f"{(res['existing_classic'] + res['existing_super']).sum():,.0f}")
            m3.metric("Peak Classic Month",        f"{res['total_classic'].max():,.0f}")
            m4.metric("Peak Super Month",          f"{res['total_super'].max():,.0f}")

            st.divider()

            # ── Chart 1: Stacked Bar — Total by product line ─────────────────
            st.markdown("**Monthly Total Customer Count by Product Line**")

            fig_bar = go.Figure()
            fig_bar.add_trace(go.Bar(
                x=res["month"], y=res["total_classic"],
                name="Classic Total", marker_color="#1E88E5",
            ))
            fig_bar.add_trace(go.Bar(
                x=res["month"], y=res["total_super"],
                name="Super Total", marker_color="#FB8C00",
            ))
            fig_bar.update_layout(
                barmode="stack",
                height=380,
                xaxis_title="Month",
                yaxis_title="Customer Count",
                legend_title="Product Line",
            )
            st.plotly_chart(fig_bar, use_container_width=True)

            # ── Chart 2: New vs Existing with CI bands ───────────────────────
            st.markdown("**New vs Existing Customers per Product Line (with 80 % CI)**")

            fig_line = go.Figure()

            # Classic existing with CI shading
            fig_line.add_trace(go.Scatter(
                x=pd.concat([res["month"], res["month"][::-1]]),
                y=pd.concat([res["upper_ci_classic"], res["lower_ci_classic"][::-1]]),
                fill="toself", fillcolor="rgba(30,136,229,0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                name="Classic Existing 80% CI", showlegend=True,
            ))
            # Super existing with CI shading
            fig_line.add_trace(go.Scatter(
                x=pd.concat([res["month"], res["month"][::-1]]),
                y=pd.concat([res["upper_ci_super"], res["lower_ci_super"][::-1]]),
                fill="toself", fillcolor="rgba(251,140,0,0.12)",
                line=dict(color="rgba(0,0,0,0)"),
                name="Super Existing 80% CI", showlegend=True,
            ))

            for col, label, colour, dash in [
                ("existing_classic", "Classic Existing", "#1E88E5", "solid"),
                ("existing_super",   "Super Existing",   "#FB8C00", "solid"),
                ("new_classic",      "Classic New",      "#1565C0", "dot"),
                ("new_super",        "Super New",        "#E65100", "dot"),
            ]:
                fig_line.add_trace(go.Scatter(
                    x=res["month"], y=res[col],
                    mode="lines", name=label,
                    line=dict(color=colour, dash=dash, width=2),
                ))

            fig_line.update_layout(
                height=420,
                xaxis_title="Month",
                yaxis_title="Customer Count",
                legend_title="Series",
            )
            st.plotly_chart(fig_line, use_container_width=True)

            # ── Detailed Table ───────────────────────────────────────────────
            st.markdown("**Monthly Forecast Detail Table**")

            display = res.copy()
            display["month"] = display["month"].dt.strftime("%Y-%m")
            display = display.rename(columns={
                "month":             "Month",
                "new_classic":       "New Classic",
                "new_super":         "New Super",
                "existing_classic":  "Existing Classic",
                "existing_super":    "Existing Super",
                "total_classic":     "Total Classic",
                "total_super":       "Total Super",
                "lower_ci_classic":  "Classic CI Low",
                "upper_ci_classic":  "Classic CI High",
                "lower_ci_super":    "Super CI Low",
                "upper_ci_super":    "Super CI High",
            })
            st.dataframe(
                display.style.format({c: "{:,.0f}" for c in display.columns if c != "Month"}),
                use_container_width=True,
                hide_index=True,
            )

            # ── Download ─────────────────────────────────────────────────────
            csv_out = res.copy()
            csv_out["month"] = csv_out["month"].dt.strftime("%Y-%m")
            csv_bytes = csv_out.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="⬇️  Download Forecast as CSV",
                data=csv_bytes,
                file_name=f"subscription_forecast_{date.today().isoformat()}.csv",
                mime="text/csv",
                use_container_width=True,
            )
