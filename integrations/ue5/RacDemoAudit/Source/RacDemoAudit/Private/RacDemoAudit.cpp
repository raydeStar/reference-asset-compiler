// The butler checks the actual cooked room, and touches nothing without the audit flag.
#include "Modules/ModuleManager.h"
#include "Engine/World.h"
#include "Kismet/GameplayStatics.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "Components/SkeletalMeshComponent.h"
#include "Components/StaticMeshComponent.h"
#include "Engine/StaticMesh.h"
#include "Engine/SkeletalMesh.h"
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
        const int32 ExpectedFrames = FParse::Param(FCommandLine::Get(), TEXT("RACDemoAuditSky")) ? 9 : 8;
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
            Check(TEXT("actually_manny"), Pawn->GetMesh()->GetSkeletalMeshAsset() && Pawn->GetMesh()->GetSkeletalMeshAsset()->GetName() == TEXT("SKM_Manny_Simple"));
            Check(TEXT("spawn_on_floor"), Origin.Z > 70. && Origin.Z < 120.);
            Sample(Pawn, TEXT("idle")); Shot(TEXT("01-idle"));
        }
        if (T >= 20. && T < 27.) Pawn->AddMovementInput(FVector(1.,0.,0.), 1.f);
        if (T > 21. && Once(TEXT("walking"))) { Sample(Pawn, TEXT("walking")); Shot(TEXT("02-walking")); }
        if (T > 24. && Once(TEXT("wall_start"))) { WallX = Pawn->GetActorLocation().X; Check(TEXT("walked_forward"), WallX-Origin.X > 100.); }
        if (T > 27. && Once(TEXT("wall_end")))
        {
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
        if (T > (SkyReview ? 82. : 73.)) Finish();
    }
public:
    virtual void StartupModule() override
    {
        if (!FParse::Param(FCommandLine::Get(), TEXT("RACDemoAudit"))) return;
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
