"""
app.py — Dash application entry point for apex-backtest dashboard.

Launch: python -m src.dashboard.app
Access: http://localhost:8050

Uses Dash + Plotly + dash-bootstrap-components for the interactive UI.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc

from src.dashboard.layouts import build_layout
from src.dashboard.callbacks import register_callbacks


def create_app() -> dash.Dash:
    """Create and configure the Dash application."""
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.DARKLY],
        title="apex-backtest Dashboard",
        suppress_callback_exceptions=True,
    )

    app.layout = build_layout()
    register_callbacks(app)

    return app


def main() -> None:
    """Entry point for running the dashboard."""
    app = create_app()
    print("Starting apex-backtest Dashboard at http://localhost:8050")
    app.run(debug=True, host="127.0.0.1", port=8050)


if __name__ == "__main__":
    main()
