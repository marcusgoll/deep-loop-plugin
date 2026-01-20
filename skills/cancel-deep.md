# Cancel Deep Loop

Immediately cancels an active deep loop session.

## Actions

1. **Update state file**:
   ```bash
   # Read current state
   cat .deep/state.json 2>/dev/null
   ```

2. **Set cancelled state**:
   Write to `.deep/state.json`:
   ```json
   {
     "active": false,
     "complete": true,
     "phase": "CANCELLED",
     "cancelled_at": "<current ISO timestamp>",
     "reason": "User requested cancellation"
   }
   ```

3. **Clean up control files**:
   ```bash
   rm -f .deep/FORCE_EXIT .deep/FORCE_COMPLETE .deep/NEEDS_USER .deep/RALPH_HANDOFF 2>/dev/null
   ```

4. **Report**:
   ```
   Deep loop cancelled.
   - State: .deep/state.json updated
   - Control files: cleaned
   ```

## Notes

- Does NOT delete `.deep/` directory (preserves history)
- Does NOT affect git state
- Safe to run even if no loop active
