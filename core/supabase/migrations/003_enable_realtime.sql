-- Migration 003: Enable Supabase Realtime for all core tables
-- Required for postgres_changes subscriptions in the dashboard to receive events.
-- Without this, useRealtime hooks silently open but never fire.

ALTER PUBLICATION supabase_realtime ADD TABLE 
  "BusinessUnit", 
  "Equipment", 
  "Job", 
  "Location", 
  "Employee", 
  "DispatchEvent";
