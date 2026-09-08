"""
Visualization utilities for model evaluation and reporting.
"""
from pathlib import Path
from typing import List, Optional, Union
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

from .io import ensure_dir, get_logger

logger = get_logger("viz")

# Set clean aesthetic styling
plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")
plt.rcParams["font.sans-serif"] = ["DejaVu Sans", "Arial", "Helvetica"]
plt.rcParams["axes.edgecolor"] = "#cccccc"
plt.rcParams["axes.linewidth"] = 0.8


def plot_coherence_curves(
    leaderboard_df: pd.DataFrame,
    output_path: Union[str, Path] = "reports/figures/coherence_curves.png"
) -> Path:
    """
    Plot Cv and UMass coherence curves across K values for each candidate model.
    """
    ensure_dir(output_path)
    fig, axes = plt.subplots(1, 2, figsize=(15, 6), sharex=True)

    models = leaderboard_df["model_type"].unique()
    palette = sns.color_palette("tab10", len(models))

    # Cv Coherence Plot (Higher is better)
    for idx, model_type in enumerate(models):
        subset = leaderboard_df[leaderboard_df["model_type"] == model_type].sort_values("k")
        if "coherence_c_v" in subset.columns and subset["coherence_c_v"].notnull().any():
            axes[0].plot(
                subset["k"],
                subset["coherence_c_v"],
                marker="o",
                linewidth=2.2,
                label=model_type,
                color=palette[idx]
            )

    axes[0].set_title(r"Topic Coherence ($C_v$) vs. Number of Topics ($K$)", fontsize=13, fontweight="bold", pad=12)
    axes[0].set_xlabel("Number of Topics ($K$)", fontsize=11)
    axes[0].set_ylabel(r"Coherence Score ($C_v$) [Higher = Better]", fontsize=11)
    axes[0].grid(True, linestyle="--", alpha=0.6)
    axes[0].legend(title="Candidate Model", frameon=True)

    # UMass Coherence Plot (Closer to 0 is better)
    for idx, model_type in enumerate(models):
        subset = leaderboard_df[leaderboard_df["model_type"] == model_type].sort_values("k")
        if "coherence_u_mass" in subset.columns and subset["coherence_u_mass"].notnull().any():
            axes[1].plot(
                subset["k"],
                subset["coherence_u_mass"],
                marker="s",
                linewidth=2.2,
                label=model_type,
                color=palette[idx]
            )

    axes[1].set_title(r"Topic Coherence ($U_{mass}$) vs. Number of Topics ($K$)", fontsize=13, fontweight="bold", pad=12)
    axes[1].set_xlabel("Number of Topics ($K$)", fontsize=11)
    axes[1].set_ylabel(r"Coherence Score ($U_{mass}$) [Closer to 0 = Better]", fontsize=11)
    axes[1].grid(True, linestyle="--", alpha=0.6)
    axes[1].legend(title="Candidate Model", frameon=True)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved coherence curves to: {output_path}")
    return Path(output_path)


def plot_confusion_matrix(
    matrix_df: pd.DataFrame,
    output_path: Union[str, Path] = "reports/figures/confusion_matrix.png",
    title: str = "Discovered Topics vs. Ground Truth Categories"
) -> Path:
    """
    Plot heatmap matrix representing topic-to-class alignment or confusion.
    """
    ensure_dir(output_path)
    plt.figure(figsize=(12, 8))
    sns.heatmap(
        matrix_df,
        annot=True,
        fmt=".2f" if matrix_df.values.dtype == float else "d",
        cmap="YlGnBu",
        cbar=True,
        linewidths=0.5,
        linecolor="#e0e0e0"
    )
    plt.title(title, fontsize=14, fontweight="bold", pad=14)
    plt.xlabel("Ground Truth Class Label", fontsize=11, fontweight="bold")
    plt.ylabel("Discovered Topic / Cluster", fontsize=11, fontweight="bold")
    plt.xticks(rotation=45, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    logger.info(f"Saved confusion matrix plot to: {output_path}")
    return Path(output_path)
