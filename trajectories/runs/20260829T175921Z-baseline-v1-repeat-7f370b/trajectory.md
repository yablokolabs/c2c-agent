# Trajectory — 20260829T175921Z-baseline-v1-repeat-7f370b

- Run: `20260829T175921Z-baseline-v1-repeat-7f370b`
- Commit: `b25292d98c4852bda817b37c0a49766e927f3bfb`
- Events: 15
- Span: 2026-08-29T17:59:21.959424+00:00 to 2026-08-29T18:01:06.540747+00:00


## Case (no case)

### **person**
<sub>2026-08-29T17:59:21.959424+00:00</sub>

*input*

```
{
  "system": "baseline",
  "stage": "baseline-v1-repeat",
  "model": "claude-haiku-4-5-20251001",
  "backend": "cli",
  "n_cases": 28,
  "note": "Identical to baseline-v1, re-run to measure run-to-run variance. No code, prompt or benchmark change."
}
```


## Case R01

### **start** · `baseline`
<sub>2026-08-29T17:59:21.960400+00:00</sub>

### **model in** · `baseline`
<sub>2026-08-29T17:59:21.960490+00:00</sub>

*input*

```
{
  "system_digest": "feaa1f115741",
  "user": "## THE CASE\n\nCASE R01\nPassenger: A. Mendes  (booking QX7T4L)\n\nWHAT THE PASSENGER SAYS\nMy flight from Lisbon to Vienna was cancelled. They emailed me on the 3rd, the flight was on the 6th. I had to buy a train ticket in the end. I want to know what I am owed.\n\nDOCUMENTS ON FILE\n--- D1 [booking_confirmation] ---\nBOOKING QX7T4L — Passenger: A. MENDES (adult)\nCarrier: Meridian Air (MR)\nMR414  LIS 06 Mar 2026 07:40  ->  VIE 06 Mar 2026 11:55\nSingle booking reference. Great-circle distance LIS-VIE: 2,090 km.\nStatus: CONFIRMED. Fare paid: 214.00 units.\n\n--- D2 [carrier_notification] ---\nFrom: notifications@meridian-air.example\nTo: a.mendes@example.org\nSent: 03 Mar 2026 09:12 UTC\nSubject: Cancellation of MR414 on 06 Mar 2026\n\nWe regret to inform you that MR414 (LIS-VIE, 06 Mar) has been cancelled. Your booking has been refunded in full. No alternative flight was offered on this routing.\n\n--- D3 [operational_record] ---\nMERIDIAN AIR OPS LOG — MR414 / 06MAR2026\nStatus: CANCELLED\nCause code: CRW-DUTY\nCause text: Operating crew unavailable; standby crew exceeded permitted duty hours. No reserve crew at LIS base.\nNo weather restriction in force at LIS or VIE.\n\nCARRIER RESPONSE\nNone on file.\n"
}
```

### **model out** · `baseline` · 63971 ms
<sub>2026-08-29T18:00:25.932531+00:00</sub>

*output*

````
```json
{
  "in_scope": true,
  "qualifies": true,
  "cause_class": "carrier_controlled",
  "eligible": true,
  "compensation_units": 420,
  "duty_of_care_units": 0,
  "downgrade_reimbursement_units": 0,
  "evidence_sufficient": true,
  "missing_evidence": [],
  "next_action": "submit_claim",
  "policy_citations": ["S1.2", "S2.1(a)", "S3.2(b)", "S4.2", "S5.1"],
  "rationale": "Cancellation due to crew duty-hour shortage (carrier-controlled, S3.2b) with 3-day notice qualifies for Band B compensation: 420 units at 100% per S4.2, as no re-routing was offered. All evidence requirements met; passenger should submit formal claim to Meridian Air."
}
```
````

### **final** · `baseline`
<sub>2026-08-29T18:00:25.932886+00:00</sub>

*output*

