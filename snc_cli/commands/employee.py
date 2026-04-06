"""employee commands."""

from __future__ import annotations

from typing import Optional

import typer

from snc_cli.client import get_client
from snc_cli.output import abort, output

app = typer.Typer(name="employee", help="Manage employees.")


@app.command("list")
def list_employees(
    business_unit: Optional[str] = typer.Option(None, "--business-unit", help="Filter by business unit UUID"),
    role: Optional[str] = typer.Option(None, "--role", help="Filter by role (Driver, Crew Lead, Crew Member)"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """List employees, optionally filtered."""
    q = get_client().table("Employee").select("*")
    if business_unit:
        q = q.eq("businessUnitId", business_unit)
    if role:
        q = q.eq("role", role)
    resp = q.execute()
    output(resp.data, human, title="Employees")


@app.command("get")
def get_employee(
    id: str = typer.Option(..., "--id", help="Employee UUID"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Get a single employee record by ID."""
    resp = get_client().table("Employee").select("*").eq("id", id).execute()
    if not resp.data:
        abort(f"Employee ID {id} not found. Ensure the ID is a valid UUID.")
    output(resp.data[0], human, title="Employee")


@app.command("create")
def create_employee(
    business_unit: str = typer.Option(..., "--business-unit", help="Business unit UUID"),
    first_name: str = typer.Option(..., "--first-name", help="Employee first name"),
    last_name: str = typer.Option(..., "--last-name", help="Employee last name"),
    employee_code: str = typer.Option(..., "--employee-code", help="Unique employee code/badge"),
    role: str = typer.Option("Crew Member", "--role", help="Role (Driver, Crew Lead, Crew Member)"),
    human: bool = typer.Option(False, "--human", help="Human-readable output"),
) -> None:
    """Create a new employee record."""
    payload: dict = {
        "businessUnitId": business_unit,
        "firstName": first_name,
        "lastName": last_name,
        "employeeCode": employee_code,
        "role": role,
    }
    resp = get_client().table("Employee").upsert(payload, on_conflict="businessUnitId,employeeCode").execute()
    if not resp.data:
        abort("Failed to create employee.")
    output(resp.data[0], human, title="Employee Created")
