# CBS spike notes (2026-10-04)

No member token was available, so this file records live anonymous probes plus
field names read by the current CBS football client in
`uberfastman/fantasy-football-metrics-weekly-report` (`ffmwr/dao/platforms/cbs.py`
and `position_mapping.json`). League body fixtures use those keys with synthetic
values. They are not a capture of a real dynasty league. Do not put a token,
email, or owner name from a real account in this directory.

## Token

- Query parameter name on `https://api.cbssports.com/fantasy` is `access_token`.
  Observed: `GET /league/details?league_id=1&access_token=invalid` returns
  HTTP 400 `text/plain` body `Failed Authentication: error - invalid access token`.
- Missing `league_id` (no token) is HTTP 400 `text/plain` `Missing league_id`.
- `league_id` with no token is HTTP 500 JSON
  `body.type=internal_server_error`, not 401. Do not treat every 500 as an expired session.
- A current football client also sends the token as an `Authorization` header to
  `https://{league}.football.cbssports.com/api`. The browser cookie name was not
  observed. The connect bookmarklet reads `access_token` from the page URL and
  from resource URLs already loaded on that page.
- Token TTL was not measured. Reconnect copy stays mandatory.
- Whether one token lists every league on the account was not observed.

## Public player list

`GET /fantasy/players/list?sport=football` is anonymous (HTTP 200). Envelope keys:
`statusCode`, `statusMessage`, `uri`, `uriAlias`, `body.players[]`.

Observed player keys: `id`, `elias_id`, `firstname`, `lastname`, `fullname`,
`position`, `pro_team`, `pro_status`, `bye_week`, `eligible_positions_display`.
DST rows use `position=DST`, `fullname` as the nickname (`49ers`), and `pro_team`
as the abbreviation (`SF`). Import names those `{ABBR} DST`.

## League resources that exist

These paths answer (400/500) rather than an HTML 404, so they are routed:
`/league/details`, `/league/teams`, `/league/rosters`, `/league/rules`,
`/league/scoring/categories`, `/league/schedules`, `/league/draft/results`.

Field names below are the ones the ffmwr client reads. Draft results are unused
until a real payload shows a keeper flag we do not already have.

## Dynasty / roster / scoring keys the importer honors

- `body.league_details`: `name`, `num_teams`
- `body.rules.roster.positions[]`: `abbr`, `max_active`
- `body.rules.roster.statuses[]`: `description`, `max`, `abbr`
- `body.rules.schedule.num_playoff_teams.value`
- CBS abbr map (ffmwr): `DST` defense, `RS` bench, `I` IR, `RB-WR-TE` flex,
  `FLEX` superflex (`OP`), `DL-LB-DB` IDP flex. `DL`/`LB`/`DB` stay on the roster
  and are listed in `idp_positions`, not in optimizer `roster_positions`.
- Taxi: `roster_status` or `roster_pos` of `TX`/`TAXI`/`TAX`, or a rules status
  whose `description` contains "taxi". Not confirmed on a live league.
- Keeper: `wildcards.contract` when present (seen in a public CBS roster thread).
  Absent on a payload means no keeper tag.
- Scoring: `body.scoring_categories[]` with `abbr` or `name` plus `points`.
  `stats_categories` in the same client is a list of `{abbr, name}`; the points
  field is the scoring resource. Mapped onto Sleeper keys
  `rec`, `pass_yd`, `pass_td`, `rush_yd`, `rush_td`, `rec_yd`, `rec_td`,
  `pass_int`, `fum_lost`.
- Rosters: `body.rosters.teams[].players[]` with `id`, `fullname`, `position`,
  `pro_team`, `roster_status`, `roster_pos`.
- Schedule: `body.schedule.periods[]` with `label` and `matchups[].home_team` /
  `away_team` (`id`, `points`).
- Standings: `body.overall_standings.teams[]` with `wins`, `losses`, `ties`,
  `points_scored`, `points_against`, `order`.