```
{
  "in_scope": true,
  "qualifies": true,
  "cause_class": "carrier_controlled",
  "eligible": true,
  "compensation_units": 420,
  "duty_of_care_units": 0,
  "downgrade_reimbursement_units": 0,
  "evidence_sufficient": true,
  "missing_evidence": [],
  "next_action": "submit_claim",
  "policy_citations": [
    "S1.2",
    "S2.1(a)",
    "S3.2(b)",
    "S4.2",
    "S5.1"
  ],
  "rationale": "Cancellation due to crew duty-hour shortage (carrier-controlled, S3.2b) with 3-day notice qualifies for Band B compensation: 420 units at 100% per S4.2, as no re-routing was offered. All evidence requirements met; passenger should submit formal claim to Meridian Air."
}
```


## Case R03

### **start** · `baseline`
<sub>2026-08-29T18:00:25.934110+00:00</sub>


## Case R02

### **start** · `baseline`
<sub>2026-08-29T18:00:25.933641+00:00</sub>

### **model in** · `baseline`
<sub>2026-08-29T18:00:25.934466+00:00</sub>

*input*

```
{
  "system_digest": "feaa1f115741",
  "user": "## THE CASE\n\nCASE R02\nPassenger: H. Okonkwo  (booking BB2M91)\n\nWHAT THE PASSENGER SAYS\nSnowstorm, flight cancelled, I was stuck overnight and paid for a hotel and dinner myself. The airline says weather means they owe me nothing at all. Is that right?\n\nDOCUMENTS ON FILE\n--- D1 [booking_confirmation] ---\nBOOKING BB2M91 — Passenger: H. OKONKWO (adult)\nCarrier: Northwind (NW)\nNW220  OSL 14 Jan 2026 18:30  ->  MAN 14 Jan 2026 20:05\nSingle booking reference. Great-circle distance OSL-MAN: 1,045 km.\nStatus: CONFIRMED. Fare paid: 96.00 units.\n\n--- D2 [carrier_notification] ---\nFrom: ops@northwind.example\nSent: 14 Jan 2026 16:02 UTC\nSubject: NW220 cancelled\n\nNW220 OSL-MAN on 14 Jan is cancelled. You have been rebooked on NW222 departing 15 Jan 2026 09:15.\n\n--- D3 [operational_record] ---\nNORTHWIND OPS LOG — NW220 / 14JAN2026\nStatus: CANCELLED\nCause code: WX-MIN\nCause text: OSL below operating minima. RVR 275m, freezing snow, airport departure rate reduced to zero 15:40-22:00Z. Airport authority declared ground stop.\n\n--- D4 [receipts] ---\nITEMISED RECEIPTS SUBMITTED BY PASSENGER\n1. Clarion Hotel Oslo Airport, 1 night 14-15 Jan, room only .... 190.00 units (receipt no. 44812)\n2. Airport restaurant, evening meal 14 Jan ................... 34.00 units (receipt no. 9911)\n3. Breakfast 15 Jan .......................................... 16.00 units (receipt no. 9974)\nTOTAL 240.00 units\n\n--- D5 [boarding_pass] ---\nCHECK-IN CONFIRMATION NW220 14JAN2026 — OKONKWO/H — accepted for travel 15:55Z, seat 12C. Flight subsequently cancelled.\n\nCARRIER RESPONSE (rejection, received 2026-01-20)\nYour claim is declined. NW220 was cancelled due to extraordinary circumstances (severe weather) outside our control. No compensation is payable and we are unable to reimburse your expenses.\n"
}
```


## Case R04

### **start** · `baseline`
<sub>2026-08-29T18:00:25.934417+00:00</sub>

### **model in** · `baseline`
<sub>2026-08-29T18:00:25.934649+00:00</sub>

*input*

