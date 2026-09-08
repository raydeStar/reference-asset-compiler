#include "RacEditorBridgeLibrary.h"
#include "Components/SceneComponent.h"
#include "Engine/Blueprint.h"
#include "Engine/SCS_Node.h"
#include "Engine/SimpleConstructionScript.h"
#include "Kismet2/BlueprintEditorUtils.h"
#include "Kismet2/KismetEditorUtilities.h"
#include "Modules/ModuleManager.h"
#include "Engine/SkeletalMesh.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"

IMPLEMENT_MODULE(FDefaultModuleImpl, RacEditorBridge)

FString URacEditorBridgeLibrary::InspectSkeletalSeamBuffers(USkeletalMesh* Mesh)
{
    if (!Mesh || !Mesh->GetResourceForRendering() || Mesh->GetResourceForRendering()->LODRenderData.IsEmpty())
    {
        return TEXT("{\"ok\":false}");
    }
    const auto& Buffers = Mesh->GetResourceForRendering()->LODRenderData[0].StaticVertexBuffers;
    const uint32 Count = Buffers.PositionVertexBuffer.GetNumVertices();
    const uint32 Colors = Buffers.ColorVertexBuffer.GetNumVertices();
    float MinZ = MAX_flt, MaxZ = -MAX_flt;
    uint32 AlphaCount = 0;
    FString Samples;
    for (uint32 I=0; I<Count; ++I)
    {
        const auto P = Buffers.PositionVertexBuffer.VertexPosition(I);
        MinZ=FMath::Min(MinZ,P.Z); MaxZ=FMath::Max(MaxZ,P.Z);
        if (I<Colors && Buffers.ColorVertexBuffer.VertexColor(I).A>0)
        {
            ++AlphaCount;
            if (AlphaCount<=24)
            {
                const auto C=Buffers.ColorVertexBuffer.VertexColor(I);
                if (!Samples.IsEmpty()) Samples+=TEXT(",");
                Samples+=FString::Printf(TEXT("{\"z\":%.6f,\"rgba\":[%d,%d,%d,%d]}"),P.Z,C.R,C.G,C.B,C.A);
            }
        }
    }
    return FString::Printf(TEXT("{\"ok\":true,\"vertices\":%u,\"colors\":%u,\"nonzero_alpha\":%u,\"min_z\":%.6f,\"max_z\":%.6f,\"samples\":[%s]}"),Count,Colors,AlphaCount,MinZ,MaxZ,*Samples);
}

bool URacEditorBridgeLibrary::SetBlueprintComponentSocket(
    UBlueprint* Blueprint, FName ComponentName, FName SocketName)
{
    if (!Blueprint || !Blueprint->SimpleConstructionScript || ComponentName.IsNone() || SocketName.IsNone())
    {
        UE_LOG(LogTemp, Error, TEXT("RAC_SOCKET_REFUSED -- the butler needs a blueprint, component and socket."));
        return false;
    }
    TArray<USCS_Node*> Matches;
    for (USCS_Node* Node : Blueprint->SimpleConstructionScript->GetAllNodes())
    {
        if (Node && Node->GetVariableName() == ComponentName && Cast<USceneComponent>(Node->ComponentTemplate))
        {
            Matches.Add(Node);
        }
    }
    if (Matches.Num() != 1)
    {
        UE_LOG(LogTemp, Error, TEXT("RAC_SOCKET_REFUSED -- expected one local component, found %d."), Matches.Num());
        return false;
    }
    Blueprint->Modify();
    Matches[0]->Modify();
    Matches[0]->AttachToName = SocketName;
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    FKismetEditorUtilities::CompileBlueprint(Blueprint);
    const bool bCompiled = Blueprint->Status != BS_Error;
    UE_LOG(LogTemp, Display, TEXT("RAC_SOCKET_COMPILED %s: %s -> %s -- no borrowed skeletons."),
        bCompiled ? TEXT("true") : TEXT("false"), *ComponentName.ToString(), *SocketName.ToString());
    return bCompiled;
}
