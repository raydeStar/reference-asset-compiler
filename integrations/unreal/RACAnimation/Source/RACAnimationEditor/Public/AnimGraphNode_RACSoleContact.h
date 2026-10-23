// SPDX-License-Identifier: MIT
#pragma once
#include "CoreMinimal.h"
#include "AnimGraphNode_SkeletalControlBase.h"
#include "AnimNode_RACSoleContact.h"
#include "AnimGraphNode_RACSoleContact.generated.h"

UCLASS()
class RACANIMATIONEDITOR_API UAnimGraphNode_RACSoleContact : public UAnimGraphNode_SkeletalControlBase
{
	GENERATED_BODY()
public:
	UPROPERTY(EditAnywhere, Category=Settings)
	FAnimNode_RACSoleContact Node;
	virtual FText GetNodeTitle(ENodeTitleType::Type TitleType) const override { return GetControllerDescription(); }
	virtual FText GetTooltipText() const override { return NSLOCTEXT("RACSoleContact", "Tooltip", "Grounded locomotion: measured boot samples stay above real collision after floor IK."); }
protected:
	virtual FText GetControllerDescription() const override { return NSLOCTEXT("RACSoleContact", "Title", "RAC Sole Contact"); }
	virtual const FAnimNode_SkeletalControlBase* GetNode() const override { return &Node; }
};
