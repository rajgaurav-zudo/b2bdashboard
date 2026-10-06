"""Downloadable reports built from the archived exports.

A report reads the files themselves rather than any dashboard's tables: it
needs columns no dashboard keeps (the application's own SRM / AMT, the
institution, the introducer's CRM id), and it should not change when a
dashboard's schema does.
"""
