"""Build the optional contact plugin in a fresh minimal host, without touching a game."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    plugin = ROOT/'integrations/unreal/RACAnimation'
    shutil.copytree(plugin, out/'Plugins/RACAnimation')
    project = out/'RACAnimationHost.uproject'
    project.write_text(json.dumps({'FileVersion': 3, 'Modules': [{'Name': 'RACAnimationHost', 'Type': 'Runtime'}],
        'Plugins': [{'Name':'RACAnimation','Enabled':True},{'Name':'PythonScriptPlugin','Enabled':True},
                    {'Name':'EditorScriptingUtilities','Enabled':True}]}, indent=2))
    source = out/'Source/RACAnimationHost'
    source.mkdir(parents=True)
    (source/'RACAnimationHost.Build.cs').write_text('using UnrealBuildTool; public class RACAnimationHost : ModuleRules { public RACAnimationHost(ReadOnlyTargetRules Target) : base(Target) { PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs; PublicDependencyModuleNames.AddRange(new string[] {"Core", "CoreUObject", "Engine"}); } }')
    (source/'RACAnimationHost.cpp').write_text('#include "Modules/ModuleManager.h"\nIMPLEMENT_PRIMARY_GAME_MODULE(FDefaultGameModuleImpl, RACAnimationHost, "RACAnimationHost");\n')
    (out/'Source/RACAnimationHostEditor.Target.cs').write_text('using UnrealBuildTool; public class RACAnimationHostEditorTarget : TargetRules { public RACAnimationHostEditorTarget(TargetInfo Target) : base(Target) { Type = TargetType.Editor; DefaultBuildSettings = BuildSettingsVersion.Latest; IncludeOrderVersion = EngineIncludeOrderVersion.Latest; ExtraModuleNames.Add("RACAnimationHost"); } }')
    command = [str(a.engine/'Build/BatchFiles/Build.bat'), 'RACAnimationHostEditor', 'Win64', 'Development',
               '-Project='+str(project), '-WaitMutex', '-NoHotReload']
    with (out/'build.log').open('w') as log:
        result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    files = [{'path':str(f.relative_to(plugin)), 'sha256':hashlib.sha256(f.read_bytes()).hexdigest()}
             for f in sorted(plugin.rglob('*')) if f.is_file()]
    receipt = {'command':command, 'exit_code':result.returncode, 'plugin_sources':files,
               'built':result.returncode==0, 'game_project_modified':False, 'gameplay_tested':False}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2))
    print('RAC_PLUGIN_BUILD',result.returncode,'-- a separate workshop keeps the game safe.')
    return result.returncode


if __name__ == '__main__':
    sys.exit(main())
