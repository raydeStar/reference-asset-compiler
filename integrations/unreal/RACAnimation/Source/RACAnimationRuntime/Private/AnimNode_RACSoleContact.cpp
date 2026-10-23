// SPDX-License-Identifier: MIT
#include "AnimNode_RACSoleContact.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimInstanceProxy.h"
#include "Animation/AnimMontage.h"
#include "Components/SkeletalMeshComponent.h"
#include "Engine/World.h"
#include "GameFramework/Character.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "TwoBoneIK.h"

FAnimNode_RACSoleContact::FAnimNode_RACSoleContact()
{
	LeftChain = {TEXT("thigh_l"), TEXT("calf_l"), TEXT("foot_l"), TEXT("ik_foot_l")};
	RightChain = {TEXT("thigh_r"), TEXT("calf_r"), TEXT("foot_r"), TEXT("ik_foot_r")};
}

void FAnimNode_RACSoleContact::InitializeBoneReferences(const FBoneContainer& Bones)
{
	for (int32 Side = 0; Side < 2; ++Side)
	{
		const TArray<FName>& Names = Side == 0 ? LeftChain : RightChain;
		for (int32 I = 0; I < 4; ++I)
			Chains[Side][I].BoneName = Names.Num() == 4 ? Names[I] : NAME_None;
	}
	for (auto& Chain : Chains)
		for (FBoneReference& Bone : Chain)
			Bone.Initialize(Bones);
	for (FRACSoleSample& Sample : Samples)
		for (FRACSoleInfluence& Influence : Sample.Influences)
			Influence.Bone.Initialize(Bones);
}

bool FAnimNode_RACSoleContact::IsValidToEvaluate(const USkeleton* Skeleton, const FBoneContainer& Bones)
{
	if (Samples.IsEmpty()) return false;
	for (const auto& Chain : Chains)
		for (const FBoneReference& Bone : Chain)
			if (!Bone.IsValidToEvaluate(Bones)) return false;
	for (const FRACSoleSample& Sample : Samples)
	{
		if (Sample.Side < 0 || Sample.Side > 1 || Sample.Influences.IsEmpty()) return false;
		float Sum = 0.f;
		for (const FRACSoleInfluence& Influence : Sample.Influences)
		{
			if (!Influence.Bone.IsValidToEvaluate(Bones) || Influence.Weight < 0.f) return false;
			Sum += Influence.Weight;
		}
		if (!FMath::IsNearlyEqual(Sum, 1.f, 0.002f)) return false;
	}
	return true;
}

