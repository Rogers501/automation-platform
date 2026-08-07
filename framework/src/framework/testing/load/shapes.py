"""Load-profile shapes for staged ramp-up / spike / wave patterns.

Defines a serializable :class:`LoadProfile` (YAML-driven) that the Locust
integration layer translates into a ``LoadTestShape``. Pure Python: no Locust
import here (rule 11).

A load profile is a sequence of :class:`RampStage` entries. Each stage ramps
to a target user count at a given spawn rate, then holds for ``duration``.
Locust's ``tick()`` method consumes the profile timeline to produce
``(user_count, spawn_rate)`` per second.

YAML example::

    profile:
      stages:
        - name: ramp_up
          target_users: 50
          spawn_rate: 5
          duration: 30
        - name: hold
          target_users: 50
          spawn_rate: 0
          duration: 60
        - name: ramp_down
          target_users: 0
          spawn_rate: 10
          duration: 10
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["LoadProfile", "LoadProfileError", "RampStage", "load_profile"]


class LoadProfileError(Exception):
    """Raised when a load profile is invalid."""


class RampStage(BaseModel):
    """A single stage in a load profile.

    Attributes:
        name: Stage label (for logging / reporting).
        target_users: User count to reach by the end of this stage.
        spawn_rate: Users spawned per second (0 = hold at target).
        duration: Stage length in seconds.
    """

    model_config = ConfigDict(extra="ignore")

    name: str = ""
    target_users: int
    spawn_rate: float = 0.0
    duration: int = 0


class LoadProfile(BaseModel):
    """A complete load profile (sequence of ramp stages).

    Attributes:
        stages: Ordered list of :class:`RampStage`.
        stop_after_last: If True, stop the test after the last stage
            (default). If False, continue running indefinitely.
    """

    model_config = ConfigDict(extra="ignore")

    stages: list[RampStage] = Field(default_factory=list)
    stop_after_last: bool = True

    @property
    def total_duration(self) -> int:
        """Total profile duration in seconds (sum of all stage durations)."""
        return sum(s.duration for s in self.stages)

    def tick(self, elapsed_seconds: float) -> tuple[int, float] | None:
        """Return (user_count, spawn_rate) for a given elapsed time.

        Returns ``None`` when the profile is finished (signals Locust to stop).

        Args:
            elapsed_seconds: Seconds since the load test started.

        Returns:
            Tuple of (target_user_count, spawn_rate), or None to stop.
        """
        if not self.stages:
            return None

        cumulative = 0.0
        prev_users = 0
        for stage in self.stages:
            stage_end = cumulative + stage.duration
            if elapsed_seconds < stage_end:
                if stage.duration <= 0:
                    return stage.target_users, stage.spawn_rate
                progress = (elapsed_seconds - cumulative) / stage.duration
                users = int(prev_users + (stage.target_users - prev_users) * progress)
                return users, stage.spawn_rate
            cumulative = stage_end
            prev_users = stage.target_users

        if self.stop_after_last:
            return None
        return self.stages[-1].target_users, 0.0


def load_profile(data: dict[str, Any]) -> LoadProfile:
    """Build a :class:`LoadProfile` from a parsed YAML mapping.

    Expects a ``profile`` key with a ``stages`` list, or a top-level
    ``stages`` list.

    Args:
        data: Parsed YAML dict.

    Returns:
        A validated :class:`LoadProfile`.

    Raises:
        LoadProfileError: If the data is not a valid profile.
    """
    if not isinstance(data, dict):
        raise LoadProfileError("profile must be a mapping")
    profile_data = data.get("profile", data)
    if not isinstance(profile_data, dict):
        raise LoadProfileError("profile section must be a mapping")
    stages = profile_data.get("stages", [])
    if not isinstance(stages, list) or not stages:
        raise LoadProfileError("profile must have a non-empty 'stages' list")
    try:
        return LoadProfile.model_validate(profile_data)
    except Exception as exc:
        raise LoadProfileError(f"invalid load profile: {exc}") from exc
