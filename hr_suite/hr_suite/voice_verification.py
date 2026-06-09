"""
voice_verification.py
Voice verification status constants for Hr Suite.

The full voice verification engine (biometric enrollment, audio processing)
has been removed. Only the status constants used by the Team Attendance
Review report are retained.
"""

# ─── Voice Profile Status Constants ───────────────────────────────────────────
VOICE_PROFILE_STATUS_NOT_ENROLLED = "Not Enrolled"
VOICE_PROFILE_STATUS_ENROLLED = "Enrolled"
VOICE_PROFILE_STATUS_SUSPENDED = "Suspended"

# ─── Voice Verification Status Constants ──────────────────────────────────────
VOICE_VERIFICATION_STATUS_NOT_REQUIRED = "Not Required"
VOICE_VERIFICATION_STATUS_PENDING = "Pending"
VOICE_VERIFICATION_STATUS_PASSED = "Passed"
VOICE_VERIFICATION_STATUS_FAILED = "Failed"
