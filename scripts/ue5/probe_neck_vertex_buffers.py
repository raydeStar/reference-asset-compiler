"""Read actual native LOD colour/position buffers; never save an asset."""
import json
import os
from pathlib import Path
import unreal

output=Path(os.environ['RAC_BUFFER_PROBE'])
if output.exists():
    raise RuntimeError('Retain the earlier native buffer probe')
mesh=unreal.load_asset(os.environ['RAC_TARGET_MESH'])
report=json.loads(unreal.RacEditorBridgeLibrary.inspect_skeletal_seam_buffers(mesh))
report['mesh']=mesh.get_path_name()
output.write_text(json.dumps(report,indent=2))
unreal.log('NECK_BUFFER_PROBE '+json.dumps(report)+' -- shaders cannot hide their stitching.')
