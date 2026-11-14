# Directional Compatibility Analyzer

`compare_contracts(old_contract, new_contract)` and `prompt-contracts diff <old_dir> <new_dir>` analyze directional compatibility between two contract versions.

## Directional Semantics

Input schemas and output schemas have opposite compatibility directions:

- **Caller-Input Direction (`I_old <= I_new`)**: Every input accepted by `old_contract` must still be accepted by `new_contract`.
  - Adding an optional input property or widening an input bound/enum is **compatible**.
  - Adding a required input property, removing an input property, or tightening an input bound/enum is **breaking**.
- **Consumer-Output Direction (`O_new <= O_old`)**: Every output accepted by `new_contract` must also be accepted by `old_contract`.
  - Adding a required output property (when allowed by `additionalProperties`) or narrowing an output bound/enum is **compatible**.
  - Removing a required output property or widening an output bound/enum is **breaking**.

## Three-Valued Status & Behavioral Flag

- **`compatible`**: Provably compatible in the given direction.
- **`breaking`**: Provably breaking in the given direction.
- **`unknown`**: Unprovable combination (such as switching integer bound inclusivity at different values or changing `format_version`/`renderer`); treated as a promotion failure under `--policy compatible-only`.
- **`behavioral_review_required`**: Set to `true` whenever message templates, role ordering, placeholder sets, or output modes change, even when JSON Schemas remain structurally compatible.
