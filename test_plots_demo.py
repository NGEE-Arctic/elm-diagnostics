"""Test and demonstrate all plotting functions with real oakharbor data."""

from pathlib import Path
import matplotlib.pyplot as plt
from elm_diagnostics import Run
from elm_diagnostics.plots import (
    plot_timeseries,
    plot_seasonal,
    plot_anomaly,
    plot_histogram,
    plot_diurnal,
)

# Load the real data
run = Run("/Users/rfiorella/Downloads/run", name="oakharbor")

print("=" * 70)
print("ELM-DIAGNOSTICS: Testing All Plot Functions with Real Data")
print("=" * 70)

# Create output directory for test plots
output_dir = Path("test_plots")
output_dir.mkdir(exist_ok=True)

# Test variables
test_vars = {
    "GPP": "Gross Primary Production",
    "RAIN": "Precipitation (Rain)",
    "QSOIL": "Ground Evaporation",
    "FSH": "Sensible Heat Flux",
    "EFLX_LH_TOT": "Latent Heat Flux",
}

print(f"\n1. Testing plot functions with {len(test_vars)} variables...")
print(f"   Output directory: {output_dir.absolute()}\n")

# Test each plot type for each variable
for varname, description in test_vars.items():
    print(f"   Variable: {varname:15s} ({description})")

    try:
        # 1. Time series
        fig = plot_timeseries(run, varname)
        fig.savefig(
            output_dir / f"{varname}_timeseries.png", dpi=150, bbox_inches="tight"
        )
        plt.close(fig)
        print(f"      ✓ Timeseries plot saved")

        # 2. Seasonal cycle
        fig = plot_seasonal(run, varname)
        fig.savefig(
            output_dir / f"{varname}_seasonal.png", dpi=150, bbox_inches="tight"
        )
        plt.close(fig)
        print(f"      ✓ Seasonal plot saved")

        # 3. Anomaly (needs multiple years, will skip for single month)
        try:
            fig = plot_anomaly(run, varname)
            fig.savefig(
                output_dir / f"{varname}_anomaly.png", dpi=150, bbox_inches="tight"
            )
            plt.close(fig)
            print(f"      ✓ Anomaly plot saved")
        except:
            print(f"      ⏭ Anomaly plot skipped (need multiple years)")

        # 4. Histogram
        fig = plot_histogram(run, varname, bins=30)
        fig.savefig(
            output_dir / f"{varname}_histogram.png", dpi=150, bbox_inches="tight"
        )
        plt.close(fig)
        print(f"      ✓ Histogram saved")

        # 5. Diurnal (will show message if not sub-daily)
        fig = plot_diurnal(run, varname)
        fig.savefig(output_dir / f"{varname}_diurnal.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        print(f"      ✓ Diurnal plot saved (may show 'not sub-daily' message)")

        print()

    except Exception as e:
        print(f"      ✗ Error plotting {varname}: {e}\n")
        continue

# Test auto-computed variable
print("2. Testing with auto-computed variable (QFLX_EVAP_TOT)...")
try:
    fig = plot_timeseries(run, "QFLX_EVAP_TOT")
    fig.savefig(
        output_dir / "QFLX_EVAP_TOT_timeseries.png", dpi=150, bbox_inches="tight"
    )
    plt.close(fig)
    print("   ✓ QFLX_EVAP_TOT (auto-computed) timeseries saved")

    fig = plot_seasonal(run, "QFLX_EVAP_TOT")
    fig.savefig(output_dir / "QFLX_EVAP_TOT_seasonal.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("   ✓ QFLX_EVAP_TOT seasonal plot saved\n")
except Exception as e:
    print(f"   ✗ Error: {e}\n")

# Create a multi-panel figure
print("3. Creating multi-panel comparison figure...")
try:
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle("Oak Harbor Site - Multiple Variables", fontsize=14, fontweight="bold")

    plot_timeseries(run, "GPP", ax=axes[0, 0])
    axes[0, 0].set_title("GPP - Time Series")

    plot_seasonal(run, "RAIN", ax=axes[0, 1])
    axes[0, 1].set_title("RAIN - Seasonal Cycle")

    plot_histogram(run, "FSH", bins=20, ax=axes[1, 0])
    axes[1, 0].set_title("FSH - Distribution")

    plot_seasonal(run, "EFLX_LH_TOT", ax=axes[1, 1])
    axes[1, 1].set_title("EFLX_LH_TOT - Seasonal Cycle")

    fig.tight_layout()
    fig.savefig(output_dir / "multi_panel_summary.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print("   ✓ Multi-panel figure saved\n")
except Exception as e:
    print(f"   ✗ Error creating multi-panel: {e}\n")

print("=" * 70)
print("✓ All plotting tests complete!")
print(f"✓ Plots saved to: {output_dir.absolute()}")
print("=" * 70)

# List generated files
print("\nGenerated files:")
for i, f in enumerate(sorted(output_dir.glob("*.png")), 1):
    print(f"  {i:2d}. {f.name}")
