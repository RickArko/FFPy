# NFL Play Level Database
Design a play-level features database for use in the project.


## Implementation Strategy

  1. Data Source Recommendation
  - `nflverse` via `n`flreadpy` - Free, open-source, 26 years of data (1999-2025)
  - 372+ fields including advanced analytics *(EPA, WPA, CPOE)*

  2. Database Schema Design
  Complete schema for 4 new tables:
      1. `plays` - Main play-by-play data (~40k plays/season)
      2. `games` - Game-level metadata
      3. `ftn_charting` - Advanced formation/personnel data (2022+)
      4. `snap_counts` - Player participation data (2012+)

  3. Implementation Plan
  - `Phase 1`: Foundation (schema + test data)
  - `Phase 2`: Historical data loading (5 seasons)
  - `Phase 3`: Query interface
  - `Phase 4`: UI integration