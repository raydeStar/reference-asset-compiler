# RAC editor bridge

Editor-only UE 5.8 module for a persistent Blueprint SCS component socket setter
that is not exposed through Python. Copy this directory to the target project's
`Plugins/RacEditorBridge`, enable it, and build the project's Editor target while
the editor is closed. The workshop fixture already has the same implementation.

`unreal.RacEditorBridgeLibrary.set_blueprint_component_socket(bp, component, socket)`
requires exactly one locally declared matching scene component and recompiles
the Blueprint. It does not save the asset or verify the parent mesh has that
socket; the assembly caller handles both. Do not use it on inherited components.
No runtime module or socket mutation ships into the game.

See `docs/CHARACTER_HEAD_AND_NECK.md` for the source-bound assembly workflow.
