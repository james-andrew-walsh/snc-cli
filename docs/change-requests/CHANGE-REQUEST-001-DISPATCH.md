# Change Request 001: Implement Dispatch and Employee Tracking

## Background
The Core MVP for the Sierra Nevada Construction (SNC) Equipment Tracking project currently models `BusinessUnit`, `Equipment`, `Job`, and `Location`. 
We are expanding the model to incorporate concepts from **HCSS Dispatcher**. Specifically, we need to track `Employee` records (to model drivers and crew leads) and `DispatchEvent` records (to model scheduled equipment moves—the "Intent").

## The Task
Modify the `snc-cli` to implement the new Dispatch and Employee commands.

## Instructions for Claude Code
1. **Analyze the Delta:** Read the `v1` files in `core/archive/v1/` and compare them against the current files in `core/` (`CORE-CLI-PRD.md`, `CORE-ARCHITECTURE.md`, `data-model/CORE_SCHEMA_SPEC.md`, `data-model/CORE_OPERATIONS.md`).
2. **Understand the New Commands:** Notice the new commands added to the PRD:
   - `snc employee` (`list`, `get`, `create`)
   - `snc dispatch` (`list`, `schedule`, `cancel`)
   - `snc equipment update` now takes an optional `--status` flag.
3. **Database Migration:** 
   - We have already written the `002_add_dispatch_and_employees.sql` migration. 
   - Apply it to the Supabase backend using the Supabase CLI (`supabase db push` or equivalent, using the provided credentials/env vars).
4. **Update the CLI:**
   - Add the new commands to the Typer application in `/tmp/snc-cli/snc_cli/`.
   - Ensure the new tables are queried via the Supabase client.
   - Update the `equipment update` command to accept `--status`.
5. **Test:** Verify the new commands work locally against the updated database.

## Validation
Once complete, we should be able to:
- Create an employee with a role of "Driver".
- Schedule a dispatch event moving a piece of equipment to a job starting on a specific date, assigned to that driver.