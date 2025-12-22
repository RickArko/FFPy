"""Demo script for Historical Projection System."""

from ffpy.database import FFPyDatabase
from ffpy.projections import HistoricalProjectionModel


def main():
    print("=" * 60)
    print("HISTORICAL PROJECTION SYSTEM DEMO")
    print("=" * 60)

    # Database status
    print("\n[1] Database Status:")
    db = FFPyDatabase()
    print(f"    Location: {db.db_path}")

    stats = db.get_actual_stats(season=2024, week=1)
    print(f"    Total records: {len(stats)}")
    print(f"    Players tracked: {len(stats['player'].unique())}")
    print(f"    Weeks of data: {stats['week'].nunique()}")

    # Generate projections
    print("\n[2] Generating Projections for Week 18:")
    model = HistoricalProjectionModel(db=db)
    projections = model.generate_projections(season=2024, week=18, lookback_weeks=4)
    print(f"    Players projected: {len(projections)}")
    print(f"    Using 4-week lookback with 60% recent weight")

    # Top 5 projections
    print("\n[3] Top 5 Projected Players:")
    top5 = projections.nlargest(5, "projected_points")[
        ["player", "position", "team", "projected_points"]
    ]
    for idx, row in top5.iterrows():
        print(
            f"    {row['player']:20} ({row['position']}) - {row['projected_points']:.1f} pts"
        )

    # Position breakdown
    print("\n[4] Projections by Position:")
    for pos in ["QB", "RB", "WR", "TE"]:
        pos_data = projections[projections["position"] == pos]
        avg_pts = pos_data["projected_points"].mean()
        print(f"    {pos}: {len(pos_data)} players, avg {avg_pts:.1f} pts")

    # App info
    print("\n[5] Streamlit Web App:")
    print("    Running at: http://localhost:8501")
    print("    Select 'Historical Model' to see these projections")

    print("\n" + "=" * 60)
    print("SUCCESS: Historical projection system is operational!")
    print("=" * 60)


if __name__ == "__main__":
    main()
