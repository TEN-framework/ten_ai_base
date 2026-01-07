#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_ai_base.timeline import AudioTimeline, AudioTimelineEventType


# ============================================================================
# Basic Functionality Tests
# ============================================================================


def test_empty_timeline():
    """Test empty timeline"""
    timeline = AudioTimeline()
    assert len(timeline.timeline) == 0
    assert timeline.total_user_audio_duration == 0
    assert timeline.total_silence_audio_duration == 0
    assert timeline.get_total_user_audio_duration() == 0
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(1000) == 0


def test_single_user_audio():
    """Test single user audio segment"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)

    assert len(timeline.timeline) == 1
    assert timeline.timeline[0] == (AudioTimelineEventType.USER_AUDIO, 1000)
    assert timeline.total_user_audio_duration == 1000
    assert timeline.get_total_user_audio_duration() == 1000

    # Test get_audio_duration_before_time
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(500) == 500
    assert timeline.get_audio_duration_before_time(1000) == 1000


def test_single_silence_audio():
    """Test single silence segment"""
    timeline = AudioTimeline()
    timeline.add_silence_audio(500)

    assert len(timeline.timeline) == 1
    assert timeline.timeline[0] == (AudioTimelineEventType.SILENCE_AUDIO, 500)
    assert timeline.total_silence_audio_duration == 500
    assert timeline.get_total_user_audio_duration() == 0

    # Silence doesn't count as user audio
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(250) == 0
    assert timeline.get_audio_duration_before_time(500) == 0


def test_multiple_user_audio_segments():
    """Test multiple user audio segments"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_user_audio(500)
    timeline.add_user_audio(1500)

    # Should be merged into one segment
    assert len(timeline.timeline) == 1
    assert timeline.timeline[0] == (AudioTimelineEventType.USER_AUDIO, 3000)
    assert timeline.total_user_audio_duration == 3000

    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(1000) == 1000
    assert timeline.get_audio_duration_before_time(2000) == 2000
    assert timeline.get_audio_duration_before_time(3000) == 3000


def test_multiple_silence_segments():
    """Test multiple silence segments are merged"""
    timeline = AudioTimeline()
    timeline.add_silence_audio(200)
    timeline.add_silence_audio(300)
    timeline.add_silence_audio(500)

    # Should be merged into one segment
    assert len(timeline.timeline) == 1
    assert timeline.timeline[0] == (AudioTimelineEventType.SILENCE_AUDIO, 1000)
    assert timeline.total_silence_audio_duration == 1000
    assert timeline.get_total_user_audio_duration() == 0


# ============================================================================
# Mixed Audio Types Tests
# ============================================================================


def test_user_audio_then_silence():
    """Test user audio followed by silence"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)

    assert len(timeline.timeline) == 2
    assert timeline.timeline[0] == (AudioTimelineEventType.USER_AUDIO, 1000)
    assert timeline.timeline[1] == (AudioTimelineEventType.SILENCE_AUDIO, 500)

    # Test time calculations
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(500) == 500
    assert timeline.get_audio_duration_before_time(1000) == 1000
    assert timeline.get_audio_duration_before_time(1200) == 1000  # In silence
    assert timeline.get_audio_duration_before_time(1500) == 1000  # End of silence


def test_silence_then_user_audio():
    """Test silence followed by user audio"""
    timeline = AudioTimeline()
    timeline.add_silence_audio(500)
    timeline.add_user_audio(1000)

    assert len(timeline.timeline) == 2
    assert timeline.timeline[0] == (AudioTimelineEventType.SILENCE_AUDIO, 500)
    assert timeline.timeline[1] == (AudioTimelineEventType.USER_AUDIO, 1000)

    # During silence, no user audio counted
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(250) == 0
    assert timeline.get_audio_duration_before_time(500) == 0

    # After silence, user audio is counted
    assert timeline.get_audio_duration_before_time(750) == 250
    assert timeline.get_audio_duration_before_time(1000) == 500
    assert timeline.get_audio_duration_before_time(1500) == 1000


def test_alternating_user_and_silence():
    """Test alternating user audio and silence"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_user_audio(2000)
    timeline.add_silence_audio(300)
    timeline.add_user_audio(700)

    assert len(timeline.timeline) == 5
    assert timeline.total_user_audio_duration == 3700
    assert timeline.total_silence_audio_duration == 800

    # Test various time points
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(500) == 500  # First user audio
    assert timeline.get_audio_duration_before_time(1000) == 1000  # End of first user
    assert timeline.get_audio_duration_before_time(1250) == 1000  # In first silence
    assert timeline.get_audio_duration_before_time(1500) == 1000  # End of first silence
    assert timeline.get_audio_duration_before_time(2000) == 1500  # In second user
    assert timeline.get_audio_duration_before_time(3500) == 3000  # End of second user
    assert timeline.get_audio_duration_before_time(3700) == 3000  # In second silence
    assert timeline.get_audio_duration_before_time(4500) == 3700  # All audio