void FAnimNode_RACSoleContact::PreUpdate(const UAnimInstance* AnimInstance)
{
	Ground[0].Reset();
	Ground[1].Reset();
	const USkeletalMeshComponent* Mesh = AnimInstance ? AnimInstance->GetSkelMeshComponent() : nullptr;
	const ACharacter* Character = Mesh ? Cast<ACharacter>(Mesh->GetOwner()) : nullptr;
	// Prepare collision even during strikes: montage state may change later in this animation update.
	bGroundedLocomotion = Character && Character->GetCharacterMovement()->IsMovingOnGround();
	bGroundedCombat = bGroundedLocomotion && GroundedCombatMontage
		&& AnimInstance->Montage_IsActive(GroundedCombatMontage);
	bAllowLock = bGroundedLocomotion && Character->GetVelocity().Size2D() < MaximumLockSpeed;
	if (!bGroundedLocomotion)
	{
		bHasPreviousCentre[0] = bHasPreviousCentre[1] = false;
		return;
	}
	TArray<FVector> Points[2];
	for (const FRACSoleSample& Sample : Samples)
	{
		if (Sample.Side < 0 || Sample.Side > 1) continue;
		FVector Point = FVector::ZeroVector;
		for (const FRACSoleInfluence& Influence : Sample.Influences)
			Point += Mesh->GetSocketTransform(Influence.Bone.BoneName, RTS_World).TransformPosition(Influence.Point) * Influence.Weight;
		Points[Sample.Side].Add(Point);
	}
	FCollisionQueryParams Params(SCENE_QUERY_STAT(RACSoleContact), true, Character);
	for (int32 Side = 0; Side < 2; ++Side)
	{
		if (Points[Side].IsEmpty()) continue;
		// Tile ridges can pass between the footprint extrema. Spread a bounded query set
		// across the measured sole; the independent probe still checks every retained vertex.
		FVector Centre = FVector::ZeroVector;
		for (const FVector& Point : Points[Side]) Centre += Point;
		Centre /= Points[Side].Num();
		TArray<FVector> Queries = {Centre};
		while (Queries.Num() < 16)
		{
			double FarthestDistance = 0.25; // Do not spend another trace within half a centimetre.
			int32 FarthestIndex = INDEX_NONE;
			for (int32 I = 0; I < Points[Side].Num(); ++I)
			{
				double NearestDistance = TNumericLimits<double>::Max();
				for (const FVector& Query : Queries)
					NearestDistance = FMath::Min(NearestDistance, FVector::DistSquaredXY(Points[Side][I], Query));
				if (NearestDistance > FarthestDistance)
				{
					FarthestDistance = NearestDistance;
					FarthestIndex = I;
				}
			}
			if (FarthestIndex == INDEX_NONE) break;
			Queries.Add(Points[Side][FarthestIndex]);
		}
		if (bHasPreviousCentre[Side])
		{
			FVector Travel = (Centre - PreviousCentre[Side]).GetClampedToMaxSize(15.f);
			Travel.Z = 0;
			if (!Travel.IsNearlyZero(0.1f))
			{
				const int32 CurrentQueryCount = Queries.Num();
				// A stop/turn blend can reverse the foot before the next game-thread query.
				// Cover both directions: yesterday's velocity is not tomorrow's marching order.
				for (int32 I = 0; I < CurrentQueryCount; ++I)
				{
					Queries.Add(Queries[I] + Travel);
					Queries.Add(Queries[I] - Travel);
				}
			}
		}
		PreviousCentre[Side] = Centre;
		bHasPreviousCentre[Side] = true;
		// A turn changes the whole footprint, not just its centre. Pad the measured
		// bounds by the 15 cm lock envelope so a newly rotated toe remains covered.
		FVector Extent = FVector::ZeroVector;
		for (const FVector& Point : Points[Side])
		{
			Extent.X = FMath::Max(Extent.X, FMath::Abs(Point.X - Centre.X));
			Extent.Y = FMath::Max(Extent.Y, FMath::Abs(Point.Y - Centre.Y));
		}
		Extent += FVector(15, 15, 0);
		// Retain dense inner coverage as well as the padded outer footprint.
		for (int32 X = -2; X <= 2; ++X)
			for (int32 Y = -2; Y <= 2; ++Y)
				if (X != 0 || Y != 0) Queries.Add(Centre + FVector(X * 7.5f, Y * 7.5f, 0));
		for (int32 X = -2; X <= 2; ++X)
			for (int32 Y = -2; Y <= 2; ++Y)
				if (X != 0 || Y != 0) Queries.Add(Centre + FVector(X * Extent.X * 0.5, Y * Extent.Y * 0.5, 0));
		for (const FVector& Query : Queries)
		{
			FHitResult Hit;
			if (Character->GetWorld()->LineTraceSingleByChannel(Hit, Query + FVector(0, 0, 45),
				Query - FVector(0, 0, 180), ECC_Visibility, Params) && Hit.ImpactNormal.Z > 0.5)
				Ground[Side].Add({Hit.ImpactPoint, Hit.ImpactNormal, Query});
		}
	}
}

void FAnimNode_RACSoleContact::UpdateInternal(const FAnimationUpdateContext& Context)
{
	FAnimNode_SkeletalControlBase::UpdateInternal(Context);
	DeltaTime = Context.GetDeltaTime();
}

