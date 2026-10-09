"""ProofFlow Canonical Event Taxonomy (18-Class) and Mapping Engine.

Defines the approved 18 canonical event types across Commerce, Order/Delivery,
and Communication categories, alongside formal classifications and mapping rules
for compatibility aliases, legacy labels, and dispute claims.
"""

from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class TaxonomyLabelCategory(str, Enum):
    CANONICAL = "CANONICAL"
    COMPATIBILITY_ALIAS = "COMPATIBILITY_ALIAS"
    LEGACY_DISPUTE = "LEGACY_DISPUTE"
    UNCLEAR = "UNCLEAR"
    NEGATIVE_SAMPLE = "NEGATIVE_SAMPLE"


# Approved ProofFlow Canonical 18 Event Types
CANONICAL_COMMERCE_EVENTS: List[str] = [
    "ORDER_PLACED",
    "PAYMENT_MADE",
    "PAYMENT_FAILED",
    "REFUND_REQUESTED",
    "REFUND_INITIATED",
    "REFUND_COMPLETED",
    "REFUND_FAILED",
]

CANONICAL_ORDER_DELIVERY_EVENTS: List[str] = [
    "ORDER_CANCELLED",
    "ITEM_SHIPPED",
    "DELIVERY_ATTEMPTED",
    "ITEM_DELIVERED",
    "RETURN_REQUESTED",
    "RETURN_PICKED_UP",
    "RETURN_COMPLETED",
]

CANONICAL_COMMUNICATION_EVENTS: List[str] = [
    "MESSAGE_SENT",
    "MESSAGE_RECEIVED",
    "SUPPORT_CONTACTED",
    "SUPPORT_RESPONSE",
]

CANONICAL_18_EVENT_TYPES: List[str] = (
    CANONICAL_COMMERCE_EVENTS
    + CANONICAL_ORDER_DELIVERY_EVENTS
    + CANONICAL_COMMUNICATION_EVENTS
)

CANONICAL_18_SET: Set[str] = set(CANONICAL_18_EVENT_TYPES)


class TaxonomyMappingRule(BaseModel):
    """Specification of how a raw or legacy label maps to the canonical taxonomy."""

    raw_label: str
    category: TaxonomyLabelCategory
    canonical_event_type: Optional[str] = None
    is_canonical: bool = False
    justification: str
    recommended_training_action: str


