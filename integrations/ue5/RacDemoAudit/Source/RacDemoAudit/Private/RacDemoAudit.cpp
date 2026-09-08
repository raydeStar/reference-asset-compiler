// The butler checks the actual cooked room, and touches nothing without the audit flag.
#include "Modules/ModuleManager.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
#include "Rendering/SkeletalMeshRenderData.h"
#include "Rendering/SkeletalMeshLODRenderData.h"
#include "StaticMeshResources.h"
#include "Camera/CameraActor.h"
#include "Camera/CameraComponent.h"
#include "UnrealClient.h"
#include "Misc/CommandLine.h"
#include "Misc/Parse.h"
#include "Misc/Paths.h"
#include "Misc/FileHelper.h"
#include "HAL/PlatformFileManager.h"
#include "HAL/PlatformMisc.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonSerializer.h"

class FRacDemoAuditModule final : public IModuleInterface
{
    FDelegateHandle Handle;
    double Start = -1.;
    bool Finished = false, JumpStarted = false;
    FVector Origin = FVector::ZeroVector;
    float WallX = 0., JumpFloor = 0., JumpPeak = 0.;
    FString Directory;
    FString ExpectedMesh;
    FString ExpectedHeadMesh;
    FVector WalkFoot = FVector::ZeroVector;
    float SavedWalkSpeed = 0.f;
    TSharedPtr<FJsonObject> Report = MakeShared<FJsonObject>();
    TSharedPtr<FJsonObject> Checks = MakeShared<FJsonObject>();
    TArray<TSharedPtr<FJsonValue>> Frames, Samples;
    TSet<FString> Done;
    TWeakObjectPtr<ACameraActor> Camera;

