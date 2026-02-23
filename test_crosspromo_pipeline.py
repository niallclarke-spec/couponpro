"""
Temporary test script: Full TP1 → TP3 cross-promo pipeline via real code paths.
Enqueues jobs via trigger_tp_crosspromo(), then the running server's worker processes them.
Run with: python3 test_crosspromo_pipeline.py
Delete after testing.
"""
import os
import sys
import time

os.environ.setdefault('DOTENV_LOADED', '1')
from dotenv import load_dotenv
load_dotenv()

from domains.crosspromo.service import trigger_tp_crosspromo
from core.logging import get_logger

logger = get_logger('test_crosspromo')

TENANT_ID = 'entrylab'
SIGNAL_ID = 1479
SIGNAL_MSG_ID = 877
TP_MSG_ID = 877

def run_test():
    print("=" * 60)
    print("CROSS-PROMO PIPELINE TEST (Real Code Paths)")
    print("=" * 60)
    print()

    print("[STEP 1] Calling trigger_tp_crosspromo(tp_number=1)...")
    result1 = trigger_tp_crosspromo(
        tenant_id=TENANT_ID,
        signal_id=SIGNAL_ID,
        tp_number=1,
        signal_message_id=SIGNAL_MSG_ID,
        tp_message_id=TP_MSG_ID,
        pips_secured=86.0
    )
    print(f"  Result: {result1}")
    if not result1.get('success'):
        print(f"  ABORT: TP1 failed — {result1}")
        return
    print(f"  Jobs queued: forward_tp1_sequence + crosspromo_finish (30min timer)")
    print()

    print("[STEP 2] Waiting 8 seconds for worker to process TP1 jobs...")
    time.sleep(8)

    print("[STEP 3] Calling trigger_tp_crosspromo(tp_number=3)...")
    result3 = trigger_tp_crosspromo(
        tenant_id=TENANT_ID,
        signal_id=SIGNAL_ID,
        tp_number=3,
        signal_message_id=SIGNAL_MSG_ID,
        tp_message_id=TP_MSG_ID,
        pips_secured=194.0
    )
    print(f"  Result: {result3}")
    if not result3.get('success'):
        print(f"  ABORT: TP3 failed — {result3}")
        return
    print(f"  Jobs queued: forward_tp_update(tp3) + crosspromo_finish (5s timer)")
    print()

    print("=" * 60)
    print("TEST SUBMITTED SUCCESSFULLY")
    print()
    print("The cross-promo worker (running in the server) will now:")
    print("  1. Process forward_tp_update(tp3) — forward TP3 + hype celebration + promo")
    print("  2. Process crosspromo_finish (5s later) — mark complete + trigger hype bot")
    print("  3. Hype bot flow 'Brag' has 1-min delay — messages arrive ~1 min after finish")
    print()
    print("Watch the FREE channel and server logs for the messages.")
    print()
    print("To reset for future tests:")
    print(f"  DELETE FROM crosspromo_jobs WHERE tenant_id = '{TENANT_ID}' AND run_at >= CURRENT_DATE;")
    print(f"  DELETE FROM hype_messages WHERE tenant_id = '{TENANT_ID}' AND sent_at >= CURRENT_DATE;")
    print(f"  UPDATE forex_signals SET crosspromo_status = 'none' WHERE id = {SIGNAL_ID};")
    print("=" * 60)

if __name__ == '__main__':
    run_test()
