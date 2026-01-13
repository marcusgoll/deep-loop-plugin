# Cancel Ralph Mode

Stop ralph mode immediately by marking all PRD tasks as complete or deleting the PRD.

## When to Use

- User wants to stop autonomous processing
- Tasks are stuck or going in wrong direction
- Need to start fresh with different approach

## Actions

1. **Check for PRD file** at `.deep/prd.json`

2. **Option A: Mark all complete** (preserves history)
   ```json
   // For each task, set:
   {
     "passes": true,
     "completedAt": "[timestamp]",
     "skippedReason": "Cancelled by user"
   }
   ```

3. **Option B: Delete PRD** (clean slate)
   ```bash
   rm .deep/prd.json
   ```

4. **Clean up state files**
   - Update `.deep/state.json` to `{ "complete": true, "phase": "CANCELLED" }`

5. **Confirm cancellation**
   ```
   Ralph mode cancelled. [N] tasks were pending.
   PRD file: [preserved/deleted]
   ```

## Example

User: `/cancel-ralph`

Response:
```
Cancelling ralph mode...

Found 5 tasks in PRD:
- 2 completed
- 3 pending (now marked as skipped)

PRD preserved at .deep/prd.json with skip reasons.
State reset. You can now exit cleanly.
```
