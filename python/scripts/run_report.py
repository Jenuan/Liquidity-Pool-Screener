"""
Entrypoint script to generate a simple metrics report from the event log.

Usage:

    python scripts/run_report.py
"""

from lpbot.analytics import compute_basic_metrics


def main() -> None:
    """Compute and print basic metrics from the event log."""
    metrics = compute_basic_metrics()
    print("=== LP Bot Report ===")
    for key, value in metrics.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

    import sys
    import subprocess

    # If the script is being run directly, provide a subprocess-based self-test.
    print("\n--- Re-running via subprocess for test/demo purpose ---")
    result = subprocess.run(
        [sys.executable, __file__],
        capture_output=True,
        text=True
    )
    print("Subprocess output:\n", result.stdout.strip())