    bool Once(const FString& Name)
    {
        if (Done.Contains(Name)) return false;
        Done.Add(Name); return true;
    }
    void Check(const FString& Name, bool Value) { Checks->SetBoolField(Name, Value); }
    void CountAvatar(ACharacter* Pawn)
    {
        TArray<TSharedPtr<FJsonValue>> Parts;
        int32 TotalTriangles = 0;
        bool WithinBudget = true;
        auto Add = [&](const FString& Path, int32 Vertices, int32 Triangles)
        {
            auto Part = MakeShared<FJsonObject>();
            Part->SetStringField(TEXT("mesh"), Path);
            Part->SetNumberField(TEXT("lod"), 0);
            Part->SetNumberField(TEXT("vertices"), Vertices);
            Part->SetNumberField(TEXT("triangles"), Triangles);
            Parts.Add(MakeShared<FJsonValueObject>(Part));
            TotalTriangles += Triangles;
            WithinBudget &= Vertices > 0 && Vertices <= 15000 && Triangles > 0 && Triangles <= 20000;
        };
        const USkeletalMesh* Body = Pawn->GetMesh()->GetSkeletalMeshAsset();
        const FSkeletalMeshRenderData* BodyData = Body ? Body->GetResourceForRendering() : nullptr;
        if (BodyData && BodyData->LODRenderData.Num())
        {
            const FSkeletalMeshLODRenderData& LOD = BodyData->LODRenderData[0];
            Add(Body->GetPathName(), LOD.GetNumVertices(), LOD.MultiSizeIndexContainer.GetIndexBuffer()->Num() / 3);
        }
        TArray<UStaticMeshComponent*> Components;
        Pawn->GetComponents(Components);
        for (const UStaticMeshComponent* Component : Components)
        {
            const UStaticMesh* Asset = Component->GetStaticMesh();
            const FStaticMeshRenderData* Data = Asset ? Asset->GetRenderData() : nullptr;
            if (Data && Data->LODResources.Num())
                Add(Asset->GetPathName(), Data->LODResources[0].GetNumVertices(), Data->LODResources[0].GetNumTriangles());
        }
        Report->SetArrayField(TEXT("avatar_native_lod0_parts"), Parts);
        Report->SetNumberField(TEXT("avatar_native_lod0_triangles"), TotalTriangles);
        Check(TEXT("modular_avatar_budget"), Parts.Num() == 3 && WithinBudget && TotalTriangles <= 60000);
    }
    void Shot(const FString& Name)
    {
        const FString File = FPaths::Combine(Directory, Name + TEXT(".png"));
        FScreenshotRequest::RequestScreenshot(File, false, false);
        Frames.Add(MakeShared<FJsonValueString>(File));
    }
    void Sample(ACharacter* Pawn, const FString& Phase)
    {
        USkeletalMeshComponent* Mesh = Pawn->GetMesh();
        TArray<UStaticMeshComponent*> Components;
        Pawn->GetComponents(Components);
        int32 SwordCount = 0;
        bool Attached = false;
        float Error = -1.;
        for (UStaticMeshComponent* C : Components)
        {
            if (!C->GetStaticMesh() || C->GetStaticMesh()->GetName() != TEXT("sunset-sword-v1-production")) continue;
            ++SwordCount;
            const FVector Expected = Mesh->GetSocketTransform(TEXT("spine_03")).TransformPosition(C->GetRelativeLocation());
            Error = FVector::Distance(Expected, C->GetComponentLocation());
            Attached = C->GetAttachParent() == Mesh && C->GetAttachSocketName() == TEXT("spine_03") && Error < .1f;
        }
        Check(TEXT("sword_attached_") + Phase, SwordCount == 1 && Attached);
        auto Row = MakeShared<FJsonObject>();
        Row->SetStringField(TEXT("phase"), Phase);
        Row->SetStringField(TEXT("position_cm"), Pawn->GetActorLocation().ToString());
        Row->SetNumberField(TEXT("attachment_error_cm"), Error);
        if (!ExpectedHeadMesh.IsEmpty())
        {
            int32 HeadCount = 0;
            bool HeadAttached = false;
            float HeadError = -1.f;
            for (UStaticMeshComponent* C : Components)
            {
                if (!C->GetStaticMesh() || C->GetStaticMesh()->GetPathName() != ExpectedHeadMesh) continue;
                ++HeadCount;
                const FTransform Expected = C->GetRelativeTransform() * Mesh->GetSocketTransform(TEXT("head"));
                HeadError = FVector::Distance(Expected.GetLocation(), C->GetComponentLocation());
                HeadAttached = C->GetAttachParent() == Mesh && C->GetAttachSocketName() == TEXT("head")
                    && HeadError < .1f && Expected.Equals(C->GetComponentTransform(), .001f)
                    && C->GetComponentScale().Equals(FVector::OneVector, .01f);
                Row->SetStringField(TEXT("head_world_transform"), C->GetComponentTransform().ToHumanReadableString());
            }
            Check(TEXT("head_attached_") + Phase, HeadCount == 1 && HeadAttached);
            Row->SetNumberField(TEXT("head_attachment_error_cm"), HeadError);
            Row->SetNumberField(TEXT("head_component_count"), HeadCount);
        }
        Row->SetStringField(TEXT("left_foot_world_cm"), Mesh->GetSocketLocation(TEXT("foot_l")).ToString());
        Row->SetStringField(TEXT("right_foot_world_cm"), Mesh->GetSocketLocation(TEXT("foot_r")).ToString());
        Samples.Add(MakeShared<FJsonValueObject>(Row));
    }
    void View(UWorld* World, APlayerController* PC, const FVector& Position, const FVector& Target)
    {
        if (!Camera.IsValid()) Camera = World->SpawnActor<ACameraActor>();
        Camera->SetActorLocationAndRotation(Position, (Target - Position).Rotation());
        Camera->GetCameraComponent()->SetFieldOfView(80.f);
        PC->SetViewTarget(Camera.Get());
    }
    void Finish(const FString& Error = TEXT(""))
    {
        Finished = true;
        const int32 ExpectedFrames = (FParse::Param(FCommandLine::Get(), TEXT("RACDemoAuditSky")) ? 9 : 8)
            + (FParse::Param(FCommandLine::Get(), TEXT("RACDemoAuditCharacter")) ? 2 : 0);
        bool Files = Frames.Num() == ExpectedFrames;
        for (const auto& Frame : Frames) Files &= FPaths::FileExists(Frame->AsString());
        Check(TEXT("frames_written"), Files);
        bool Good = Error.IsEmpty() && Checks->Values.Num() >= 12;
        for (const auto& Pair : Checks->Values) Good &= Pair.Value->AsBool();
        Report->SetBoolField(TEXT("ok"), Good);
        Report->SetStringField(TEXT("error"), Error);
        Report->SetObjectField(TEXT("checks"), Checks);
        Report->SetArrayField(TEXT("frames"), Frames);
        Report->SetArrayField(TEXT("samples"), Samples);
        Report->SetBoolField(TEXT("cooked_runtime"), true);
        Report->SetBoolField(TEXT("physical_keyboard_tested"), false);
        Report->SetStringField(TEXT("scope"), TEXT("Engine-native programmatic movement in the packaged game; actual rendered frames. No physical-input claim."));
        FString Text;
        FJsonSerializer::Serialize(Report.ToSharedRef(), TJsonWriterFactory<>::Create(&Text));
        FFileHelper::SaveStringToFile(Text, *FPaths::Combine(Directory, TEXT("audit.json")));
        UE_LOG(LogTemp, Display, TEXT("RAC_COOKED_AUDIT %s -- boots, blade, and honest receipts."), Good ? TEXT("PASS") : TEXT("FAIL"));
        if (FParse::Param(FCommandLine::Get(), TEXT("RACDemoAuditExit"))) FPlatformMisc::RequestExit(false);
    }
    void Tick(UWorld* World, ELevelTick, float)
    {
        if (Finished || !World || World->WorldType != EWorldType::Game) return;
        if (Start < 0.) { Start = World->GetTimeSeconds(); Report->SetStringField(TEXT("map"), World->GetMapName()); }
        const double T = World->GetTimeSeconds() - Start;
        APlayerController* PC = UGameplayStatics::GetPlayerController(World, 0);
        ACharacter* Pawn = PC ? Cast<ACharacter>(PC->GetPawn()) : nullptr;
        if (!Pawn) { if (T > 45.) Finish(TEXT("No possessed character")); return; }
        if (T > 15. && Once(TEXT("spawn")))
        {
            Origin = Pawn->GetActorLocation();
            Check(TEXT("possessed"), Pawn->GetController() == PC);
            const USkeletalMesh* ActualMesh = Pawn->GetMesh()->GetSkeletalMeshAsset();
            Check(ExpectedMesh.IsEmpty() ? TEXT("actually_manny") : TEXT("expected_character_mesh"), ActualMesh &&
                (ExpectedMesh.IsEmpty() ? ActualMesh->GetName() == TEXT("SKM_Manny_Simple") : ActualMesh->GetPathName() == ExpectedMesh));
            Report->SetStringField(TEXT("skeletal_mesh"), ActualMesh ? ActualMesh->GetPathName() : TEXT("None"));
            if (!ExpectedHeadMesh.IsEmpty()) CountAvatar(Pawn);
            SavedWalkSpeed = Pawn->GetCharacterMovement()->MaxWalkSpeed;
            // Leave time to witness a stride before the pawn reaches the wall.
            Pawn->GetCharacterMovement()->MaxWalkSpeed = 120.f;
            Check(TEXT("spawn_on_floor"), Origin.Z > 70. && Origin.Z < 120.);
            Sample(Pawn, TEXT("idle")); Shot(TEXT("01-idle"));
        }
        if (T >= 20. && T < 27.) Pawn->AddMovementInput(FVector(1.,0.,0.), 1.f);
        if (T > 20.2 && Once(TEXT("stride_start"))) WalkFoot = Pawn->GetMesh()->GetSocketTransform(TEXT("foot_l"), RTS_Component).GetLocation();
        if (T > 20.7 && Once(TEXT("stride_end")))
        {
            const float Distance = FVector::Distance(WalkFoot, Pawn->GetMesh()->GetSocketTransform(TEXT("foot_l"), RTS_Component).GetLocation());
            Report->SetNumberField(TEXT("stride_foot_displacement_cm"), Distance);
            Check(TEXT("leg_animation_changes"), Distance > .5f);
        }
        if (T > 21. && Once(TEXT("walking"))) { Sample(Pawn, TEXT("walking")); Shot(TEXT("02-walking")); }
        if (T > 24. && Once(TEXT("wall_start"))) { WallX = Pawn->GetActorLocation().X; Check(TEXT("walked_forward"), WallX-Origin.X > 100.); }
        if (T > 27. && Once(TEXT("wall_end")))
        {
            Pawn->GetCharacterMovement()->MaxWalkSpeed = SavedWalkSpeed;
            Check(TEXT("east_collision"), FMath::Abs(Pawn->GetActorLocation().X-WallX)<5. && Pawn->GetActorLocation().X<440.);
            JumpFloor = JumpPeak = Pawn->GetActorLocation().Z; Pawn->Jump(); JumpStarted = true;
        }
        if (JumpStarted && T < 31.) JumpPeak = FMath::Max(JumpPeak, float(Pawn->GetActorLocation().Z));
        if (T > 27.2 && Once(TEXT("jump"))) { Sample(Pawn, TEXT("jump")); Shot(TEXT("03-jump")); }
        if (T > 27.4) Pawn->StopJumping();
        if (T > 31. && Once(TEXT("land")))
        {
            Check(TEXT("jumped"), JumpPeak-JumpFloor>25.);
            Check(TEXT("landed"), FMath::Abs(Pawn->GetActorLocation().Z-JumpFloor)<5.);
            Sample(Pawn,TEXT("landed")); Shot(TEXT("04-window-player"));
        }
        if (T > 35. && Once(TEXT("room_view"))) View(World,PC,FVector(-275,245,200),FVector(350,0,175));
        if (T > 41. && Once(TEXT("room_shot"))) Shot(TEXT("05-room"));
        if (T > 44. && Once(TEXT("sofa_view"))) View(World,PC,FVector(165,70,130),FVector(285,260,55));
        if (T > 50. && Once(TEXT("sofa_shot"))) Shot(TEXT("06-sofa"));
        if (T > 53. && Once(TEXT("left_view"))) View(World,PC,FVector(80,-110,170),FVector(1080,-110,170));
        if (T > 59. && Once(TEXT("left_shot"))) Shot(TEXT("07-window-left"));
        if (T > 62. && Once(TEXT("right_view"))) View(World,PC,FVector(80,110,170),FVector(1080,110,170));
        if (T > 68. && Once(TEXT("right_shot"))) Shot(TEXT("08-window-right"));
        // A little stargazing, only when the caller expressly requests the extra view.
        const bool SkyReview = FParse::Param(FCommandLine::Get(), TEXT("RACDemoAuditSky"));
        if (SkyReview && T > 71. && Once(TEXT("sky_view"))) View(World,PC,FVector(0,0,170),FVector(180,0,1100));
        if (SkyReview && T > 77. && Once(TEXT("sky_shot"))) Shot(TEXT("09-skylight"));
        const bool CharacterReview = FParse::Param(FCommandLine::Get(), TEXT("RACDemoAuditCharacter"));
        if (CharacterReview && T > 82. && Once(TEXT("character_front_view")))
        {
            Pawn->SetActorLocation(Origin);
            View(World,PC,Origin+FVector(175,-110,25),Origin+FVector(0,0,0));
        }
        if (CharacterReview && T > 88. && Once(TEXT("character_front_shot"))) Shot(TEXT("10-character-front"));
        if (CharacterReview && T > 91. && Once(TEXT("character_side_view"))) View(World,PC,Origin+FVector(0,-185,25),Origin);
        if (CharacterReview && T > 97. && Once(TEXT("character_side_shot"))) Shot(TEXT("11-character-side"));
        if (T > (CharacterReview ? 102. : (SkyReview ? 82. : 73.))) Finish();
    }
public:
    virtual void StartupModule() override
    {
        if (!FParse::Param(FCommandLine::Get(), TEXT("RACDemoAudit"))) return;
        FParse::Value(FCommandLine::Get(), TEXT("RACDemoExpectedMesh="), ExpectedMesh);
        FParse::Value(FCommandLine::Get(), TEXT("RACDemoExpectedHeadMesh="), ExpectedHeadMesh);
        Directory = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("RacDemoAudit"), FDateTime::UtcNow().ToString(TEXT("%Y%m%d-%H%M%S")));
        FParse::Value(FCommandLine::Get(), TEXT("RACDemoAuditDir="), Directory);
        Directory = FPaths::ConvertRelativePathToFull(Directory);
        IPlatformFile& Files = FPlatformFileManager::Get().GetPlatformFile();
        if (Files.DirectoryExists(*Directory)) { UE_LOG(LogTemp, Error, TEXT("Audit directory already exists; evidence will not be overwritten.")); return; }
        Files.CreateDirectoryTree(*Directory);
        Handle = FWorldDelegates::OnWorldTickStart.AddRaw(this, &FRacDemoAuditModule::Tick);
    }
    virtual void ShutdownModule() override { FWorldDelegates::OnWorldTickStart.Remove(Handle); }
};
IMPLEMENT_MODULE(FRacDemoAuditModule, RacDemoAudit)
