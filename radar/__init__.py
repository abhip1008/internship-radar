"""Internship Radar — a self-hosted internship tracker for CS/SWE roles.

See the project spec / README for the full design. The package is organized as a
cron-driven batch pipeline: collectors -> normalize -> filter -> dedupe ->
score/deadlines/notes -> SQLite -> UI.
"""

__version__ = "0.1.0"
