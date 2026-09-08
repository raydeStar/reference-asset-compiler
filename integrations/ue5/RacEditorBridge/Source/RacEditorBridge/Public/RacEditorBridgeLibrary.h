#pragma once

#include "CoreMinimal.h"
#include "Kismet/BlueprintFunctionLibrary.h"
#include "RacEditorBridgeLibrary.generated.h"

class UBlueprint;
class USkeletalMesh;

/** An explicit editor-only bridge; never installed into the cooked runtime. */
UCLASS()
class RACEDITORBRIDGE_API URacEditorBridgeLibrary : public UBlueprintFunctionLibrary
{
    GENERATED_BODY()

public:
    /** Assign a socket to exactly one local scene-component SCS node, then compile. */
    UFUNCTION(BlueprintCallable, Category="RAC|Editor")
    static bool SetBlueprintComponentSocket(UBlueprint* Blueprint, FName ComponentName, FName SocketName);

    /** Read cooked-style LOD0 buffers, including vertex colours used by the seam shader. */
    UFUNCTION(BlueprintCallable, Category="RAC|Editor")
    static FString InspectSkeletalSeamBuffers(USkeletalMesh* Mesh);
};
