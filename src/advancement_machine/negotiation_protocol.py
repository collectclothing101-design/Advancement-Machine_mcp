"""
Autonomous Negotiation Protocol.

Enables agents to bargain for resources, trade capabilities, and
distribute workloads through structured negotiation rounds.

Uses alternating-offer bargaining with concession modeling.
"""
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

class NegotiationPhase(Enum):
    OPENING = "opening"
    BARGAINING = "bargaining"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"

@dataclass
class Offer:
    offer_id: str
    proposer: str
    target: str
    resource_type: str
    offered_quantity: float
    requested_quantity: float
    concessions: List[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

@dataclass
class Negotiation:
    negotiation_id: str
    initiator: str
    responder: str
    resource_type: str
    phase: NegotiationPhase = NegotiationPhase.OPENING
    offers: List[Offer] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    concluded_at: Optional[float] = None

class NegotiationProtocol:
    """Full negotiation lifecycle: offer, counter-offer, concession,
    acceptance, rejection, withdrawal. Uses alternating-offer protocol."""

    def __init__(self, max_rounds: int = 10, time_limit: float = 300):
        self.negotiations: Dict[str, Negotiation] = {}
        self._max_rounds = max_rounds
        self._time_limit = time_limit

    def initiate(self, initiator: str, responder: str, resource_type: str,
                 offered_quantity: float, requested_quantity: float) -> dict:
        """Start a new negotiation with an opening offer."""
        neg_id = hashlib.md5(f"{initiator}:{responder}:{resource_type}:{time.time()}".encode()).hexdigest()[:12]
        neg = Negotiation(
            negotiation_id=neg_id,
            initiator=initiator,
            responder=responder,
            resource_type=resource_type,
        )
        offer = Offer(
            offer_id=f"{neg_id}_o0",
            proposer=initiator,
            target=responder,
            resource_type=resource_type,
            offered_quantity=offered_quantity,
            requested_quantity=requested_quantity,
        )
        neg.offers.append(offer)
        self.negotiations[neg_id] = neg
        logger.info(f"Negotiation {neg_id}: {initiator} -> {responder} for {resource_type}")
        return self._status(neg)

    def counter(self, negotiation_id: str, proposer: str,
                offered_quantity: float, requested_quantity: float,
                concessions: List[str] = None) -> dict:
        """Make a counter-offer in an existing negotiation."""
        neg = self.negotiations.get(negotiation_id)
        if not neg:
            return {"error": "Negotiation not found"}
        if neg.phase != NegotiationPhase.OPENING and neg.phase != NegotiationPhase.BARGAINING:
            return {"error": f"Negotiation is in phase {neg.phase.value}, cannot counter"}
        if len(neg.offers) >= self._max_rounds:
            return {"error": f"Max rounds ({self._max_rounds}) reached"}

        offer = Offer(
            offer_id=f"{negotiation_id}_o{len(neg.offers)}",
            proposer=proposer,
            target=neg.initiator if proposer == neg.responder else neg.responder,
            resource_type=neg.resource_type,
            offered_quantity=offered_quantity,
            requested_quantity=requested_quantity,
            concessions=concessions or [],
        )
        neg.offers.append(offer)
        neg.phase = NegotiationPhase.BARGAINING
        logger.info(f"Counter-offer {offer.offer_id}: {proposer} offers {offered_quantity} requests {requested_quantity}")
        return self._status(neg)

    def accept(self, negotiation_id: str, acceptor: str) -> dict:
        """Accept the latest offer."""
        neg = self.negotiations.get(negotiation_id)
        if not neg:
            return {"error": "Negotiation not found"}
        if not neg.offers:
            return {"error": "No offers to accept"}
        neg.phase = NegotiationPhase.ACCEPTED
        neg.concluded_at = time.time()
        final_offer = neg.offers[-1]
        logger.info(f"Negotiation {negotiation_id} ACCEPTED: {final_offer.proposer} provides {final_offer.offered_quantity} for {final_offer.requested_quantity}")
        return self._status(neg)

    def reject(self, negotiation_id: str) -> dict:
        """Reject the negotiation outright."""
        neg = self.negotiations.get(negotiation_id)
        if not neg:
            return {"error": "Negotiation not found"}
        neg.phase = NegotiationPhase.REJECTED
        neg.concluded_at = time.time()
        logger.info(f"Negotiation {negotiation_id} REJECTED")
        return self._status(neg)

    def withdraw(self, negotiation_id: str, party: str) -> dict:
        """Withdraw from a negotiation."""
        neg = self.negotiations.get(negotiation_id)
        if not neg:
            return {"error": "Negotiation not found"}
        neg.phase = NegotiationPhase.WITHDRAWN
        neg.concluded_at = time.time()
        logger.info(f"Negotiation {negotiation_id} WITHDRAWN by {party}")
        return self._status(neg)

    def auto_counter(self, negotiation_id: str, responder: str,
                     concession_rate: float = 0.1) -> dict:
        """Automatically generate a counter-offer using concession modeling.

        Concession rate determines how much the responder moves toward
        the initiator's position per round.
        """
        neg = self.negotiations.get(negotiation_id)
        if not neg:
            return {"error": "Negotiation not found"}

        last_offer = neg.offers[-1] if neg.offers else None
        if not last_offer:
            return {"error": "No previous offer"}

        # Model concession: move toward the midpoint
        offered = last_offer.offered_quantity
        requested = last_offer.requested_quantity
        midpoint = (offered + requested) / 2

        new_offered = offered + (midpoint - offered) * concession_rate
        new_requested = requested + (midpoint - requested) * concession_rate

        return self.counter(negotiation_id, responder, new_offered, new_requested,
                           concessions=["automated concession"])

    def _status(self, neg: Negotiation) -> dict:
        last_offer = neg.offers[-1] if neg.offers else None
        return {
            "negotiation_id": neg.negotiation_id,
            "phase": neg.phase.value,
            "round": len(neg.offers),
            "initiator": neg.initiator,
            "responder": neg.responder,
            "resource_type": neg.resource_type,
            "last_offer": {
                "proposer": last_offer.proposer,
                "offered": last_offer.offered_quantity,
                "requested": last_offer.requested_quantity,
                "concessions": last_offer.concessions,
            } if last_offer else None,
            "elapsed_seconds": round(time.time() - neg.started_at, 1),
        }

    def list_active(self) -> List[dict]:
        return [self._status(n) for n in self.negotiations.values()
                if n.phase in (NegotiationPhase.OPENING, NegotiationPhase.BARGAINING)]

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        return [
            {
                "name": "negotiate_initiate",
                "description": "Start a new negotiation with another agent",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "initiator": {"type": "string"},
                        "responder": {"type": "string"},
                        "resource_type": {"type": "string"},
                        "offered_quantity": {"type": "number"},
                        "requested_quantity": {"type": "number"},
                    },
                    "required": ["initiator", "responder", "resource_type", "offered_quantity", "requested_quantity"],
                },
            },
            {
                "name": "negotiate_counter",
                "description": "Make a counter-offer in a negotiation",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "negotiation_id": {"type": "string"},
                        "proposer": {"type": "string"},
                        "offered_quantity": {"type": "number"},
                        "requested_quantity": {"type": "number"},
                        "concessions": {"type": "array", "items": {"type": "string"}, "default": []},
                    },
                    "required": ["negotiation_id", "proposer", "offered_quantity", "requested_quantity"],
                },
            },
            {
                "name": "negotiate_auto_counter",
                "description": "Auto-generate a counter-offer using concession modeling",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "negotiation_id": {"type": "string"},
                        "responder": {"type": "string"},
                        "concession_rate": {"type": "number", "default": 0.1},
                    },
                    "required": ["negotiation_id", "responder"],
                },
            },
            {
                "name": "negotiate_accept",
                "description": "Accept the current offer",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "negotiation_id": {"type": "string"},
                        "acceptor": {"type": "string"},
                    },
                    "required": ["negotiation_id", "acceptor"],
                },
            },
            {
                "name": "negotiate_list_active",
                "description": "List all active negotiations",
                "inputSchema": {"type": "object", "properties": {}},
            },
        ]