def test_complex_timeline():
    """Test complex timeline from documentation example"""
    timeline = AudioTimeline()
    # Timeline: [USER_AUDIO:100ms] [SILENCE:50ms] [USER_AUDIO:200ms] [SILENCE:100ms]
    timeline.add_user_audio(100)
    timeline.add_silence_audio(50)
    timeline.add_user_audio(200)
    timeline.add_silence_audio(100)

    assert timeline.total_user_audio_duration == 300
    assert timeline.total_silence_audio_duration == 150

    # Examples from documentation
    assert timeline.get_audio_duration_before_time(80) == 80
    assert timeline.get_audio_duration_before_time(120) == 100
    assert timeline.get_audio_duration_before_time(200) == 150
    assert timeline.get_audio_duration_before_time(350) == 300


# ============================================================================
# Edge Cases Tests
# ============================================================================


def test_zero_duration_audio():
    """Test that zero duration audio is ignored"""
    timeline = AudioTimeline()
    timeline.add_user_audio(0)
    timeline.add_silence_audio(0)

    assert len(timeline.timeline) == 0
    assert timeline.total_user_audio_duration == 0
    assert timeline.total_silence_audio_duration == 0


def test_negative_duration_audio():
    """Test that negative duration audio is ignored"""
    timeline = AudioTimeline()
    timeline.add_user_audio(-100)
    timeline.add_silence_audio(-50)

    assert len(timeline.timeline) == 0
    assert timeline.total_user_audio_duration == 0
    assert timeline.total_silence_audio_duration == 0


def test_time_at_exact_boundaries():
    """Test get_audio_duration_before_time at exact segment boundaries"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_user_audio(2000)

    # At exact boundaries
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(1000) == 1000
    assert timeline.get_audio_duration_before_time(1500) == 1000
    assert timeline.get_audio_duration_before_time(3500) == 3000


def test_time_beyond_timeline():
    """Test behavior when requested time exceeds timeline duration"""
    errors = []

    def error_cb(msg):
        errors.append(msg)

    timeline = AudioTimeline(error_cb=error_cb)
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)

    # Request time beyond timeline
    result = timeline.get_audio_duration_before_time(2000)

    # Should return total user audio duration
    assert result == 1000
    # Should call error callback
    assert len(errors) == 1
    assert "exceeds timeline duration" in errors[0]
    assert "2000ms" in errors[0]
    assert "1500ms" in errors[0]


def test_negative_time():
    """Test behavior with negative time"""
    errors = []

    def error_cb(msg):
        errors.append(msg)

    timeline = AudioTimeline(error_cb=error_cb)
    timeline.add_user_audio(1000)

    result = timeline.get_audio_duration_before_time(-500)

    # Should return 0
    assert result == 0
    # Should call error callback
    assert len(errors) == 1
    assert "less than 0" in errors[0]
    assert "-500ms" in errors[0]


def test_error_callback_exception_handling():
    """Test that exceptions in error callback are silently ignored"""

    def error_cb(msg):
        raise ValueError("Error callback failed!")

    timeline = AudioTimeline(error_cb=error_cb)
    timeline.add_user_audio(1000)

    # Should not raise exception even though callback raises
    result = timeline.get_audio_duration_before_time(-100)
    assert result == 0

    result = timeline.get_audio_duration_before_time(2000)
    assert result == 1000


# ============================================================================
# Partial Segment Calculation Tests
# ============================================================================


def test_partial_user_audio_segment():
    """Test calculation within a user audio segment"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)

    # Test various points within the segment
    assert timeline.get_audio_duration_before_time(0) == 0
    assert timeline.get_audio_duration_before_time(100) == 100
    assert timeline.get_audio_duration_before_time(250) == 250
    assert timeline.get_audio_duration_before_time(500) == 500
    assert timeline.get_audio_duration_before_time(750) == 750
    assert timeline.get_audio_duration_before_time(999) == 999
    assert timeline.get_audio_duration_before_time(1000) == 1000


