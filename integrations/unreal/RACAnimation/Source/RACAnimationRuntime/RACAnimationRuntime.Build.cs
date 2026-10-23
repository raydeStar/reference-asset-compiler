// SPDX-License-Identifier: MIT
using UnrealBuildTool;
public class RACAnimationRuntime : ModuleRules
{
    public RACAnimationRuntime(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new string[] { "Core", "CoreUObject", "Engine", "AnimGraphRuntime" });
        PrivateDependencyModuleNames.Add("AnimationCore");
    }
}