```
{
  "system_digest": "feaa1f115741",
  "user": "## THE CASE\n\nCASE R04\nPassenger: D. Ferreira  (booking MT5590)\n\nWHAT THE PASSENGER SAYS\nMy first flight was late so I missed my connection in Doha and got in to Sydney the next morning. I was told the delay only counts on the leg that was late.\n\nDOCUMENTS ON FILE\n--- D1 [booking_confirmation] ---\nBOOKING MT5590 — Passenger: D. FERREIRA (adult)\nCarrier: Meridian Transcontinental (MT)\nMT119  MAD 11 Nov 2026 14:20  ->  DOH 11 Nov 2026 23:10\nMT402  DOH 12 Nov 2026 01:55  ->  SYD 12 Nov 2026 21:30\nBOTH SEGMENTS ON THIS SINGLE BOOKING REFERENCE.\nGreat-circle distance MAD-SYD (origin to final destination): 17,680 km.\nStatus: CONFIRMED.\n\n--- D2 [boarding_pass] ---\nBOARDING PASS MT119 11NOV2026 — FERREIRA/D — seat 21A — boarded 14:05Z\n\n--- D3 [operational_record] ---\nMT OPS LOG — MT119 / 11NOV2026\nStatus: DELAYED 02:35 departure\nCause code: ROT-INB\nCause text: Late inbound aircraft. Inbound MT118 delayed by MT ground handling shortfall at MAD. No weather or ATC restriction.\nConsequence: 14 passengers misconnected at DOH onto MT404.\n\n--- D4 [arrival_record] ---\nSYD ARRIVALS\nOriginally ticketed arrival (MT402): 12 Nov 2026 21:30 local\nPassenger FERREIRA/D rebooked onto MT404, actual on-blocks 13 Nov 2026 01:40 local\nDelay at final destination: 4h 10m\n\nCARRIER RESPONSE\nNone on file.\n"
}
```


## Case R03

### **model in** · `baseline`
<sub>2026-08-29T18:00:25.934769+00:00</sub>

*input*

```
{
  "system_digest": "feaa1f115741",
  "user": "## THE CASE\n\nCASE R03\nPassenger: S. Ivanova  (booking LP08KD)\n\nWHAT THE PASSENGER SAYS\nSix hours late into Nairobi because something broke on the plane. The airline told me sudden technical faults are outside their control.\n\nDOCUMENTS ON FILE\n--- D1 [booking_confirmation] ---\nBOOKING LP08KD — Passenger: S. IVANOVA (adult)\nCarrier: Lyra Pacific (LP)\nLP771  AMS 02 Sep 2026 21:15  ->  NBO 03 Sep 2026 07:40\nSingle booking reference. Great-circle distance AMS-NBO: 6,635 km.\nStatus: CONFIRMED.\n\n--- D2 [boarding_pass] ---\nBOARDING PASS LP771 02SEP2026 — IVANOVA/S — seat 34K — boarded 21:02Z\n\n--- D3 [arrival_record] ---\nNBO ARRIVALS — LP771 03SEP2026\nScheduled on-blocks 07:40 local\nActual on-blocks 13:46 local\nDelay at final destination: 6h 06m\n\n--- D4 [operational_record] ---\nLYRA PACIFIC OPS LOG — LP771 / 02SEP2026\nStatus: DELAYED 06:06\nCause code: TECH-UNSCH\nCause text: Unscheduled maintenance. Bleed air valve fault detected by LP line maintenance during pre-departure checks at AMS. Part sourced from LP stores, replaced, aircraft returned to service.\nNo manufacturer or regulator directive associated with this defect.\n\nCARRIER RESPONSE\nNone on file.\n"
}
```


## Case R02

### **model out** · `baseline` · 40605 ms
<sub>2026-08-29T18:01:06.539917+00:00</sub>

*output*

