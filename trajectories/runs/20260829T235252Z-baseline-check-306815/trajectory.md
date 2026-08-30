# Trajectory — baseline-check (baseline)

- Run: `20260829T235252Z-baseline-check-306815`
- Commit: `fbcae5e95c3cce5f428ad195339ffa0615ff4e45`
- Events: 5
- Span: 2026-08-29T23:52:52.845248+00:00 to 2026-08-29T23:52:58.767475+00:00


## Case (no case)

### **person**
<sub>2026-08-29T23:52:52.845248+00:00</sub>

*input*

```
{
  "system": "baseline",
  "stage": "baseline-check",
  "model": "claude-haiku-4-5-20251001",
  "backend": "cli",
  "n_cases": 1,
  "note": ""
}
```


## Case R01

### **start** · `baseline`
<sub>2026-08-29T23:52:52.845863+00:00</sub>

### **model in** · `baseline`
<sub>2026-08-29T23:52:52.845942+00:00</sub>

*input*

```
{
  "system_digest": "feaa1f115741",
  "user": "## THE CASE\n\nCASE R01\nPassenger: A. Mendes  (booking QX7T4L)\n\nWHAT THE PASSENGER SAYS\nMy flight from Lisbon to Vienna was cancelled. They emailed me on the 3rd, the flight was on the 6th. I had to buy a train ticket in the end. I want to know what I am owed.\n\nDOCUMENTS ON FILE\n--- D1 [booking_confirmation] ---\nBOOKING QX7T4L — Passenger: A. MENDES (adult)\nCarrier: Meridian Air (MR)\nMR414  LIS 06 Mar 2026 07:40  ->  VIE 06 Mar 2026 11:55\nSingle booking reference. Great-circle distance LIS-VIE: 2,090 km.\nStatus: CONFIRMED. Fare paid: 214.00 units.\n\n--- D2 [carrier_notification] ---\nFrom: notifications@meridian-air.example\nTo: a.mendes@example.org\nSent: 03 Mar 2026 09:12 UTC\nSubject: Cancellation of MR414 on 06 Mar 2026\n\nWe regret to inform you that MR414 (LIS-VIE, 06 Mar) has been cancelled. Your booking has been refunded in full. No alternative flight was offered on this routing.\n\n--- D3 [operational_record] ---\nMERIDIAN AIR OPS LOG — MR414 / 06MAR2026\nStatus: CANCELLED\nCause code: CRW-DUTY\nCause text: Operating crew unavailable; standby crew exceeded permitted duty hours. No reserve crew at LIS base.\nNo weather restriction in force at LIS or VIE.\n\nCARRIER RESPONSE\nNone on file.\n"
}
```

### **ERROR** · FAILED
<sub>2026-08-29T23:52:58.762206+00:00</sub>

*output*

```
LLMError('cli backend failed after 3 attempts: claude -p exited 1: ')
```


## Case (no case)

### **final**
<sub>2026-08-29T23:52:58.767475+00:00</sub>

*output*

```
{
  "metrics": {
    "n_cases": 1,
    "case_resolution_accuracy": 0.0,
    "action_accuracy": 0.0,
    "compensation_accuracy": 0.0,
    "eligibility_accuracy": 0.0,
    "cause_accuracy": 0.0,
    "evidence_sufficiency_accuracy": 0.0,
    "duty_of_care_accuracy": 0.0,
    "downgrade_accuracy": 0.0,
    "unsupported_claims": 0,
    "unsupported_rejection_challenges": 0,
    "false_escalations": 0,
    "missed_escalations": 0,
    "failed_cases": [
      "R01"
    ]
  },
  "totals": {
    "model_calls": 0,
    "task_input_tokens": 0,
    "output_tokens": 0,
    "cache_creation_tokens": 0,
    "cache_read_tokens": 0,
    "harness_overhead_tokens": 0,
    "cost_usd": 0.0,
    "wall_clock_s": 5.9,
    "mean_calls_per_case": 0.0
  }
}
```