def test_partial_calculation_crossing_boundary():
    """Test partial calculation when time falls in silence after user audio"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)

    # Time in silence - should return all previous user audio
    assert timeline.get_audio_duration_before_time(1100) == 1000
    assert timeline.get_audio_duration_before_time(1250) == 1000
    assert timeline.get_audio_duration_before_time(1499) == 1000


def test_partial_second_user_audio_segment():
    """Test partial calculation in second user audio segment"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_user_audio(2000)

    # Time in second user audio segment
    assert timeline.get_audio_duration_before_time(1600) == 1100  # 100ms into second
    assert timeline.get_audio_duration_before_time(2000) == 1500  # 500ms into second
    assert timeline.get_audio_duration_before_time(2500) == 2000  # 1000ms into second
    assert timeline.get_audio_duration_before_time(3000) == 2500  # 1500ms into second
    assert timeline.get_audio_duration_before_time(3500) == 3000  # All of second


# ============================================================================
# Reset Functionality Tests
# ============================================================================


def test_reset_empty_timeline():
    """Test reset on empty timeline"""
    timeline = AudioTimeline()
    timeline.reset()

    assert len(timeline.timeline) == 0
    assert timeline.total_user_audio_duration == 0
    assert timeline.total_silence_audio_duration == 0


def test_reset_with_data():
    """Test reset clears all data"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_user_audio(2000)

    # Verify data exists
    assert len(timeline.timeline) == 3
    assert timeline.total_user_audio_duration == 3000
    assert timeline.total_silence_audio_duration == 500

    # Reset
    timeline.reset()

    # Verify everything is cleared
    assert len(timeline.timeline) == 0
    assert timeline.total_user_audio_duration == 0
    assert timeline.total_silence_audio_duration == 0
    assert timeline.get_audio_duration_before_time(1000) == 0


def test_reset_and_reuse():
    """Test timeline can be reused after reset"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.reset()

    # Add new data
    timeline.add_user_audio(500)
    timeline.add_silence_audio(250)

    assert len(timeline.timeline) == 2
    assert timeline.total_user_audio_duration == 500
    assert timeline.total_silence_audio_duration == 250
    assert timeline.get_audio_duration_before_time(500) == 500


# ============================================================================
# Large Values Tests
# ============================================================================


def test_large_duration_values():
    """Test with large duration values"""
    timeline = AudioTimeline()
    # Simulate 1 hour of audio
    timeline.add_user_audio(3600000)  # 1 hour in ms
    timeline.add_silence_audio(1800000)  # 30 minutes

    assert timeline.total_user_audio_duration == 3600000
    assert timeline.total_silence_audio_duration == 1800000

    # Test calculation at 45 minutes (2700000ms)
    assert timeline.get_audio_duration_before_time(2700000) == 2700000
    # Test at 1 hour 15 minutes (in silence)
    assert timeline.get_audio_duration_before_time(4500000) == 3600000


def test_many_small_segments():
    """Test with many small segments"""
    timeline = AudioTimeline()

    # Add 100 segments of 10ms each
    for _ in range(100):
        timeline.add_user_audio(10)

    # Should be merged into one segment
    assert len(timeline.timeline) == 1
    assert timeline.total_user_audio_duration == 1000
    assert timeline.get_audio_duration_before_time(500) == 500


# ============================================================================
# get_total_user_audio_duration Tests
# ============================================================================


def test_get_total_user_audio_duration_empty():
    """Test get_total_user_audio_duration on empty timeline"""
    timeline = AudioTimeline()
    assert timeline.get_total_user_audio_duration() == 0


def test_get_total_user_audio_duration_only_silence():
    """Test get_total_user_audio_duration with only silence"""
    timeline = AudioTimeline()
    timeline.add_silence_audio(1000)
    assert timeline.get_total_user_audio_duration() == 0