````
```json
{
  "in_scope": true,
  "qualifies": true,
  "cause_class": "extraordinary",
  "eligible": false,
  "compensation_units": 0,
  "duty_of_care_units": 240,
  "downgrade_reimbursement_units": 0,
  "evidence_sufficient": true,
  "missing_evidence": [],
  "next_action": "challenge_rejection",
  "policy_citations": ["S2.1(a)", "S3.1", "S3.3(a)", "S6.1", "S6.2", "S9.1(e)"],
  "rationale": "Flight cancelled due to extraordinary weather circumstances (S3.3(a)); compensation not payable under S3.1. Duty of care is owed regardless of cause (S6.1), and passenger submitted itemised receipts totalling 240 units (hotel 190 + meals 50) within the 300-unit cap. Carrier's rejection is validly challengeable under S9.1(e) for failing to separately address duty-of-care reimbursement."
}
```
````

### **final** · `baseline`
<sub>2026-08-29T18:01:06.540302+00:00</sub>

*output*

```
{
  "in_scope": true,
  "qualifies": true,
  "cause_class": "extraordinary",
  "eligible": false,
  "compensation_units": 0,
  "duty_of_care_units": 240,
  "downgrade_reimbursement_units": 0,
  "evidence_sufficient": true,
  "missing_evidence": [],
  "next_action": "challenge_rejection",
  "policy_citations": [
    "S2.1(a)",
    "S3.1",
    "S3.3(a)",
    "S6.1",
    "S6.2",
    "S9.1(e)"
  ],
  "rationale": "Flight cancelled due to extraordinary weather circumstances (S3.3(a)); compensation not payable under S3.1. Duty of care is owed regardless of cause (S6.1), and passenger submitted itemised receipts totalling 240 units (hotel 190 + meals 50) within the 300-unit cap. Carrier's rejection is validly challengeable under S9.1(e) for failing to separately address duty-of-care reimbursement."
}
```


## Case R05

### **start** · `baseline`
<sub>2026-08-29T18:01:06.540613+00:00</sub>

### **model in** · `baseline`
<sub>2026-08-29T18:01:06.540747+00:00</sub>

*input*

```
{
  "system_digest": "feaa1f115741",
  "user": "## THE CASE\n\nCASE R05\nPassenger: K. Rasmussen  (booking JJ1002 / TT4419)\n\nWHAT THE PASSENGER SAYS\nI booked the two legs separately to save money. The first flight was an hour late and I missed the second one, then had to buy a whole new ticket. Surely they still owe me for getting me there fifteen hours late.\n\nDOCUMENTS ON FILE\n--- D1 [booking_confirmation] ---\nBOOKING JJ1002 — Passenger: K. RASMUSSEN (adult)\nCarrier: Jetline (JJ)\nJJ88  CPH 04 Apr 2026 06:00  ->  FRA 04 Apr 2026 07:35\nGreat-circle distance CPH-FRA: 670 km.\nStatus: CONFIRMED.\n\n--- D2 [booking_confirmation] ---\nBOOKING TT4419 — Passenger: K. RASMUSSEN (adult)\nCarrier: Tarn Air (TT) — SEPARATE BOOKING, PURCHASED INDEPENDENTLY\nTT610  FRA 04 Apr 2026 09:10  ->  IST 04 Apr 2026 13:05\nStatus: CONFIRMED. Not through-ticketed with JJ1002. No interline agreement recorded.\n\n--- D3 [arrival_record] ---\nFRA ARRIVALS — JJ88 04APR2026\nScheduled on-blocks 07:35\nActual on-blocks 08:30\nDelay: 0h 55m\n\n--- D4 [operational_record] ---\nJETLINE OPS LOG — JJ88 / 04APR2026\nStatus: DELAYED 00:55\nCause code: CRW-LATE\nCause text: Crew positioning delay, JJ-controlled.\n\n--- D5 [passenger_statement] ---\nI reached IST at 04:20 on 5 April, about fifteen hours after I was supposed to, because TT would not rebook me and I had to buy a new ticket for the next morning.\n\nCARRIER RESPONSE\nNone on file.\n"
}
```
