"""Provider-neutral, immutable match-clock boundaries.

The event provider's display clock is deliberately kept out of this module.  The
normalizer supplies continuous played-time boundaries; consumers only deal in
half-open integer-second intervals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from ingestion.models import MatchEventPeriod


CLOCK_CALCULATION_VERSION = "match_clock_v1"
SUPPORTED_PERIODS = (
    MatchEventPeriod.FIRST_HALF,
    MatchEventPeriod.SECOND_HALF,
    MatchEventPeriod.FIRST_EXTRA_TIME,
    MatchEventPeriod.SECOND_EXTRA_TIME,
)
NOMINAL_PERIOD_SECONDS = {
    MatchEventPeriod.FIRST_HALF: 45 * 60,
    MatchEventPeriod.SECOND_HALF: 45 * 60,
    MatchEventPeriod.FIRST_EXTRA_TIME: 15 * 60,
    MatchEventPeriod.SECOND_EXTRA_TIME: 15 * 60,
}


class MatchClockError(ValueError):
    """Raised when played-time metadata cannot define a reliable timeline."""

    def __init__(
        self, code: str, message: str, *, details: Mapping[str, Any] | None = None
    ):
        self.code = code
        self.details = dict(details or {})
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class MatchClockPeriod:
    period: int
    period_index: int
    start_second: int
    end_second: int
    nominal_duration_seconds: int

    @property
    def duration_seconds(self) -> int:
        return self.end_second - self.start_second

    @property
    def nominal_end_second(self) -> int:
        return self.start_second + self.nominal_duration_seconds

    def contains(self, second: int) -> bool:
        return self.start_second <= second < self.end_second

    def is_added_time(self, second: int) -> bool:
        return second >= self.nominal_end_second


@dataclass(frozen=True, slots=True)
class MatchClock:
    periods: tuple[MatchClockPeriod, ...]
    supported_end_second: int
    calculation_version: str = CLOCK_CALCULATION_VERSION

    @property
    def supported_start_second(self) -> int:
        return self.periods[0].start_second

    @property
    def exposure_seconds(self) -> int:
        return sum(period.duration_seconds for period in self.periods)

    def period_for(self, period: int) -> MatchClockPeriod | None:
        return next((value for value in self.periods if value.period == period), None)

    def period_at(self, second: int) -> MatchClockPeriod | None:
        return next((value for value in self.periods if value.contains(second)), None)

    def boundary_seconds(
        self, *, include_nominal_boundaries: bool = False
    ) -> tuple[int, ...]:
        values = {self.supported_start_second, self.supported_end_second}
        for period in self.periods:
            values.update((period.start_second, period.end_second))
            if (
                include_nominal_boundaries
                and period.nominal_end_second < period.end_second
            ):
                values.add(period.nominal_end_second)
        return tuple(sorted(values))

    def as_dict(self) -> dict[str, Any]:
        return {
            "calculation_version": self.calculation_version,
            "supported_end_second": self.supported_end_second,
            "periods": [
                {
                    "period": int(period.period),
                    "period_index": period.period_index,
                    "start_second": period.start_second,
                    "end_second": period.end_second,
                    "duration_seconds": period.duration_seconds,
                    "nominal_duration_seconds": period.nominal_duration_seconds,
                }
                for period in self.periods
            ],
        }


def match_clock_from_mapping(value: Mapping[str, Any]) -> MatchClock:
    """Parse the provider-neutral mapping emitted by event normalization."""
    if value.get("valid") is False:
        code = str(value.get("exclusion_reason") or "clock_metadata_invalid")
        raise MatchClockError(code, "Normalization excluded the supplied match clock.")
    raw_periods = value.get("periods")
    if not isinstance(raw_periods, Sequence) or isinstance(raw_periods, (str, bytes)):
        raise MatchClockError("clock_metadata_missing", "Clock periods are missing.")
    periods: list[MatchClockPeriod] = []
    for default_index, raw_period in enumerate(raw_periods):
        if not isinstance(raw_period, Mapping):
            raise MatchClockError(
                "clock_metadata_invalid", "A clock period is not an object."
            )
        try:
            period = int(raw_period["period"])
            period_index = int(raw_period.get("period_index", default_index))
            start_second = int(raw_period["start_second"])
            end_second = int(raw_period["end_second"])
            nominal_duration = int(
                raw_period.get(
                    "nominal_duration_seconds", NOMINAL_PERIOD_SECONDS[period]
                )
            )
        except (KeyError, TypeError, ValueError) as error:
            raise MatchClockError(
                "clock_metadata_invalid", "A clock period contains invalid values."
            ) from error
        periods.append(
            MatchClockPeriod(
                period=period,
                period_index=period_index,
                start_second=start_second,
                end_second=end_second,
                nominal_duration_seconds=nominal_duration,
            )
        )
    supported_end = value.get("supported_end_second")
    if supported_end is None and periods:
        supported_end = periods[-1].end_second
    try:
        supported_end_second = int(supported_end)
    except (TypeError, ValueError) as error:
        raise MatchClockError(
            "clock_metadata_invalid", "Clock end is invalid."
        ) from error
    clock = MatchClock(
        periods=tuple(periods),
        supported_end_second=supported_end_second,
        calculation_version=str(
            value.get("calculation_version") or CLOCK_CALCULATION_VERSION
        ),
    )
    validate_match_clock(clock)
    return clock


def match_clock_from_period_rows(rows: Iterable[Any]) -> MatchClock:
    ordered = sorted(rows, key=lambda row: (row.period_index, row.period))
    if not ordered:
        raise MatchClockError("clock_metadata_missing", "No played-period rows exist.")
    return match_clock_from_mapping(
        {
            "calculation_version": ordered[0].calculation_version,
            "supported_end_second": ordered[-1].end_second,
            "periods": [
                {
                    "period": row.period,
                    "period_index": row.period_index,
                    "start_second": row.start_second,
                    "end_second": row.end_second,
                    "nominal_duration_seconds": NOMINAL_PERIOD_SECONDS[int(row.period)],
                }
                for row in ordered
            ],
        }
    )


def coerce_match_clock(
    value: MatchClock | Mapping[str, Any] | Iterable[Any],
) -> MatchClock:
    if isinstance(value, MatchClock):
        validate_match_clock(value)
        return value
    if isinstance(value, Mapping):
        return match_clock_from_mapping(value)
    return match_clock_from_period_rows(value)


def validate_match_clock(clock: MatchClock) -> None:
    if not clock.periods:
        raise MatchClockError("no_supported_play", "Clock has no supported periods.")
    if clock.periods[0].start_second != 0:
        raise MatchClockError(
            "clock_metadata_invalid", "Played time must start at zero."
        )
    seen_periods: set[int] = set()
    previous_end = 0
    for expected_index, period in enumerate(clock.periods):
        if period.period not in SUPPORTED_PERIODS or period.period in seen_periods:
            raise MatchClockError(
                "clock_metadata_invalid", "Clock periods are unsupported or duplicated."
            )
        if period.period_index != expected_index:
            raise MatchClockError(
                "clock_metadata_invalid", "Clock period indexes are not consecutive."
            )
        if period.start_second != previous_end:
            raise MatchClockError(
                "clock_metadata_invalid", "Clock periods contain a gap or overlap."
            )
        if (
            period.end_second <= period.start_second
            or period.nominal_duration_seconds <= 0
        ):
            raise MatchClockError(
                "clock_metadata_invalid", "Clock period duration is not positive."
            )
        seen_periods.add(period.period)
        previous_end = period.end_second
    if previous_end != clock.supported_end_second:
        raise MatchClockError(
            "clock_metadata_invalid", "Clock end does not match its last period."
        )
    if clock.exposure_seconds != clock.supported_end_second:
        raise MatchClockError(
            "clock_metadata_invalid", "Played-period durations do not reconcile."
        )


def validate_event_timestamp(event: Any, clock: MatchClock) -> int:
    second = getattr(event, "timeline_seconds", None)
    if second is None:
        raise MatchClockError(
            "event_timestamp_invalid",
            "Event has no canonical timeline timestamp.",
            details={"event_index": getattr(event, "event_index", None)},
        )
    try:
        second = int(second)
    except (TypeError, ValueError) as error:
        raise MatchClockError(
            "event_timestamp_invalid", "Event timestamp is invalid."
        ) from error
    period = clock.period_for(int(getattr(event, "period", MatchEventPeriod.UNKNOWN)))
    if period is None or not period.contains(second):
        raise MatchClockError(
            "event_timestamp_invalid",
            "Event timestamp falls outside its supported period.",
            details={
                "event_index": getattr(event, "event_index", None),
                "second": second,
            },
        )
    return second