def test_get_total_user_audio_duration_mixed():
    """Test get_total_user_audio_duration with mixed audio"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_user_audio(2000)
    timeline.add_silence_audio(300)

    assert timeline.get_total_user_audio_duration() == 3000

#
# Copyright © 2025 Agora
# This file is part of TEN Framework, an open source project.
# Licensed under the Apache License, Version 2.0, with certain conditions.
# Refer to the "LICENSE" file in the root directory for more information.
#

from ten_ai_base.timeline import AudioTimeline, AudioTimelineEventType


# ============================================================================
# Dropped Audio Basic Functionality Tests
# ============================================================================


def test_dropped_audio_basic():
    """Test basic dropped audio functionality"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(3000)
    timeline.add_user_audio(1000)

    assert timeline.total_dropped_audio_duration == 3000
    assert timeline.total_user_audio_duration == 1000
    # get_total_user_audio_duration should include dropped audio
    assert timeline.get_total_user_audio_duration() == 4000

    # Provider time 0 should map to 3000 real audio time (after dropped audio)
    assert timeline.get_audio_duration_before_time(0) == 3000
    # Provider time 500 should map to 3500 real audio time
    assert timeline.get_audio_duration_before_time(500) == 3500
    # Provider time 1000 should map to 4000 real audio time
    assert timeline.get_audio_duration_before_time(1000) == 4000


def test_dropped_audio_requirement_example():
    """Test the exact requirement: 3s dropped, provider returns 1s, real should be 4s"""
    timeline = AudioTimeline()
    # Drop first 3 seconds
    timeline.add_dropped_audio(3000)
    # Then send audio to provider
    timeline.add_user_audio(2000)

    # Provider returns 1000ms
    provider_time = 1000
    real_audio_time = timeline.get_audio_duration_before_time(provider_time)

    # Real audio time should be 4000ms (3000 dropped + 1000)
    assert real_audio_time == 4000


def test_only_dropped_audio():
    """Test timeline with only dropped audio"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(5000)

    # Provider timeline is empty, but real audio time includes dropped
    assert timeline.get_audio_duration_before_time(0) == 5000
    # get_total_user_audio_duration should include dropped audio
    assert timeline.get_total_user_audio_duration() == 5000


def test_dropped_audio_merging():
    """Test that consecutive dropped audio segments are merged"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(1000)
    timeline.add_dropped_audio(1000)
    timeline.add_dropped_audio(1000)

    # Should be merged into one segment
    assert len(timeline.timeline) == 1
    assert timeline.timeline[0] == (AudioTimelineEventType.DROPPED_AUDIO, 3000)
    assert timeline.total_dropped_audio_duration == 3000


# ============================================================================
# Dropped Audio + User Audio Combination Tests
# ============================================================================


def test_dropped_then_user():
    """Test dropped audio followed by user audio"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(2000)
    timeline.add_user_audio(1000)

    assert timeline.get_audio_duration_before_time(0) == 2000
    assert timeline.get_audio_duration_before_time(500) == 2500
    assert timeline.get_audio_duration_before_time(1000) == 3000


def test_user_then_dropped_then_user():
    """Test user audio, then dropped, then user audio"""
    timeline = AudioTimeline()
    timeline.add_user_audio(1000)
    timeline.add_dropped_audio(2000)
    timeline.add_user_audio(500)

    # Provider sees: [USER:1000] [USER:500]
    # Real audio: [USER:1000] [DROPPED:2000] [USER:500]
    # Provider time 0 -> real time 0
    assert timeline.get_audio_duration_before_time(0) == 0
    # Provider time 1000 -> real time 1000
    assert timeline.get_audio_duration_before_time(1000) == 1000
    # Provider time 1000+ -> starts adding dropped audio
    # At provider 1001, we're past first user, add dropped, then into second user
    # Actually, provider time 1001 means 1ms into second user audio
    # Real time = 1000 (first user) + 2000 (dropped) + 1 (partial second user) = 3001
    assert timeline.get_audio_duration_before_time(1001) == 3001
    assert timeline.get_audio_duration_before_time(1500) == 3500


def test_multiple_dropped_segments():
    """Test multiple dropped audio segments"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(1000)
    timeline.add_user_audio(500)
    timeline.add_dropped_audio(2000)
    timeline.add_user_audio(1000)

    # Provider timeline: [USER:500] [USER:1000] (continuous from provider's view)
    # Real audio timeline: [DROPPED:1000] [USER:500] [DROPPED:2000] [USER:1000]
    
    # Provider time 0 -> after first dropped = 1000
    assert timeline.get_audio_duration_before_time(0) == 1000
    # Provider time 500 -> 1000 (dropped1) + 500 (user1) = 1500
    assert timeline.get_audio_duration_before_time(500) == 1500
    # Provider time 1000 -> 1000 (dropped1) + 500 (user1) + 2000 (dropped2) + 500 (user2) = 4000
    assert timeline.get_audio_duration_before_time(1000) == 4000
    # Provider time 1500 -> 1000 + 500 + 2000 + 1000 = 4500
    assert timeline.get_audio_duration_before_time(1500) == 4500


