# Limitations

What this project does not establish, stated plainly.

## The policy is invented, and that cuts both ways

`benchmark/POLICY.md` is synthetic, with thresholds chosen to differ from every
real scheme. That is deliberate and it is the right call for measuring
document-grounded reasoning — a model cannot score well by recalling a real
regulation.

But it means **nothing here transfers directly to a real compensation scheme.**
A real one has case law, regulator guidance, carrier-specific terms, and
ambiguity that a 1,800-word document does not. The agent is good at applying
*this* policy to *these* documents. That is a weaker claim than "good at airline
compensation", and it is the only claim the evidence supports.

## Ground truth is one author's reading

Each case's ground truth was written by one person, from the policy, with the
derivation recorded. A test checks every cited clause exists. Nothing checks
whether a second competent reader would agree with the reading.

For the cases that turn on a fine distinction — R11 versus R27 on when a
contradiction is resolved by rule, or R26 on the scope of the delay taper — a
second annotator might reasonably differ. **There is no inter-annotator
agreement measurement, so the ceiling on the metric is unknown.** Some of what
is scored as agent error may be ground-truth disagreement.

The honest fix is two independent annotators and a reported agreement rate. That
was not done.

## Twenty-eight cases is a small sample

One case is 3.6 points of the primary metric. Differences under about 0.07
between two runs are not distinguishable from sampling noise, and the model is
sampled rather than deterministic. Every comparison in this repository is a
single run per configuration, so **the reported deltas carry no confidence
interval.**

Repeated runs at several temperatures would fix this. Time and budget did not
allow it, and inventing an interval would be worse than saying so.

## The benchmark was extended after the first baseline run

The original 20 cases were near-saturated at 0.90. Eight harder cases were added
before the agent existed, targeting general difficulty properties rather than
observed baseline errors, and both systems are scored on the same 28. The
reasoning and the constraints are recorded in FAILURES.md F-003, and the
original 20-case result file is kept.

This is a real threat to validity even handled carefully. A reader should treat
the 28-case numbers as the fair comparison and the 20-case numbers as the record
of how the benchmark was found to be inadequate.

## The durability suite tests the workflow, not the agent

The six scenarios point the assess step at a stub returning a fixed verdict, so
model sampling does not add variance to a measurement about crash recovery. That
is the right isolation, but it means **the durability result says nothing about
whether the agent reasons well under failure** — only that the workflow does not
lose or duplicate work.

## The baseline scores nothing on durability, and that is not a win

The baseline is a single prompt. It has no lifecycle, so there is nothing for a
crash to interrupt. Reporting "agent 6/6, baseline 0/6" would be comparing a
system to the absence of one. The durability suite is reported as evidence that
Restate delivers the invariants it was added for, not as a margin over the
baseline.

## The simulated world is friendlier than the real one

The synthetic airline responds on demand, honours idempotency keys, and returns
structured records. Real carriers send PDFs and free text, contradict themselves
across channels, ignore correspondence, and have no idempotency semantics at
all. **The exactly-once guarantee here depends on the carrier deduplicating on a
key**, which a real one will not do.

Against a real carrier the invariant would have to be enforced differently —
probably by never retrying a submission without a human confirming it did not
land. That is a materially harder problem and it is not solved here.

## Timers are compressed, not tested at scale

`C2C_CLOCK_SCALE` shortens the 56-day and 28-day clocks so the demo and the
suite can run. The durable semantics are identical, and Restate's timers are
well-tested upstream, but **no case in this repository has actually waited eight
weeks.** The longest observed suspension is minutes.

## One model, one size

Everything was run on Haiku 4.5 for both systems, which keeps the comparison
fair and the cost tractable. Whether the agent's advantage grows, shrinks or
inverts on a larger model is unmeasured. The plausible result — that a stronger
model closes most of the gap the tools open — would matter a lot to anyone
deciding whether to build this, and it is not known.

## The cost figures come from the harness, not from a meter

`totals.cost_usd` is what the backend reported. On the CLI backend that includes
a fixed harness system prompt C2C did not author, reported separately as
`harness_overhead_tokens`. It is a good relative signal between runs on the same
backend and a poor absolute one. Where a backend reports nothing, the field is
`null` and the run says so.

## No human evaluation of output quality

The metric scores structured fields: action, amounts, entitlements. Nothing
scores whether the rationale is *useful* to a passenger, whether a claim
document reads as something a person would send, or whether the challenge letter
would persuade anyone. For a system whose output a real user has to act on, that
is a genuine gap.
