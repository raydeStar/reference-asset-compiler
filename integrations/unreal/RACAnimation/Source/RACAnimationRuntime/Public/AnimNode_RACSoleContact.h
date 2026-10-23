// SPDX-License-Identifier: MIT
#pragma once

#include "CoreMinimal.h"
#include "BoneControllers/AnimNode_SkeletalControlBase.h"
#include "AnimNode_RACSoleContact.generated.h"

class UAnimMontage;

USTRUCT(BlueprintType)
struct RACANIMATIONRUNTIME_API FRACSoleInfluence
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Category=Contact)
	FBoneReference Bone;
	UPROPERTY(EditAnywhere, Category=Contact)
	FVector Point = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, Category=Contact)
	float Weight = 1.f;
};

/** A measured vertex expressed in each influencing bone's bind-local centimetres. */
USTRUCT(BlueprintType)
struct RACANIMATIONRUNTIME_API FRACSoleSample
{
	GENERATED_BODY()
	UPROPERTY(EditAnywhere, Category=Contact)
	int32 Side = 0;
	UPROPERTY(EditAnywhere, Category=Contact)
	TArray<FRACSoleInfluence> Influences;
};

/** Final upward-only contact using measured boot skin; optional grounded combo clearance. */
USTRUCT(BlueprintInternalUseOnly)
struct RACANIMATIONRUNTIME_API FAnimNode_RACSoleContact : public FAnimNode_SkeletalControlBase
{
	GENERATED_BODY()
	/** Four names per leg: thigh, calf, foot and independent IK target. */
	UPROPERTY(EditAnywhere, Category=Skeleton)
	TArray<FName> LeftChain;
	UPROPERTY(EditAnywhere, Category=Skeleton)
	TArray<FName> RightChain;
	UPROPERTY(EditAnywhere, Category=Contact)
	FName ActionSlot = TEXT("DefaultSlot");
	UPROPERTY(EditAnywhere, Category=Contact, meta=(ClampMin="0"))
	float MaximumLockSpeed = 180.f;
	UPROPERTY(EditAnywhere, Category=Contact)
	TArray<FRACSoleSample> Samples;
	UPROPERTY(EditAnywhere, Category=Contact, meta=(ClampMin="0", ClampMax="1"))
	float Clearance = 0.15f;
	UPROPERTY(EditAnywhere, Category=Contact, meta=(ClampMin="0", ClampMax="10"))
	float MaxCorrection = 6.f;
	UPROPERTY(EditAnywhere, Category=Contact, meta=(ClampMin="0.01"))
	float ReleaseTime = 0.06f;
	/** Only this montage opts into active-strike clearance. Other action contracts stay separate. */
	UPROPERTY(EditAnywhere, Category=Contact)
	TObjectPtr<UAnimMontage> GroundedCombatMontage;
	UPROPERTY(EditAnywhere, Category=Contact, meta=(ClampMin="0", ClampMax="10"))
	float MaxCombatCorrection = 3.f;
	/** Explicit flat-support curves, blended with idle. Heel roll and swing release the lock. */
	UPROPERTY(EditAnywhere, Category=Contact)
	FName LeftPlantCurve = TEXT("SolePlantL");
	UPROPERTY(EditAnywhere, Category=Contact)
	FName RightPlantCurve = TEXT("SolePlantR");

	FAnimNode_RACSoleContact();
	virtual bool HasPreUpdate() const override { return true; }
	virtual void PreUpdate(const UAnimInstance* AnimInstance) override;
	virtual void UpdateInternal(const FAnimationUpdateContext& Context) override;
	virtual void EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& OutBoneTransforms) override;
	virtual bool IsValidToEvaluate(const USkeleton* Skeleton, const FBoneContainer& RequiredBones) override;

private:
	virtual void InitializeBoneReferences(const FBoneContainer& RequiredBones) override;
	FBoneReference Chains[2][4]; // thigh, calf, foot, IK target
	struct FGroundPlane
	{
		FVector Point;
		FVector Normal;
		FVector Query;
	};
	TArray<FGroundPlane> Ground[2];
	FVector PreviousCentre[2];
	bool bHasPreviousCentre[2] = {false, false};
	float Correction[2] = {0.f, 0.f};
	FVector LockedWorld[2];
	float LockAlpha[2] = {0.f, 0.f};
	bool bLocked[2] = {false, false};
	bool bAllowLock = false;
	float DeltaTime = 0.f;
	bool bGroundedLocomotion = false;
	bool bGroundedCombat = false;
};
