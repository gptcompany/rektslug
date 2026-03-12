# Feature Specification: Counterflow Profile

**Feature ID**: 021
**Canonical Source**: `specs/021-counterflow-profile/spec.md`

This mirror exists for `.specify` compatibility.

The source of truth remains:
- `specs/021-counterflow-profile/spec.md`

The implementation goal is unchanged:
- define Counterflow as an explicit provider/profile
- document Lightweight Charts constraints
- align future integration with the shared visual harness
- treat Counterflow as a separate `lightweight` renderer adapter
- treat Counterflow as both data-source and visual-reference, with an asymmetrical role

Current repo decision:
- expose Counterflow as explicit provider-profile metadata
- keep its expected harness entry at `renderer_adapter=lightweight`
- do not add a local Lightweight smoke page until a later spec actually needs it
