from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class AuthThrottle(AnonRateThrottle):
    scope = "auth"  # login / register / OTP: 10 per minute per IP


class DonationThrottle(UserRateThrottle):
    scope = "donation"
