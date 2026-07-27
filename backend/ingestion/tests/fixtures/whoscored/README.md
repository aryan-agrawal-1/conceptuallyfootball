# Sanitized WhoScored foundation fixtures

These fixtures are hand-authored, synthetic, and intentionally minimal. Team,
player, match, event, and qualifier identifiers do not come from WhoScored.
They preserve only the field shapes needed to test the source adapter and
future normalization work.

Do not replace them with a downloaded match-centre payload. Complete provider
payloads belong only in the ignored `backend/.soccerdata/` cache or another
approved private backend store.

The two match payloads jointly cover passes and typed qualifiers, every v1 shot
outcome, touches, take-ons, defensive actions, fouls/cards/offside,
substitutions, an event without a player ID, an unknown event/qualifier, and a
synthetic player appearing for a different team in the second match.
