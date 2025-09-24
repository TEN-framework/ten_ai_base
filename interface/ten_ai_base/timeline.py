#
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0.
# See the LICENSE file for more information.
#
from enum import Enum
from typing import Callable, Optional


class AudioTimelineEventType(Enum):
    USER_AUDIO = 0
    SILENCE_AUDIO = 1


class AudioTimeline:
    def __init__(self, error_cb: Optional[Callable[[str], None]] = None):
        # Store timeline event list, each event is a tuple of (type, duration)
        self.timeline: list[tuple[AudioTimelineEventType, int]] = []
        self.total_user_audio_duration = 0
        self.total_silence_audio_duration = 0
        self.error_cb = error_cb

    def add_user_audio(self, duration_ms: int):
        """Add user audio

        Args:
            duration_ms: Audio duration in milliseconds
        """
        if duration_ms <= 0:
            return

        if self.timeline and self.timeline[-1][0] == AudioTimelineEventType.USER_AUDIO:
            # Merge adjacent user audio events
            self.timeline[-1] = (
                AudioTimelineEventType.USER_AUDIO,
                self.timeline[-1][1] + duration_ms,
            )
        else:
            self.timeline.append((AudioTimelineEventType.USER_AUDIO, duration_ms))

        self.total_user_audio_duration += duration_ms

    def add_silence_audio(self, duration_ms: int):
        """Add silence audio

        Args:
            duration_ms: Silence duration in milliseconds
        """
        if duration_ms <= 0:
            return

        if (
            self.timeline
            and self.timeline[-1][0] == AudioTimelineEventType.SILENCE_AUDIO
        ):
            # Merge adjacent silence events
            self.timeline[-1] = (
                AudioTimelineEventType.SILENCE_AUDIO,
                self.timeline[-1][1] + duration_ms,
            )
        else:
            self.timeline.append((AudioTimelineEventType.SILENCE_AUDIO, duration_ms))

        self.total_silence_audio_duration += duration_ms

    def get_audio_duration_before_time(self, time_ms: int) -> int:
        """
        Calculate the total duration of user audio before a specified timestamp.
        If time_ms exceeds the total timeline duration, an error callback will be invoked.

        Timeline diagram:
        Timeline: [USER_AUDIO:100ms] [SILENCE:50ms] [USER_AUDIO:200ms] [SILENCE:100ms]
        Time:     0              100            150              350             450

        Examples:
        - get_audio_duration_before_time(80)  -> 80ms  (within first USER_AUDIO segment)
        - get_audio_duration_before_time(120) -> 100ms (first USER_AUDIO + partial SILENCE)
        - get_audio_duration_before_time(200) -> 150ms (first 100ms + second 50ms)
        - get_audio_duration_before_time(500) -> 300ms (all USER_AUDIO, but error reported)

        Args:
            time_ms: The specified timestamp in milliseconds

        Returns:
            Total duration of user audio before the specified timestamp in milliseconds
        """
        if time_ms < 0:
            return 0

        total_user_audio_duration = 0
        current_time = 0

        # Calculate total timeline duration
        total_timeline_duration = sum(duration for _, duration in self.timeline)

        # Check if requested time exceeds timeline range
        if time_ms > total_timeline_duration:
            if self.error_cb is not None:
                try:
                    self.error_cb(
                        f"Requested time {time_ms}ms exceeds timeline duration {total_timeline_duration}ms"
                    )
                except Exception:
                    # Silently ignore callback errors to keep returning result normally
                    pass
            # When exceeding range, return total user audio duration in timeline
            return self.total_user_audio_duration

        # Iterate through timeline, accumulating user audio before specified time
        for event_type, duration in self.timeline:
            # Stop if current time has reached or exceeded target time
            if current_time >= time_ms:
                break

            if event_type == AudioTimelineEventType.USER_AUDIO:
                # If entire audio segment is before target time
                if current_time + duration <= time_ms:
                    total_user_audio_duration += duration
                else:
                    # If audio segment crosses target time, only count portion before target
                    partial_duration = time_ms - current_time
                    total_user_audio_duration += max(0, partial_duration)
                    break

            current_time += duration

        return total_user_audio_duration

    def get_total_user_audio_duration(self) -> int:
        return sum(
            duration
            for event, duration in self.timeline
            if event == AudioTimelineEventType.USER_AUDIO
        )

    def reset(self):
        self.timeline = []
