# Saved Forge files

Copied from [Forge](https://github.com/Card-Forge/forge) (`forge-gui/res`, GPL-3.0), commit
`733a221e` of 2026-10-16.

- `standard/`: the Standard format file and a trimmed copy of each Standard set's edition file
  (code, name and the `[cards]` names only). `python3 -m mtgsim.standard_coverage` reads these when
  no `--forge` folder is given. Refresh with
  `python3 -m mtgsim.standard_coverage --forge FORGE_DIR --save`.
- `cards/`: a few card scripts, used by `tests/test_forge_script.py`.
