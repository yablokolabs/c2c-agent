> **Superseded.** This was the first diagnosis of the run failures, written
> before the transport was tested. Its conclusion — a verifier resource leak
> causing a "progressive failure pattern" — is **wrong**. The real cause was a
> gateway serving a different model, plus an inherited `ANTHROPIC_BASE_URL`
> capturing the CLI subprocess. See `FAILURES.md` F-007.
>
> Kept because the diagnostic mistake is the more useful lesson: the story was
> built entirely from the *shape* of the failures, while the fact that the
> **baseline had moved** — with no change made to the baseline — was sitting in
> the data the whole time.

# Failure Pattern Analysis: C2C Agent System

## Executive Summary

Analysis of trajectory data reveals a progressive failure pattern in the C2C agent system where the verifier component accumulates resources over time, eventually causing CLI backend failures that prevent case processing.

## Failure Pattern Observed

### Temporal Progression
- **Cases R01-R10**: Process successfully through complete workflow (agent → verdict → verifier → success)
- **Cases R11-R12**: Fail during verifier's tool execution phase
- **Cases R13-R28**: Fail immediately at agent startup (no processing occurs)

### Failure Location
All failures occur during tool execution in what appears to be the verifier component:
- `calculate` tool calls (simple arithmetic: 750*0.5, 420*0)
- `read_document` tool calls (accessing case evidence)
- `policy_lookup` tool calls (checking policy rules)

### Error Signature
Consistent error message across all failures:
```
LLMError('cli backend failed after 3 attempts: claude -p exited 1: ')
```

## Root Cause Analysis

### Primary Hypothesis: Verifier Resource Leak
The verifier component appears to be accumulating state or resources that are not properly cleaned up between cases, leading to progressive resource exhaustion.

### Supporting Evidence
1. **Selective Failure Pattern**: Early cases succeed through full workflow including verification; later cases fail specifically during verification-phase operations
2. **Progressive Degradation**: System processes 10+ cases successfully before failures begin, indicating accumulation over time
3. **Verification-Specific Failures**: Failures cluster around verification tasks requiring additional work (evidence requests, calculations, contradiction resolution)
4. **System-Wide Impact**: Eventually affects agent startup, suggesting verifier leakage degrades overall system resources

### Contributing Factors
- **Tool Execution Residue**: Potential file descriptor or memory leaks from repeated tool use
- **Context Accumulation**: Verifier may retain conversation history or state between cases
- **Incomplete Cleanup**: Resources allocated during tool execution not properly released
- **Threshold Effect**: System tolerates initial resource usage but fails once critical thresholds exceeded

## Impact Assessment

### Metrics from Final Trajectory
- Case Resolution Accuracy: 0.25 (7/28 cases)
- Action Accuracy: 0.25
- Compensation Accuracy: 0.25
- Eligibility Accuracy: 0.25
- Cause Accuracy: 0.25
- Evidence Sufficiency Accuracy: 0.2143
- Duty of Care Accuracy: 0.25
- Downgrade Accuracy: 0.25
- Missed Escalations: 1 (likely case R15)
- Failed Cases: R04, R08, R10, R11, R12, R13-R28 (21/28 cases)

### Comparison to Baseline
Baseline-v1-repeat trajectory shows successful processing of all 28 cases, indicating the failure is specific to the agent/verifier workflow architecture rather than the underlying model or policy logic.

## Recommendations

### Immediate Actions
1. **Verify Resource Cleanup**: Audit verifier implementation for proper resource release after tool execution
2. **State Isolation**: Ensure verifier context/state is fully reset between cases
3. **Tool Execution Monitoring**: Add logging to track resource usage during tool calls

### System Improvements
1. **Resource Limits**: Implement per-case resource quotas with automatic cleanup
2. **Health Checks**: Add lightweight health checks between cases to detect degradation
3. **Recovery Mechanism**: Implement automatic restart of verifier component when degradation detected

### Verification Focus
- Examine verifier's handling of tool execution results
- Check for accumulation of conversation history or metadata
- Audit file descriptor usage during document operations
- Review memory management in policy lookup and calculation modules

## Conclusion

The failure pattern indicates a solvable resource management issue in the verifier component rather than a fundamental flaw in the agent architecture. Addressing the verifier's resource cleanup should restore the system's ability to process sustained workloads without degradation.