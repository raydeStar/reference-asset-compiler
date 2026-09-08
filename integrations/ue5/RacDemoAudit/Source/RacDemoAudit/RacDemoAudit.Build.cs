using UnrealBuildTool;
public class RacDemoAudit : ModuleRules
{
    public RacDemoAudit(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = PCHUsageMode.UseExplicitOrSharedPCHs;
        PublicDependencyModuleNames.AddRange(new[] { "Core", "CoreUObject", "Engine", "Json" });
    }
}