# ============================================================================
# Dropped Audio + Silence Combination Tests
# ============================================================================


def test_dropped_with_silence():
    """Test dropped audio with silence"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(3000)
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_user_audio(2000)

    # Provider timeline: [USER:1000] [SILENCE:500] [USER:2000]
    # Real audio timeline: [DROPPED:3000] [USER:1000] [USER:2000]
    
    # Provider time 0 -> 3000 (dropped)
    assert timeline.get_audio_duration_before_time(0) == 3000
    # Provider time 1000 -> 3000 + 1000 = 4000
    assert timeline.get_audio_duration_before_time(1000) == 4000
    # Provider time 1200 (in silence) -> still 4000 (silence excluded)
    assert timeline.get_audio_duration_before_time(1200) == 4000
    # Provider time 1500 (end of silence) -> still 4000
    assert timeline.get_audio_duration_before_time(1500) == 4000
    # Provider time 2000 -> 4000 + 500 = 4500
    assert timeline.get_audio_duration_before_time(2000) == 4500
    # Provider time 3500 -> 4000 + 2000 = 6000
    assert timeline.get_audio_duration_before_time(3500) == 6000


def test_silence_then_dropped():
    """Test silence followed by dropped audio"""
    timeline = AudioTimeline()
    timeline.add_silence_audio(500)
    timeline.add_dropped_audio(1000)
    timeline.add_user_audio(2000)

    # Provider timeline: [SILENCE:500] [USER:2000]
    # Provider time:      0          500         2500
    
    # Real world timeline: [SILENCE:500] [DROPPED:1000] [USER:2000]
    # Real time:           0          500           1500         3500
    
    # Real audio timeline (excluding silence): [DROPPED:1000] [USER:2000]
    # Real audio time:                         0           1000         3000
    
    # Provider time 0 (start of silence) -> real audio time 0 (silence excluded)
    assert timeline.get_audio_duration_before_time(0) == 0
    # Provider time 500 (end of silence) -> real audio time 0 (silence excluded, haven't reached user audio yet)
    # But we need to account for dropped audio that comes after silence
    # Actually at provider time 500, we've passed the silence, and the next thing is dropped audio (1000ms)
    # But we haven't "sent" anything past the silence yet, so we're at the boundary
    # Real audio position = 0 + 0 (no user audio sent yet)
    # Wait, this is confusing. Let me think differently...
    
    # At provider time 500, provider has received 500ms of silence
    # Real audio time should account for: dropped audio that exists between silence end and next user audio
    # But the dropped audio hasn't been "processed" yet from provider's perspective
    
    # I think the issue is: when do we count dropped audio?
    # Dropped audio should be counted when we pass it in the timeline
    # At provider time 500+, we start the user audio, which comes after dropped
    # So at provider time 500, we're at the boundary, just added the dropped audio offset
    
    # Actually, let me reconsider: provider time 500 means we're 500ms into what provider received
    # At this point, provider received silence
    # Real audio at this point = 0 (no user audio) + 0 (silence doesn't count)
    # The dropped audio comes AFTER this point in real world
    # So it shouldn't be counted yet
    
    # Let me test what actually happens:
    # At provider time 500: we've passed 500ms silence, haven't entered user audio yet
    # Real audio time = 0 (no real audio counted yet)
    assert timeline.get_audio_duration_before_time(500) == 0
    
    # At provider time 501: we're 1ms into user audio (from provider's view)
    # In real world, this 1ms user audio comes after dropped audio
    # Real audio time = 1000 (dropped) + 1 (user audio) = 1001
    assert timeline.get_audio_duration_before_time(501) == 1001
    
    # Provider time 1000 -> 500ms into user audio -> 1000 (dropped) + 500 (user) = 1500
    assert timeline.get_audio_duration_before_time(1000) == 1500
    # Provider time 2500 -> all user audio -> 1000 (dropped) + 2000 (user) = 3000
    assert timeline.get_audio_duration_before_time(2500) == 3000


# ============================================================================
# Complex Scenarios Tests
# ============================================================================


def test_complex_interleaved_all_types():
    """Test complex timeline with all event types interleaved"""
    timeline = AudioTimeline()
    # [DROPPED:500] [USER:1000] [SILENCE:200] [DROPPED:300] [USER:800] [SILENCE:100]
    timeline.add_dropped_audio(500)
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(200)
    timeline.add_dropped_audio(300)
    timeline.add_user_audio(800)
    timeline.add_silence_audio(100)

    # Provider timeline: [USER:1000] [SILENCE:200] [USER:800] [SILENCE:100]
    # Provider time:      0         1000        1200       2000        2100
    
    # Real audio timeline: [DROPPED:500] [USER:1000] [DROPPED:300] [USER:800]
    # Real audio time:      0          500        1500          1800       2600
    
    # Provider time 0 -> real audio 500 (first dropped)
    assert timeline.get_audio_duration_before_time(0) == 500
    # Provider time 1000 (end of first user) -> 500 + 1000 = 1500
    assert timeline.get_audio_duration_before_time(1000) == 1500
    # Provider time 1200 (in first silence) -> still 1500 (silence doesn't add to real audio)
    assert timeline.get_audio_duration_before_time(1200) == 1500
    # Provider time 1201 (1ms into second user from provider view, which comes after second dropped)
    # Real: 500 + 1000 + 300 + 1 = 1801
    assert timeline.get_audio_duration_before_time(1201) == 1801
    # Provider time 1500 (300ms into second user) -> 500 + 1000 + 300 + 300 = 2100
    assert timeline.get_audio_duration_before_time(1500) == 2100
    # Provider time 2100 (in second silence) -> 500 + 1000 + 300 + 800 = 2600
    assert timeline.get_audio_duration_before_time(2100) == 2600


def test_alternating_dropped_and_silence():
    """Test alternating dropped audio and silence"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(1000)
    timeline.add_silence_audio(500)
    timeline.add_dropped_audio(2000)
    timeline.add_user_audio(1000)

    # Provider timeline: [SILENCE:500] [USER:1000]
    # Provider time:      0          500        1500
    
    # Real world timeline: [DROPPED:1000] [SILENCE:500] [DROPPED:2000] [USER:1000]
    # Real time:           0           1000          1500          3500         4500
    
    # Real audio timeline: [DROPPED:1000] [DROPPED:2000] [USER:1000]
    # Real audio time:     0           1000          3000       4000
    
    # Provider time 0 (start of silence) -> real audio 1000 (first dropped before silence)
    assert timeline.get_audio_duration_before_time(0) == 1000
    # Provider time 500 (end of silence, before entering user audio)
    # At this point, we've passed first dropped and silence
    # But haven't entered the user audio yet (which comes after second dropped)
    # Real audio = 1000 (first dropped) + 0 (silence doesn't count) = 1000
    assert timeline.get_audio_duration_before_time(500) == 1000
    # Provider time 501 (1ms into user audio from provider view)
    # Real audio = 1000 (dropped1) + 2000 (dropped2) + 1 (user) = 3001
    assert timeline.get_audio_duration_before_time(501) == 3001
    # Provider time 1000 (500ms into user audio)
    # Real audio = 1000 + 2000 + 500 = 3500
    assert timeline.get_audio_duration_before_time(1000) == 3500
    # Provider time 1500 (all user audio)
    # Real audio = 1000 + 2000 + 1000 = 4000
    assert timeline.get_audio_duration_before_time(1500) == 4000


