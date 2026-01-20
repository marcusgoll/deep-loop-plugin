# Deep Loop Status

Display current deep loop session status.

## Actions

1. **Read state**:
   ```bash
   cat .deep/state.json 2>/dev/null
   ```

2. **Check for control files**:
   ```bash
   ls -la .deep/FORCE_EXIT .deep/FORCE_COMPLETE .deep/NEEDS_USER .deep/RALPH_HANDOFF 2>/dev/null
   ```

3. **Get file timestamps**:
   ```bash
   stat .deep/state.json 2>/dev/null | grep -i modify
   ```

4. **Display status**:

   **If state.json exists**:
   ```
   Deep Loop Status
   ================
   Phase: [phase from state.json]
   Active: [true/false]
   Complete: [true/false]
   Iteration: [current] / [max]
   Last Update: [timestamp from stat]

   Control Flags:
   - FORCE_EXIT: [yes/no]
   - FORCE_COMPLETE: [yes/no]
   - NEEDS_USER: [yes/no]
   - RALPH_HANDOFF: [yes/no]
   ```

   **If no state.json**:
   ```
   No active deep loop session.
   Start one with: /deep
   ```

## Notes

- Read-only operation
- Safe to run anytime