# Full Taxonomy Mapping Directory for all 28 existing labels in ProofFlow
TAXONOMY_MAPPINGS: Dict[str, TaxonomyMappingRule] = {
    # --- 18 CANONICAL EVENT TYPES ---
    # Commerce
    "ORDER_PLACED": TaxonomyMappingRule(
        raw_label="ORDER_PLACED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="ORDER_PLACED",
        is_canonical=True,
        justification="Approved canonical commerce event representing order placement or confirmation.",
        recommended_training_action="Direct canonical training target.",
    ),
    "PAYMENT_MADE": TaxonomyMappingRule(
        raw_label="PAYMENT_MADE",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="PAYMENT_MADE",
        is_canonical=True,
        justification="Approved canonical commerce event representing successful debit or payment settlement.",
        recommended_training_action="Direct canonical training target.",
    ),
    "PAYMENT_FAILED": TaxonomyMappingRule(
        raw_label="PAYMENT_FAILED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="PAYMENT_FAILED",
        is_canonical=True,
        justification="Approved canonical commerce event representing payment rejection or failure.",
        recommended_training_action="Direct canonical training target.",
    ),
    "REFUND_REQUESTED": TaxonomyMappingRule(
        raw_label="REFUND_REQUESTED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="REFUND_REQUESTED",
        is_canonical=True,
        justification="Approved canonical commerce event representing customer claim or refund demand.",
        recommended_training_action="Direct canonical training target.",
    ),
    "REFUND_INITIATED": TaxonomyMappingRule(
        raw_label="REFUND_INITIATED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="REFUND_INITIATED",
        is_canonical=True,
        justification="Approved canonical commerce event representing refund processing start.",
        recommended_training_action="Direct canonical training target.",
    ),
    "REFUND_COMPLETED": TaxonomyMappingRule(
        raw_label="REFUND_COMPLETED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="REFUND_COMPLETED",
        is_canonical=True,
        justification="Approved canonical commerce event representing successful refund payout / ledger credit.",
        recommended_training_action="Direct canonical training target.",
    ),
    "REFUND_FAILED": TaxonomyMappingRule(
        raw_label="REFUND_FAILED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="REFUND_FAILED",
        is_canonical=True,
        justification="Approved canonical commerce event representing refund rejection or reversal failure.",
        recommended_training_action="Direct canonical training target.",
    ),
    # Order / Delivery
    "ORDER_CANCELLED": TaxonomyMappingRule(
        raw_label="ORDER_CANCELLED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="ORDER_CANCELLED",
        is_canonical=True,
        justification="Approved canonical delivery event representing order cancellation or voiding.",
        recommended_training_action="Direct canonical training target.",
    ),
    "ITEM_SHIPPED": TaxonomyMappingRule(
        raw_label="ITEM_SHIPPED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="ITEM_SHIPPED",
        is_canonical=True,
        justification="Approved canonical delivery event representing dispatch or handover to courier.",
        recommended_training_action="Direct canonical training target.",
    ),
    "DELIVERY_ATTEMPTED": TaxonomyMappingRule(
        raw_label="DELIVERY_ATTEMPTED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="DELIVERY_ATTEMPTED",
        is_canonical=True,
        justification="Approved canonical delivery event representing failed or attempted courier drop-off.",
        recommended_training_action="Direct canonical training target.",
    ),
    "ITEM_DELIVERED": TaxonomyMappingRule(
        raw_label="ITEM_DELIVERED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="ITEM_DELIVERED",
        is_canonical=True,
        justification="Approved canonical delivery event representing final receipt or verified parcel drop.",
        recommended_training_action="Direct canonical training target.",
    ),
    "RETURN_REQUESTED": TaxonomyMappingRule(
        raw_label="RETURN_REQUESTED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="RETURN_REQUESTED",
        is_canonical=True,
        justification="Approved canonical delivery event representing customer return or RMA request.",
        recommended_training_action="Direct canonical training target.",
    ),
    "RETURN_PICKED_UP": TaxonomyMappingRule(
        raw_label="RETURN_PICKED_UP",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="RETURN_PICKED_UP",
        is_canonical=True,
        justification="Approved canonical delivery event representing courier return item collection.",
        recommended_training_action="Direct canonical training target.",
    ),
    "RETURN_COMPLETED": TaxonomyMappingRule(
        raw_label="RETURN_COMPLETED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="RETURN_COMPLETED",
        is_canonical=True,
        justification="Approved canonical delivery event representing return item warehouse receipt / inspection.",
        recommended_training_action="Direct canonical training target.",
    ),
    # Communication
    "MESSAGE_SENT": TaxonomyMappingRule(
        raw_label="MESSAGE_SENT",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="MESSAGE_SENT",
        is_canonical=True,
        justification="Approved canonical communication event representing outbound message dispatch.",
        recommended_training_action="Direct canonical training target.",
    ),
    "MESSAGE_RECEIVED": TaxonomyMappingRule(
        raw_label="MESSAGE_RECEIVED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="MESSAGE_RECEIVED",
        is_canonical=True,
        justification="Approved canonical communication event representing inbound message receipt.",
        recommended_training_action="Direct canonical training target.",
    ),
    "SUPPORT_CONTACTED": TaxonomyMappingRule(
        raw_label="SUPPORT_CONTACTED",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="SUPPORT_CONTACTED",
        is_canonical=True,
        justification="Approved canonical communication event representing escalation or customer support ticket opening.",
        recommended_training_action="Direct canonical training target.",
    ),
    "SUPPORT_RESPONSE": TaxonomyMappingRule(
        raw_label="SUPPORT_RESPONSE",
        category=TaxonomyLabelCategory.CANONICAL,
        canonical_event_type="SUPPORT_RESPONSE",
        is_canonical=True,
        justification="Approved canonical communication event representing agent support reply or ticket update.",
        recommended_training_action="Direct canonical training target.",
    ),
    # --- 4 COMPATIBILITY ALIASES ---
    "ORDER_SHIPPED": TaxonomyMappingRule(
        raw_label="ORDER_SHIPPED",
        category=TaxonomyLabelCategory.COMPATIBILITY_ALIAS,
        canonical_event_type="ITEM_SHIPPED",
        is_canonical=True,
        justification="Direct synonym for package dispatch; maps cleanly to ITEM_SHIPPED.",
        recommended_training_action="Map to ITEM_SHIPPED with raw label preserved in sample provenance.",
    ),
    "ORDER_DELIVERED": TaxonomyMappingRule(
        raw_label="ORDER_DELIVERED",
        category=TaxonomyLabelCategory.COMPATIBILITY_ALIAS,
        canonical_event_type="ITEM_DELIVERED",
        is_canonical=True,
        justification="Direct synonym for package delivery; maps cleanly to ITEM_DELIVERED.",
        recommended_training_action="Map to ITEM_DELIVERED with raw label preserved in sample provenance.",
    ),
    "ITEM_RECEIVED": TaxonomyMappingRule(
        raw_label="ITEM_RECEIVED",
        category=TaxonomyLabelCategory.COMPATIBILITY_ALIAS,
        canonical_event_type="ITEM_DELIVERED",
        is_canonical=True,
        justification="Recipient confirmation of physical receipt is semantically equivalent to delivery completion.",
        recommended_training_action="Map to ITEM_DELIVERED with raw label preserved in sample provenance.",
    ),
    "RETURN_INITIATED": TaxonomyMappingRule(
        raw_label="RETURN_INITIATED",
        category=TaxonomyLabelCategory.COMPATIBILITY_ALIAS,
        canonical_event_type="RETURN_REQUESTED",
        is_canonical=True,
        justification="Buyer initiation of return workflow aligns with RETURN_REQUESTED.",
        recommended_training_action="Map to RETURN_REQUESTED with raw label preserved in sample provenance.",
    ),
    # --- 5 LEGACY / DISPUTE LABELS ---
    "REFUND_APPROVED": TaxonomyMappingRule(
        raw_label="REFUND_APPROVED",
        category=TaxonomyLabelCategory.LEGACY_DISPUTE,
        canonical_event_type=None,
        is_canonical=False,
        justification=(
            "Administrative authorization milestone prior to financial initiation. "
            "Forcing it to REFUND_INITIATED or REFUND_COMPLETED conflates authorization with execution."
        ),
        recommended_training_action=(
            "Preserve in dataset provenance as legacy label. Exclude from 18-class classifier loss "
            "or assign to auxiliary merchant approval workflow."
        ),
    ),
    "REFUND_PROCESSED": TaxonomyMappingRule(
        raw_label="REFUND_PROCESSED",
        category=TaxonomyLabelCategory.LEGACY_DISPUTE,
        canonical_event_type=None,
        is_canonical=False,
        justification=(
            "Gateway transfer execution step. Forcing to REFUND_INITIATED or REFUND_COMPLETED "
            "collapses distinct financial gateway states."
        ),
        recommended_training_action=(
            "Preserve in dataset provenance as legacy label. Exclude from 18-class classifier loss."
        ),
    ),
    "REFUND_RECEIVED": TaxonomyMappingRule(
        raw_label="REFUND_RECEIVED",
        category=TaxonomyLabelCategory.LEGACY_DISPUTE,
        canonical_event_type=None,
        is_canonical=False,
        justification=(
            "Customer credit receipt on bank statement. Collapsing into REFUND_COMPLETED "
            "blurs customer-side settlement verification with merchant ledger status."
        ),
        recommended_training_action=(
            "Preserve in dataset provenance as legacy label. Exclude from 18-class classifier loss."
        ),
    ),
    "DISPUTE_OPENED": TaxonomyMappingRule(
        raw_label="DISPUTE_OPENED",
        category=TaxonomyLabelCategory.LEGACY_DISPUTE,
        canonical_event_type=None,
        is_canonical=False,
        justification=(
            "Formal dispute/claim filing on payment platform. Governed by dispute resolution rules "
            "(Track 2 Claims), not standard 3-party commercial fulfillment/communication events."
        ),
        recommended_training_action=(
            "Preserve in dataset provenance as dispute domain label. Exclude from 18-class event classifier; "
            "train separately in Track 2 Claim/Dispute reasoning."
        ),
    ),
    "CHARGEBACK_REQUESTED": TaxonomyMappingRule(
        raw_label="CHARGEBACK_REQUESTED",
        category=TaxonomyLabelCategory.LEGACY_DISPUTE,
        canonical_event_type=None,
        is_canonical=False,
        justification=(
            "Cardholder bank chargeback demand. Legal card-network arbitration mechanism, "
            "semantically distinct from merchant refund or commercial payment events."
        ),
        recommended_training_action=(
            "Preserve in dataset provenance as dispute domain label. Exclude from 18-class event classifier; "
            "route to Track 2 Claim/Dispute reasoning."
        ),
    ),
    # --- NEGATIVE CONTRASTIVE CLASS ---
    "NO_EVENT": TaxonomyMappingRule(
        raw_label="NO_EVENT",
        category=TaxonomyLabelCategory.NEGATIVE_SAMPLE,
        canonical_event_type="NO_EVENT",
        is_canonical=True,
        justification="Negative non-event text to enforce non-event rejection in binary & multiclass heads.",
        recommended_training_action="Retained as explicit negative class (Class 19) in DeBERTa classifier.",
    ),
}


