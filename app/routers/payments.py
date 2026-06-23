from fastapi import APIRouter

router = APIRouter(prefix="/payments", tags=["payments"])


# POST /payments/android/verify               — PAY-001
# POST /payments/android/refund-notification  — PAY-001
# POST /payments/ios/verify                   — PAY-001
# POST /payments/ios/refund-notification      — PAY-001
