"""SNC CLI – Studio Northern Construction equipment tracking."""

import typer

from snc_cli.commands import business_unit, equipment, job, location, telemetry

app = typer.Typer(
    name="snc",
    help="Studio Northern Construction – equipment tracking CLI.",
    no_args_is_help=True,
)

app.add_typer(business_unit.app)
app.add_typer(equipment.app)
app.add_typer(job.app)
app.add_typer(location.app)
app.add_typer(telemetry.app)

if __name__ == "__main__":
    app()