# ============================================================================
# Edge Cases Tests (Dropped Audio)
# ============================================================================


def test_zero_duration_dropped_audio():
    """Test that zero duration dropped audio is ignored"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(0)
    timeline.add_user_audio(1000)

    assert len(timeline.timeline) == 1
    assert timeline.total_dropped_audio_duration == 0
    assert timeline.get_audio_duration_before_time(500) == 500


def test_negative_duration_dropped_audio():
    """Test that negative duration dropped audio is ignored"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(-100)
    timeline.add_user_audio(1000)

    assert len(timeline.timeline) == 1
    assert timeline.total_dropped_audio_duration == 0


def test_time_beyond_timeline_with_dropped():
    """Test behavior when time exceeds timeline with dropped audio"""
    errors = []

    def error_cb(msg):
        errors.append(msg)

    timeline = AudioTimeline(error_cb=error_cb)
    timeline.add_dropped_audio(1000)
    timeline.add_user_audio(2000)

    # Request time beyond provider timeline
    result = timeline.get_audio_duration_before_time(3000)

    # Should return total real audio (user + dropped)
    assert result == 3000
    # Should call error callback
    assert len(errors) == 1
    assert "exceeds timeline duration" in errors[0]


def test_partial_user_audio_with_dropped():
    """Test partial user audio calculation with dropped audio"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(1000)
    timeline.add_user_audio(2000)

    # Test various points within the user audio segment
    assert timeline.get_audio_duration_before_time(0) == 1000
    assert timeline.get_audio_duration_before_time(100) == 1100
    assert timeline.get_audio_duration_before_time(500) == 1500
    assert timeline.get_audio_duration_before_time(1000) == 2000
    assert timeline.get_audio_duration_before_time(1500) == 2500
    assert timeline.get_audio_duration_before_time(2000) == 3000


# ============================================================================
# Reset Functionality Tests (Dropped Audio)
# ============================================================================


def test_reset_with_dropped_audio():
    """Test reset clears dropped audio tracking"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(3000)
    timeline.add_user_audio(1000)
    timeline.add_silence_audio(500)

    # Verify data exists
    assert timeline.total_dropped_audio_duration == 3000

    # Reset
    timeline.reset()

    # Verify everything is cleared
    assert len(timeline.timeline) == 0
    assert timeline.total_user_audio_duration == 0
    assert timeline.total_silence_audio_duration == 0
    assert timeline.total_dropped_audio_duration == 0
    assert timeline.get_audio_duration_before_time(1000) == 0


