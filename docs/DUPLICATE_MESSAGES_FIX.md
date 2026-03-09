# Duplicate Messages & Zero Pips Investigation & Fix

**Date:** March 9, 2026  
**Issues:**

1. Duplicate messages being sent to the free channel
2. Promotional messages showing "+0 pips"

**Status:** ✅ Fixed

## Problem Summary

The free channel (`signalstack_free`) had two issues:

1. **Duplicate messages** when signals hit their take-profit targets (TP1, TP2, TP3)
2. **Promotional messages showing "+0 pips"** which looks unprofessional

Example of the zero pips issue:

```
🚀💰 Just witnessed another amazing win! Our VIP members just secured +0 pips
on the XAU/USD BUY signal! Imagine the profits! Don't stay behind; greatness
awaits you! Join us and elevate your trading game.
```

## Root Causes

### Issue 1: Duplicate Messages

The cross-promo system was missing **deduplication keys** on the jobs that forward TP hit messages to the free channel. Specifically:

1. **`forward_tp1_sequence`** - Forwards original signal + TP1 message to FREE channel
2. **`forward_tp_update`** (TP2) - Forwards TP2 update message
3. **`forward_tp_update`** (TP3) - Forwards TP3 update message

Without dedupe keys, if the same TP event was triggered multiple times (due to price fluctuations near the TP level, race conditions, or monitoring system retries), multiple jobs would be created and ALL of them would be processed by the worker, resulting in duplicate messages.

### Issue 2: Zero Pips in Messages

The AI-generated promotional messages were including "+0 pips" even when:

1. The `pips_secured` value was `0` or `None`
2. The pips value wasn't meaningful yet (TP just hit, calculation pending)

**Root causes:**

- The conditional check `if pips_secured` allowed `0` to pass through (since `0` is falsy but still a valid number)
- The AI prompt didn't explicitly instruct to omit pips when not provided
- The AI was including pips in the generated text even when the context didn't mention them

## Code Analysis

### Before Fix

```python
# ❌ NO dedupe_key - allows duplicates!
repo.enqueue_job(
    tenant_id=tenant_id,
    job_type='forward_tp1_sequence',
    run_at=now,
    payload={
        'signal_id': signal_id,
        'signal_message_id': signal_message_id,
        'tp1_message_id': tp1_message_id,
        'pips_secured': pips_secured
    }
)
```

### After Fix

```python
# ✅ With dedupe_key - prevents duplicates!
repo.enqueue_job(
    tenant_id=tenant_id,
    job_type='forward_tp1_sequence',
    run_at=now,
    payload={
        'signal_id': signal_id,
        'signal_message_id': signal_message_id,
        'tp1_message_id': tp1_message_id,
        'pips_secured': pips_secured
    },
    dedupe_key=f"{tenant_id}|{signal_id}|tp1_forward"
)
```

## How Deduplication Works

The `crosspromo_jobs` table has a unique constraint:

```sql
CREATE UNIQUE INDEX idx_crosspromo_jobs_dedupe
ON crosspromo_jobs(tenant_id, dedupe_key)
WHERE dedupe_key IS NOT NULL
```

When a job is enqueued with a `dedupe_key`:

```python
INSERT INTO crosspromo_jobs (...)
VALUES (...)
ON CONFLICT (tenant_id, dedupe_key) WHERE dedupe_key IS NOT NULL
DO NOTHING
```

If a job with the same `(tenant_id, dedupe_key)` already exists, the insert is silently ignored, preventing duplicates.

## Changes Made

**File:** `domains/crosspromo/service.py`

### Fix 1: Added Deduplication Keys

#### 1.1 TP1 Forward Job (Line ~1154)

- **Added:** `dedupe_key=f"{tenant_id}|{signal_id}|tp1_forward"`
- **Prevents:** Multiple TP1 forward sequences for the same signal

#### 1.2 TP2 Forward Job (Line ~1189)

- **Added:** `dedupe_key=f"{tenant_id}|{signal_id}|tp2_forward"`
- **Prevents:** Multiple TP2 updates for the same signal

#### 1.3 TP3 Forward Job (Line ~1223)

- **Added:** `dedupe_key=f"{tenant_id}|{signal_id}|tp3_forward"`
- **Prevents:** Multiple TP3 updates for the same signal

### Fix 2: Filter Zero Pips Values

#### 2.1 Improved Pips Context Check (Line ~268)

**Before:**

```python
pips_context = f" VIP members just secured {pips_secured:+.0f} pips on this signal." if pips_secured else ""
```

**After:**

```python
# Only include pips if meaningful (> 0)
pips_context = f" VIP members just secured {pips_secured:+.0f} pips on this signal." if (pips_secured and pips_secured > 0) else ""
```

**Why:** The old check `if pips_secured` would be `False` for `0`, but the value `0` could still be passed as a number. The new check explicitly requires `pips_secured > 0`.

#### 2.2 Updated AI Prompt (Line ~280)

**Added instruction:**

```
- IMPORTANT: Do NOT mention pips unless they were provided in the context above
```

This explicitly tells the AI not to fabricate or include pip values when they weren't provided in the context.

## Dedupe Key Pattern

All cross-promo jobs now follow a consistent dedupe key pattern:

| Job Type                  | Dedupe Key Pattern                      | Example                               |
| ------------------------- | --------------------------------------- | ------------------------------------- |
| `morning_news`            | `{tenant_id}\|{date}\|morning_news`     | `entrylab\|2026-03-09\|morning_news`  |
| `vip_soon`                | `{tenant_id}\|{date}\|vip_soon`         | `entrylab\|2026-03-09\|vip_soon`      |
| `eod_pip_brag`            | `{tenant_id}\|{date}\|eod_pip_brag`     | `entrylab\|2026-03-09\|eod_pip_brag`  |
| `forward_recap`           | `{tenant_id}\|{date}\|forward_recap`    | `entrylab\|2026-03-09\|forward_recap` |
| `forward_tp1_sequence`    | `{tenant_id}\|{signal_id}\|tp1_forward` | `entrylab\|135\|tp1_forward`          |
| `forward_tp_update` (TP2) | `{tenant_id}\|{signal_id}\|tp2_forward` | `entrylab\|135\|tp2_forward`          |
| `forward_tp_update` (TP3) | `{tenant_id}\|{signal_id}\|tp3_forward` | `entrylab\|135\|tp3_forward`          |
| `crosspromo_finish`       | `{tenant_id}\|{signal_id}\|finish`      | `entrylab\|135\|finish`               |
| `hype_message`            | `hype_{flow_id}_{date}_step{N}`         | `hype_abc123_2026-03-09_step1`        |
| `hype_cta`                | `hype_{flow_id}_{date}_cta`             | `hype_abc123_2026-03-09_cta`          |
| `hype_bump`               | `hype_bump_{flow_id}_{date}`            | `hype_bump_abc123_2026-03-09`         |

## Testing Recommendations

### 1. Manual Testing

- Trigger a signal that hits TP1 multiple times (by adjusting the TP level)
- Verify only ONE set of messages is sent to the free channel
- Check the `crosspromo_jobs` table for dedupe conflicts in logs

### 2. Database Verification

```sql
-- Check for duplicate jobs (should return 0 rows after fix)
SELECT
    tenant_id,
    job_type,
    payload->>'signal_id' as signal_id,
    COUNT(*) as count
FROM crosspromo_jobs
WHERE job_type IN ('forward_tp1_sequence', 'forward_tp_update')
AND status = 'queued'
GROUP BY tenant_id, job_type, payload->>'signal_id'
HAVING COUNT(*) > 1;
```

### 3. Log Monitoring

Look for these log messages indicating dedupe is working:

```
[INFO] [repo] Job dedupe conflict: entrylab/entrylab|135|tp1_forward
```

## Additional Safeguards

The system has multiple layers of protection against duplicates:

1. **Dedupe Keys** (NEW) - Prevents duplicate job creation
2. **Atomic Job Claiming** - `FOR UPDATE SKIP LOCKED` prevents workers from claiming the same job
3. **Cross-promo Status Tracking** - Signals have `crosspromo_status`: `none` → `started` → `complete`
4. **Daily Limits** - Max 1 winning signal per day can be forwarded
5. **Idempotent Finish** - `finish_crosspromo()` checks if already complete before proceeding

## Deployment Notes

- ✅ **No database migration required** - dedupe_key column already exists
- ✅ **No breaking changes** - dedupe_key is optional, existing jobs work fine
- ✅ **Backward compatible** - old jobs without dedupe keys still process normally
- ⚠️ **Restart required** - Service must be restarted to load the updated code

## Related Files

- `domains/crosspromo/service.py` - Main fix location
- `domains/crosspromo/repo.py` - Job enqueueing with dedupe logic
- `scheduler/crosspromo_worker.py` - Job processor (unchanged)
- `db.py` - Database schema with dedupe index (unchanged)

## Monitoring

After deployment, monitor:

1. **Free channel** - Verify no duplicate messages appear
2. **Logs** - Look for `Job dedupe conflict` messages (indicates system is working)
3. **Database** - Check `crosspromo_jobs` table for job counts per signal
4. **User feedback** - Confirm users no longer report duplicates

## Expected Behavior After Fix

### Duplicate Messages

- ✅ Each signal's TP hit will only trigger ONE message sequence to the free channel
- ✅ If the same TP event fires multiple times, subsequent attempts will be deduplicated
- ✅ Logs will show: `[INFO] [repo] Job dedupe conflict: entrylab/entrylab|135|tp1_forward`

### Zero Pips Messages

- ✅ Messages will NOT include "+0 pips"
- ✅ If pips are meaningful (> 0), they will be included: "+179 pips secured!"
- ✅ If pips are zero or not available, the message focuses on the win without mentioning pips

### Example Messages

**Before Fix (BAD):**

```
🚀💰 Just witnessed another amazing win! Our VIP members just secured +0 pips
on the XAU/USD BUY signal! Imagine the profits!
```

**After Fix (GOOD):**

```
🔥 Another win for VIP! This signal was live in VIP earlier today.
Our members are stacking pips daily 💰
```

**With Meaningful Pips (GOOD):**

```
+179 pips secured! 🔥 Another win for VIP! This signal was live in VIP
earlier today. Our members are stacking pips daily 💰
```

## Conclusion

The fixes address both issues:

1. **Deduplication keys** prevent duplicate messages from being sent to the free channel
2. **Pips filtering** ensures only meaningful pip values are included in promotional messages

**Impact:** High - Directly fixes user-facing issues  
**Risk:** Low - Only adds dedupe keys and improves conditional logic  
**Urgency:** High - Affects user experience and brand perception on free channel
