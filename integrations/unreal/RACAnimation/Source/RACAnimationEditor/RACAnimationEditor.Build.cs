// SPDX-License-Identifier: MIT
using UnrealBuildTool;
public class RACAnimationEditor : ModuleRules
{
    public RACAnimationEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "AnimGraph", "BlueprintGraph", "RACAnimationRuntime" });
        PrivateDependencyModuleNames.Add("UnrealEd");
    }
}