def map_to_canonical(label: str) -> Optional[str]:
    """Resolves any label to its canonical 18 target, or None if non-canonical/unmapped."""
    rule = TAXONOMY_MAPPINGS.get(label)
    if rule:
        return rule.canonical_event_type
    if label in CANONICAL_18_SET:
        return label
    return None


def is_canonical_event(label: str) -> bool:
    """Returns True if the label is one of the 18 approved canonical event types."""
    return label in CANONICAL_18_SET


def get_taxonomy_summary() -> Dict[str, Any]:
    """Returns a structured summary of the canonical taxonomy and all mapping classifications."""
    counts_by_cat: Dict[str, int] = {}
    for rule in TAXONOMY_MAPPINGS.values():
        counts_by_cat[rule.category.value] = counts_by_cat.get(rule.category.value, 0) + 1

    return {
        "canonical_classes_count": len(CANONICAL_18_EVENT_TYPES),
        "canonical_classes": CANONICAL_18_EVENT_TYPES,
        "total_labels_audited": len(TAXONOMY_MAPPINGS),
        "counts_by_category": counts_by_cat,
        "compatibility_aliases": {
            k: v.canonical_event_type
            for k, v in TAXONOMY_MAPPINGS.items()
            if v.category == TaxonomyLabelCategory.COMPATIBILITY_ALIAS
        },
        "unmapped_legacy_dispute": [
            k for k, v in TAXONOMY_MAPPINGS.items()
            if v.category == TaxonomyLabelCategory.LEGACY_DISPUTE
        ],
    }
