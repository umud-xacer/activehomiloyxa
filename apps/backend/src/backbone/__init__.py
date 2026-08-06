"""backbone -- shared backend infrastructure machinery (Task P-03).

Not a bounded context and not DDD value-object content (that is `shared_kernel`, DDD Sec 5.14,
closed as of Task P-02) -- this is the persistence/outbox/migration/error-handling/DI/logging
plumbing every one of the 13 modules' `infrastructure/` layers builds on, so it is not
hand-rolled thirteen times. See `backbone/README.md` for the placement rationale (neither
`shared_kernel` nor `packages/shared` fit this per Playbook Sec 2's shared-code rule) and
`tools/importlinter.cfg` for the enforced boundary: every module MAY import `backbone`;
`backbone` imports only `shared_kernel`.

Named `backbone`, not `platform` (Python's stdlib module of that name) -- a top-level package
named `platform` would shadow it for every other import in the interpreter.
"""
