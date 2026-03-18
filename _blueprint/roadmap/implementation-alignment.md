# Implementation Alignment Report

*Generated: 2026-03-16*
*Last updated: 2026-03-17 (user notes)*
*Purpose: Identify inconsistencies between blueprint docs and actual implementation state.*

---

## ToDo Items

1. some routes still have helpers etc.
- use our new <pattern> consistently


<pattern>
allow gaets are at the router level

individual routes with permission or additional requirements use require gates

routes that need information the allow or require gate returns should:
- add an information only Dependency chain to dependencies
- call it on the route specifically
- this makes the Depends information tree easy to follow (even if it duplicates some code form allow gates)

route moduyles should ideally not make helpers if possible
- use existing dependencies etc.
</pattern>