"""
Lead scoring service
"""
from datetime import datetime
from typing import Dict, Any

import structlog
from sqlalchemy import select, and_, func

from src.database.connection import get_session
from src.database.models import Lead, LeadStatus, Conversation, Appointment

logger = structlog.get_logger()


class LeadScoringService:
    """
    Service for calculating lead scores based on various factors
    """

    # Scoring weights
    WEIGHTS = {
        "has_name": 5,
        "has_email": 10,
        "has_budget": 15,
        "has_preferences": 10,
        "recent_contact": 20,
        "multiple_conversations": 15,
        "appointment_scheduled": 25,
        "high_engagement": 20,
        "qualified_status": 30,
        "source_quality": 10
    }

    async def calculate_score(self, lead: Lead) -> int:
        """
        Calculate lead score based on various factors
        
        Returns score between 0-100
        """
        score = 0
        factors = {}

        # Basic information completeness
        if lead.name:
            score += self.WEIGHTS["has_name"]
            factors["has_name"] = True

        if lead.email:
            score += self.WEIGHTS["has_email"]
            factors["has_email"] = True

        # Budget information
        if lead.budget_min or lead.budget_max:
            score += self.WEIGHTS["has_budget"]
            factors["has_budget"] = True

        # Preferences defined
        if lead.preferences and len(lead.preferences) > 0:
            score += self.WEIGHTS["has_preferences"]
            factors["has_preferences"] = True

        # Recent contact (within last 7 days)
        if lead.last_contact_at:
            days_since_contact = (datetime.utcnow() - lead.last_contact_at).days
            if days_since_contact <= 7:
                score += self.WEIGHTS["recent_contact"]
                factors["recent_contact"] = True
            elif days_since_contact <= 14:
                score += self.WEIGHTS["recent_contact"] // 2
                factors["recent_contact_partial"] = True

        # Get engagement metrics
        async with get_session() as session:
            # Count conversations
            conversation_count = await session.scalar(
                select(func.count(Conversation.id)).where(
                    Conversation.lead_id == lead.id
                )
            )

            if conversation_count >= 2:
                score += self.WEIGHTS["multiple_conversations"]
                factors["multiple_conversations"] = True
            elif conversation_count == 1:
                score += self.WEIGHTS["multiple_conversations"] // 2
                factors["single_conversation"] = True

            # Check for appointments
            appointment_count = await session.scalar(
                select(func.count(Appointment.id)).where(
                    Appointment.lead_id == lead.id
                )
            )

            if appointment_count > 0:
                score += self.WEIGHTS["appointment_scheduled"]
                factors["appointment_scheduled"] = True

            # Check engagement level (messages in conversations)
            if conversation_count > 0:
                # This is a simplified check - in production, you'd count messages
                score += self.WEIGHTS["high_engagement"] // 2
                factors["some_engagement"] = True

        # Status-based scoring
        if lead.status == LeadStatus.QUALIFIED:
            score += self.WEIGHTS["qualified_status"]
            factors["qualified_status"] = True
        elif lead.status == LeadStatus.CONTACTED:
            score += self.WEIGHTS["qualified_status"] // 2
            factors["contacted_status"] = True

        # Source quality
        high_quality_sources = ["website", "referral", "agent"]
        if lead.source in high_quality_sources:
            score += self.WEIGHTS["source_quality"]
            factors["high_quality_source"] = True

        # Ensure score is within bounds
        score = min(100, max(0, score))

        # Store scoring factors
        lead.score_factors = factors

        logger.info(
            f"Calculated lead score",
            lead_id=str(lead.id),
            score=score,
            factors=factors
        )

        return score

    async def update_all_scores(self, tenant_id: str):
        """
        Update scores for all leads of a tenant
        """
        async with get_session() as session:
            stmt = select(Lead).where(Lead.tenant_id == tenant_id)
            result = await session.execute(stmt)
            leads = result.scalars().all()

            updated_count = 0
            for lead in leads:
                old_score = lead.score
                new_score = await self.calculate_score(lead)

                if old_score != new_score:
                    lead.score = new_score
                    updated_count += 1

            await session.commit()

            logger.info(
                f"Updated lead scores",
                tenant_id=tenant_id,
                total_leads=len(leads),
                updated_count=updated_count
            )

    def get_score_interpretation(self, score: int) -> Dict[str, Any]:
        """
        Get interpretation of lead score
        """
        if score >= 80:
            return {
                "category": "hot",
                "label": "Hot Lead",
                "color": "#FF4444",
                "priority": "high",
                "recommended_action": "Contact immediately"
            }
        elif score >= 60:
            return {
                "category": "warm",
                "label": "Warm Lead",
                "color": "#FF8800",
                "priority": "medium",
                "recommended_action": "Follow up within 24 hours"
            }
        elif score >= 40:
            return {
                "category": "cool",
                "label": "Cool Lead",
                "color": "#4488FF",
                "priority": "low",
                "recommended_action": "Nurture with automated content"
            }
        else:
            return {
                "category": "cold",
                "label": "Cold Lead",
                "color": "#888888",
                "priority": "minimal",
                "recommended_action": "Add to long-term nurture campaign"
            }
