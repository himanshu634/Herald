"""The API's internal routes for the triage pipeline: the contract, the client and the queries.

The worker never opens the database for triage. It loads the email, runs the history tools and
saves the result through these routes, so tenancy and "commit, then publish" live in the API.
"""