# ============================================================================
# Large Values Tests (Dropped Audio)
# ============================================================================


def test_large_dropped_audio_values():
    """Test with large dropped audio values"""
    timeline = AudioTimeline()
    # Simulate dropping 1 hour
    timeline.add_dropped_audio(3600000)
    # Then 30 minutes of user audio
    timeline.add_user_audio(1800000)

    # Provider time 0 should map to 1 hour real audio time
    assert timeline.get_audio_duration_before_time(0) == 3600000
    # Provider time 30 min should map to 1.5 hour real audio time
    assert timeline.get_audio_duration_before_time(1800000) == 5400000
    # Total user audio should include dropped audio (1.5 hours)
    assert timeline.get_total_user_audio_duration() == 5400000


# ============================================================================
# get_total_user_audio_duration Tests (with dropped audio)
# ============================================================================


def test_get_total_user_audio_duration_with_dropped():
    """Test get_total_user_audio_duration includes dropped audio"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(1000)
    timeline.add_user_audio(2000)
    timeline.add_dropped_audio(500)
    
    # Should include both USER_AUDIO and DROPPED_AUDIO
    assert timeline.get_total_user_audio_duration() == 3500


def test_get_total_user_audio_duration_mixed_with_silence():
    """Test get_total_user_audio_duration with all types"""
    timeline = AudioTimeline()
    timeline.add_dropped_audio(1000)
    timeline.add_user_audio(2000)
    timeline.add_silence_audio(500)
    timeline.add_dropped_audio(800)
    timeline.add_user_audio(1200)
    
    # Should include USER_AUDIO (2000 + 1200) + DROPPED_AUDIO (1000 + 800)
    # Should NOT include SILENCE_AUDIO (500)
    assert timeline.get_total_user_audio_duration() == 5000


def test_get_total_user_audio_duration_use_case():
    """Test typical use case: record total user audio before reset"""
    timeline = AudioTimeline()
    
    # Simulate a session
    timeline.add_dropped_audio(3000)  # First 3s dropped (e.g., VAD warmup)
    timeline.add_user_audio(10000)    # 10s user audio
    timeline.add_silence_audio(1000)  # 1s silence
    timeline.add_user_audio(5000)     # 5s user audio
    
    # Before reset, record total user audio received
    total_received = timeline.get_total_user_audio_duration()
    
    # Should be: 3000 (dropped) + 10000 (user) + 5000 (user) = 18000
    # Silence is NOT counted as it's not real user audio
    assert total_received == 18000
    
    # Reset
    timeline.reset()
    
    # After reset, should be 0
    assert timeline.get_total_user_audio_duration() == 0

