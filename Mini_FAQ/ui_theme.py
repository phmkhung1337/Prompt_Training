"""Resolve primitive, semantic and component tokens for the Streamlit UI."""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st


ROOT = Path(__file__).resolve().parent


def theme_variables(mode: str) -> tuple[dict[str, str], str]:
    tokens = json.loads((ROOT / "design_tokens.json").read_text(encoding="utf-8"))
    primitives = tokens["primitives"]

    def resolve(reference: str) -> str:
        group, name = reference.split(".", 1)
        return primitives[group][name]

    semantic = tokens["semantic"][mode]
    variables = {
        f"--campus-{name}": resolve(reference)
        for name, reference in semantic.items() if name != "scheme"
    }
    for group in ("space", "radius", "font"):
        variables.update({f"--campus-{group}-{name}": value for name, value in primitives[group].items()})
    variables.update({f"--campus-{name}": resolve(reference) for name, reference in tokens["components"].items()})
    return variables, semantic["scheme"]


def apply_theme(mode: str) -> None:
    variables, scheme = theme_variables(mode)
    declarations = ";".join(f"{name}:{value}" for name, value in variables.items())
    stylesheet = (ROOT / "ui.css").read_text(encoding="utf-8")
    st.markdown(
        f"<style>:root{{{declarations};color-scheme:{scheme}}}{stylesheet}</style>",
        unsafe_allow_html=True,
    )