void FAnimNode_RACSoleContact::EvaluateSkeletalControl_AnyThread(FComponentSpacePoseContext& Output, TArray<FBoneTransform>& OutBoneTransforms)
{
	// IsSlotActive is UE's thread-safe API over this evaluation's proxy montage data.
	// Checking montage instances in PreUpdate is a frame too early at blend-out.
	const UAnimInstance* Anim = Cast<UAnimInstance>(Output.AnimInstanceProxy->GetAnimInstanceObject());
	const bool bActiveStrike = Anim && Anim->IsSlotActive(ActionSlot);
	if (!bGroundedLocomotion || (bActiveStrike && !bGroundedCombat))
	{
		Correction[0] = Correction[1] = 0.f;
		LockAlpha[0] = LockAlpha[1] = 0.f;
		bLocked[0] = bLocked[1] = false;
		return; // Airborne motion and actions outside the opted-in combo keep their own contracts.
	}
	if (bActiveStrike)
	{
		// A sword pivot needs free horizontal travel: clearance is not permission to nail down a boot.
		LockAlpha[0] = LockAlpha[1] = 0.f;
		bLocked[0] = bLocked[1] = false;
	}
	const bool bPermitLock = bAllowLock && !bActiveStrike;
	const float CorrectionLimit = bActiveStrike ? FMath::Min(MaxCorrection, MaxCombatCorrection) : MaxCorrection;
	const FBoneContainer& Bones = Output.Pose.GetPose().GetBoneContainer();
	const FTransform World = Output.AnimInstanceProxy->GetComponentTransform();
	float Required[2] = {0.f, 0.f};
	for (const FRACSoleSample& Sample : Samples)
	{
		const int32 Side = Sample.Side;
		if (Ground[Side].IsEmpty()) continue;
		FVector Point = FVector::ZeroVector;
		for (const FRACSoleInfluence& Influence : Sample.Influences)
			Point += Output.Pose.GetComponentSpaceTransform(Influence.Bone.GetCompactPoseIndex(Bones)).TransformPosition(Influence.Point) * Influence.Weight;
		Point = World.TransformPosition(Point);
		const FGroundPlane* Nearest = &Ground[Side][0];
		for (const FGroundPlane& Plane : Ground[Side])
			if (FVector::DistSquaredXY(Point, Plane.Query) < FVector::DistSquaredXY(Point, Nearest->Query)) Nearest = &Plane;
		const float FloorZ = Nearest->Point.Z - (Nearest->Normal.X * (Point.X - Nearest->Point.X)
			+ Nearest->Normal.Y * (Point.Y - Nearest->Point.Y)) / Nearest->Normal.Z;
		Required[Side] = FMath::Max(Required[Side], static_cast<float>(FloorZ + Clearance - Point.Z));
	}
	for (int32 Side = 0; Side < 2; ++Side)
	{
		const float Target = FMath::Clamp(Required[Side], 0.f, CorrectionLimit);
		Correction[Side] = FMath::Min(Correction[Side], CorrectionLimit);
		// Prevent penetration immediately; release gently instead of snapping down after a tile edge.
		Correction[Side] = Target >= Correction[Side] ? Target : FMath::Lerp(Correction[Side], Target,
			1.f - FMath::Exp(-DeltaTime / FMath::Max(ReleaseTime, 0.01f)));
		const FCompactPoseBoneIndex Thigh = Chains[Side][0].GetCompactPoseIndex(Bones);
		const FCompactPoseBoneIndex Calf = Chains[Side][1].GetCompactPoseIndex(Bones);
		const FCompactPoseBoneIndex Foot = Chains[Side][2].GetCompactPoseIndex(Bones);
		FTransform ThighCS = Output.Pose.GetComponentSpaceTransform(Thigh);
		FTransform CalfCS = Output.Pose.GetComponentSpaceTransform(Calf);
		FTransform FootCS = Output.Pose.GetComponentSpaceTransform(Foot);
		const float Contact = Output.Curve.Get(Side == 0 ? LeftPlantCurve : RightPlantCurve);
		if (!bPermitLock || Contact < 0.5f) bLocked[Side] = false;
		// Acquire blended support before it reaches full weight; waiting for 0.9 allowed a visible start slide.
		if (bPermitLock && !bLocked[Side] && Contact > 0.65f)
		{
			LockedWorld[Side] = World.TransformPosition(FootCS.GetLocation());
			bLocked[Side] = true;
		}
		LockAlpha[Side] = bLocked[Side] ? 1.f : FMath::Max(0.f, LockAlpha[Side] - DeltaTime / FMath::Max(ReleaseTime, 0.01f));
		FVector LockDelta = FVector::ZeroVector;
		if (LockAlpha[Side] > 0.f)
		{
			const FVector Current = World.TransformPosition(FootCS.GetLocation());
			LockDelta = World.InverseTransformVector(FVector(LockedWorld[Side].X - Current.X, LockedWorld[Side].Y - Current.Y, 0)) * LockAlpha[Side];
			const double Length = (CalfCS.GetLocation() - ThighCS.GetLocation()).Size() + (FootCS.GetLocation() - CalfCS.GetLocation()).Size();
			const FVector Lift = World.InverseTransformVector(FVector(0, 0, Correction[Side]));
			// A recovery can outgrow the plant envelope. Project onto it instead of resetting
			// a 15 cm correction in one frame; the foot yields continuously until normal release.
			LockDelta = LockDelta.GetClampedToMaxSize(15.f);
			const FVector BaseReach = FootCS.GetLocation() + Lift - ThighCS.GetLocation();
			if ((BaseReach + LockDelta).Size() > Length * 0.999)
			{
				float Low = 0.f, High = 1.f;
				for (int32 Iteration = 0; Iteration < 12; ++Iteration)
				{
					const float Midpoint = (Low + High) * 0.5f;
					if ((BaseReach + LockDelta * Midpoint).Size() <= Length * 0.999) Low = Midpoint;
					else High = Midpoint;
				}
				LockDelta *= Low;
			}
		}
		if (!LockDelta.IsNearlyZero())
		{
			// A horizontal plant on sloping ground changes the height needed by the boot.
			// Measure at its final locked position, not only at the incoming animation position.
			const FVector WorldLockDelta = World.TransformVector(LockDelta);
			for (const FRACSoleSample& Sample : Samples)
			{
				if (Sample.Side != Side || Ground[Side].IsEmpty()) continue;
				FVector Point = FVector::ZeroVector;
				for (const FRACSoleInfluence& Influence : Sample.Influences)
					Point += Output.Pose.GetComponentSpaceTransform(Influence.Bone.GetCompactPoseIndex(Bones)).TransformPosition(Influence.Point) * Influence.Weight;
				Point = World.TransformPosition(Point) + WorldLockDelta;
				const FGroundPlane* Nearest = &Ground[Side][0];
				for (const FGroundPlane& Plane : Ground[Side])
					if (FVector::DistSquaredXY(Point, Plane.Query) < FVector::DistSquaredXY(Point, Nearest->Query)) Nearest = &Plane;
				const float FloorZ = Nearest->Point.Z - (Nearest->Normal.X * (Point.X - Nearest->Point.X)
					+ Nearest->Normal.Y * (Point.Y - Nearest->Point.Y)) / Nearest->Normal.Z;
				Correction[Side] = FMath::Clamp(FMath::Max(Correction[Side], static_cast<float>(FloorZ + Clearance - Point.Z)), 0.f, MaxCorrection);
			}
		}
		if (Correction[Side] < 0.001f && LockDelta.IsNearlyZero()) continue;
		const FQuat Rotation = FootCS.GetRotation();
		const FVector Mid = 0.5f * (ThighCS.GetLocation() + FootCS.GetLocation());
		const FVector Pole = CalfCS.GetLocation() + (CalfCS.GetLocation() - Mid).GetSafeNormal() * 50.f;
		const FVector TargetFoot = FootCS.GetLocation() + LockDelta + World.InverseTransformVector(FVector(0, 0, Correction[Side]));
		AnimationCore::SolveTwoBoneIK(ThighCS, CalfCS, FootCS, Pole, TargetFoot, false, 1.f, 1.f);
		FootCS.SetRotation(Rotation);
		OutBoneTransforms.Add(FBoneTransform(Thigh, ThighCS));
		OutBoneTransforms.Add(FBoneTransform(Calf, CalfCS));
		OutBoneTransforms.Add(FBoneTransform(Foot, FootCS));
		OutBoneTransforms.Add(FBoneTransform(Chains[Side][3].GetCompactPoseIndex(Bones), FootCS));
	}
	OutBoneTransforms.Sort(FCompareBoneTransformIndex());
}
