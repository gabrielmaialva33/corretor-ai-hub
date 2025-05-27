"""
Property matching service for lead-property recommendations
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple

import structlog
from jinja2 import Template
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload

from src.database.connection import get_session
from src.database.models import (
    Lead, Property, Tenant, PropertyType, PropertyStatus
)
from src.integrations.evo_api import EvoAPIClient
from src.services.notification_service import NotificationService

logger = structlog.get_logger()


class PropertyMatcher:
    """
    Service for matching leads with suitable properties
    """

    # Matching weight factors
    WEIGHT_FACTORS = {
        "price_match": 0.30,  # 30% - Price within budget
        "location_match": 0.25,  # 25% - Location preferences
        "type_match": 0.20,  # 20% - Property type match
        "size_match": 0.15,  # 15% - Size/rooms match
        "features_match": 0.10  # 10% - Features/amenities match
    }

    # Notification template
    PROPERTY_MATCH_TEMPLATE = Template("""
🏠 *Novos imóveis que podem interessar ao cliente*

*Cliente*: {{ lead_name }}
📱 *Telefone*: {{ lead_phone }}
{% if lead_email %}📧 *Email*: {{ lead_email }}{% endif %}

*Preferências do cliente*:
{% if budget_range %}💰 Orçamento: {{ budget_range }}{% endif %}
{% if locations %}📍 Localizações: {{ locations }}{% endif %}
{% if property_types %}🏢 Tipos: {{ property_types }}{% endif %}
{% if bedrooms %}🛏️ Quartos: {{ bedrooms }}{% endif %}

*Imóveis correspondentes*:
{% for property in matching_properties %}
{{ loop.index }}. *{{ property.title }}*
   💰 {{ property.price_formatted }}
   📍 {{ property.location }}
   🔗 {{ property.url }}
   📊 Compatibilidade: {{ property.match_score }}%
   
{% endfor %}

💡 *Ação sugerida*: Entre em contato com o cliente para apresentar estas opções!
    """)

    async def find_matching_properties(
            self,
            lead_id: str,
            limit: int = 10,
            min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find properties matching lead preferences
        
        Args:
            lead_id: Lead ID
            limit: Maximum number of matches to return
            min_score: Minimum matching score (0-1)
            
        Returns:
            List of matching properties with scores
        """
        try:
            async with get_session() as session:
                # Get lead with preferences
                stmt = select(Lead).where(Lead.id == lead_id)
                result = await session.execute(stmt)
                lead = result.scalar_one_or_none()

                if not lead:
                    logger.error(f"Lead not found: {lead_id}")
                    return []

                # Get available properties for the same tenant
                properties_stmt = select(Property).where(
                    and_(
                        Property.tenant_id == lead.tenant_id,
                        Property.status == PropertyStatus.AVAILABLE,
                        Property.is_active == True
                    )
                )
                properties_result = await session.execute(properties_stmt)
                properties = properties_result.scalars().all()

                # Calculate match scores
                matches = []
                for property in properties:
                    score, breakdown = self._calculate_match_score(lead, property)

                    if score >= min_score:
                        matches.append({
                            "property": property,
                            "score": score,
                            "breakdown": breakdown
                        })

                # Sort by score descending
                matches.sort(key=lambda x: x["score"], reverse=True)

                # Return top matches
                return matches[:limit]

        except Exception as e:
            logger.error("Error finding matching properties", error=str(e))
            return []

    def _calculate_match_score(
            self,
            lead: Lead,
            property: Property
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calculate match score between lead and property
        
        Args:
            lead: Lead with preferences
            property: Property to match
            
        Returns:
            Tuple of (total_score, score_breakdown)
        """
        scores = {}

        # Price match
        scores["price_match"] = self._calculate_price_match(lead, property)

        # Location match
        scores["location_match"] = self._calculate_location_match(lead, property)

        # Property type match
        scores["type_match"] = self._calculate_type_match(lead, property)

        # Size match (bedrooms, area)
        scores["size_match"] = self._calculate_size_match(lead, property)

        # Features match
        scores["features_match"] = self._calculate_features_match(lead, property)

        # Calculate weighted total
        total_score = sum(
            scores[factor] * weight
            for factor, weight in self.WEIGHT_FACTORS.items()
        )

        return total_score, scores

    def _calculate_price_match(self, lead: Lead, property: Property) -> float:
        """Calculate price matching score (0-1)"""
        if not property.price:
            return 0.5  # Neutral if no price

        # If lead has no budget preference, give neutral score
        if not lead.budget_min and not lead.budget_max:
            return 0.7

        # Check if price is within budget
        if lead.budget_min and property.price < lead.budget_min:
            # Under budget - calculate how far under
            ratio = property.price / lead.budget_min
            return max(0, ratio)  # Linear decrease as price gets lower

        if lead.budget_max and property.price > lead.budget_max:
            # Over budget - calculate how far over
            ratio = lead.budget_max / property.price
            return max(0, ratio)  # Linear decrease as price gets higher

        # Within budget - perfect match
        return 1.0

    def _calculate_location_match(self, lead: Lead, property: Property) -> float:
        """Calculate location matching score (0-1)"""
        if not lead.preferred_locations:
            return 0.7  # Neutral if no preference

        # Check exact matches first
        property_locations = [
            property.neighborhood,
            property.city,
            property.address
        ]

        for pref_location in lead.preferred_locations:
            pref_lower = pref_location.lower()
            for prop_location in property_locations:
                if prop_location and pref_lower in prop_location.lower():
                    return 1.0

        # No exact match
        return 0.0

    def _calculate_type_match(self, lead: Lead, property: Property) -> float:
        """Calculate property type matching score (0-1)"""
        if not lead.property_type_interest:
            return 0.7  # Neutral if no preference

        # Direct match
        if property.property_type in lead.property_type_interest:
            return 1.0

        # Similar types
        similar_types = {
            PropertyType.HOUSE: [PropertyType.CONDO],
            PropertyType.APARTMENT: [PropertyType.STUDIO, PropertyType.LOFT],
            PropertyType.STUDIO: [PropertyType.APARTMENT, PropertyType.LOFT]
        }

        for pref_type in lead.property_type_interest:
            if property.property_type in similar_types.get(pref_type, []):
                return 0.7  # Partial match for similar types

        return 0.0

    def _calculate_size_match(self, lead: Lead, property: Property) -> float:
        """Calculate size matching score (0-1)"""
        scores = []

        # Bedroom match
        if "bedrooms" in lead.preferences:
            desired_bedrooms = lead.preferences["bedrooms"]
            if property.bedrooms:
                if property.bedrooms == desired_bedrooms:
                    scores.append(1.0)
                elif abs(property.bedrooms - desired_bedrooms) == 1:
                    scores.append(0.7)  # One bedroom difference
                else:
                    scores.append(0.3)  # More than one bedroom difference

        # Area match
        if "min_area" in lead.preferences or "max_area" in lead.preferences:
            min_area = lead.preferences.get("min_area", 0)
            max_area = lead.preferences.get("max_area", float('inf'))

            if property.area:
                if min_area <= property.area <= max_area:
                    scores.append(1.0)
                elif property.area < min_area:
                    ratio = property.area / min_area
                    scores.append(max(0, ratio))
                else:  # property.area > max_area
                    ratio = max_area / property.area
                    scores.append(max(0, ratio))

        # Return average of size scores
        return sum(scores) / len(scores) if scores else 0.7

    def _calculate_features_match(self, lead: Lead, property: Property) -> float:
        """Calculate features matching score (0-1)"""
        if "desired_features" not in lead.preferences:
            return 0.7  # Neutral if no preference

        desired_features = set(lead.preferences["desired_features"])
        property_features = set(property.features + property.amenities)

        if not desired_features:
            return 0.7

        # Calculate overlap
        matching_features = desired_features.intersection(property_features)
        match_ratio = len(matching_features) / len(desired_features)

        return match_ratio

    async def run_weekly_matching(
            self,
            tenant_id: str,
            property_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Run weekly matching process for a tenant
        
        Args:
            tenant_id: Tenant ID
            property_ids: Optional list of specific property IDs to match
            
        Returns:
            Matching results summary
        """
        try:
            async with get_session() as session:
                # Get tenant
                tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
                tenant_result = await session.execute(tenant_stmt)
                tenant = tenant_result.scalar_one_or_none()

                if not tenant:
                    logger.error(f"Tenant not found: {tenant_id}")
                    return {"error": "Tenant not found"}

                # Get active leads with preferences
                leads_stmt = select(Lead).where(
                    and_(
                        Lead.tenant_id == tenant_id,
                        Lead.status.in_(["new", "contacted", "qualified"]),
                        or_(
                            Lead.budget_max.isnot(None),
                            Lead.preferred_locations != [],
                            Lead.property_type_interest != []
                        )
                    )
                )
                leads_result = await session.execute(leads_stmt)
                leads = leads_result.scalars().all()

                # Get properties to match
                if property_ids:
                    properties_stmt = select(Property).where(
                        and_(
                            Property.tenant_id == tenant_id,
                            Property.id.in_(property_ids),
                            Property.status == PropertyStatus.AVAILABLE
                        )
                    )
                else:
                    # Get properties added in the last week
                    week_ago = datetime.utcnow() - timedelta(days=7)
                    properties_stmt = select(Property).where(
                        and_(
                            Property.tenant_id == tenant_id,
                            Property.status == PropertyStatus.AVAILABLE,
                            Property.created_at >= week_ago
                        )
                    )

                properties_result = await session.execute(properties_stmt)
                properties = properties_result.scalars().all()

                # Run matching
                total_matches = 0
                notifications_sent = 0

                for lead in leads:
                    lead_matches = []

                    for property in properties:
                        score, breakdown = self._calculate_match_score(lead, property)

                        if score >= 0.7:  # Minimum 70% match
                            lead_matches.append({
                                "property": property,
                                "score": score,
                                "breakdown": breakdown
                            })

                    if lead_matches:
                        # Sort by score
                        lead_matches.sort(key=lambda x: x["score"], reverse=True)

                        # Send notification to corretor
                        await self._send_match_notification(
                            tenant,
                            lead,
                            lead_matches[:5]  # Top 5 matches
                        )

                        total_matches += len(lead_matches)
                        notifications_sent += 1

                return {
                    "success": True,
                    "leads_analyzed": len(leads),
                    "properties_analyzed": len(properties),
                    "total_matches": total_matches,
                    "notifications_sent": notifications_sent,
                    "timestamp": datetime.utcnow().isoformat()
                }

        except Exception as e:
            logger.error("Error running weekly matching", error=str(e))
            return {
                "success": False,
                "error": str(e)
            }

    async def _send_match_notification(
            self,
            tenant: Tenant,
            lead: Lead,
            matches: List[Dict[str, Any]]
    ):
        """Send property match notification to corretor"""
        try:
            # Prepare template data
            template_data = {
                "lead_name": lead.name or "Sem nome",
                "lead_phone": lead.phone,
                "lead_email": lead.email,
                "budget_range": self._format_budget_range(lead),
                "locations": ", ".join(lead.preferred_locations) if lead.preferred_locations else None,
                "property_types": self._format_property_types(lead),
                "bedrooms": lead.preferences.get("bedrooms"),
                "matching_properties": []
            }

            # Format matching properties
            for match in matches:
                property = match["property"]
                template_data["matching_properties"].append({
                    "title": property.title,
                    "price_formatted": self._format_price(property.price),
                    "location": f"{property.neighborhood}, {property.city}" if property.neighborhood else property.city,
                    "url": property.source_url or "#",
                    "match_score": round(match["score"] * 100)
                })

            # Render message
            message = self.PROPERTY_MATCH_TEMPLATE.render(**template_data)

            # Send via WhatsApp if configured
            if tenant.evo_instance_key and tenant.phone:
                async with EvoAPIClient(tenant.evo_instance_key) as evo_client:
                    await evo_client.send_text_message(
                        to=tenant.phone,
                        message=message
                    )

            # Also send via internal notification system
            notification_service = NotificationService()
            await notification_service.create_notification(
                tenant_id=str(tenant.id),
                type="property_match",
                title=f"Novos imóveis para {lead.name or 'cliente'}",
                message=message,
                data={
                    "lead_id": str(lead.id),
                    "match_count": len(matches)
                }
            )

        except Exception as e:
            logger.error("Error sending match notification", error=str(e))

    def _format_budget_range(self, lead: Lead) -> Optional[str]:
        """Format budget range for display"""
        if not lead.budget_min and not lead.budget_max:
            return None

        if lead.budget_min and lead.budget_max:
            return f"R$ {lead.budget_min:,.0f} - R$ {lead.budget_max:,.0f}"
        elif lead.budget_min:
            return f"A partir de R$ {lead.budget_min:,.0f}"
        else:
            return f"Até R$ {lead.budget_max:,.0f}"

    def _format_property_types(self, lead: Lead) -> Optional[str]:
        """Format property types for display"""
        if not lead.property_type_interest:
            return None

        type_names = {
            PropertyType.HOUSE: "Casa",
            PropertyType.APARTMENT: "Apartamento",
            PropertyType.CONDO: "Condomínio",
            PropertyType.STUDIO: "Studio",
            PropertyType.LOFT: "Loft",
            PropertyType.COMMERCIAL: "Comercial",
            PropertyType.LAND: "Terreno",
            PropertyType.OTHER: "Outro"
        }

        return ", ".join([
            type_names.get(ptype, ptype.value)
            for ptype in lead.property_type_interest
        ])

    def _format_price(self, price: float) -> str:
        """Format price for display"""
        if price >= 1000000:
            return f"R$ {price / 1000000:.1f}M"
        elif price >= 1000:
            return f"R$ {price / 1000:.0f}K"
        else:
            return f"R$ {price:,.0f}"

    async def find_leads_for_property(
            self,
            property_id: str,
            limit: int = 20,
            min_score: float = 0.7
    ) -> List[Dict[str, Any]]:
        """
        Find leads that might be interested in a specific property
        
        Args:
            property_id: Property ID
            limit: Maximum number of leads to return
            min_score: Minimum matching score
            
        Returns:
            List of matching leads with scores
        """
        try:
            async with get_session() as session:
                # Get property
                property_stmt = select(Property).where(Property.id == property_id)
                property_result = await session.execute(property_stmt)
                property = property_result.scalar_one_or_none()

                if not property:
                    logger.error(f"Property not found: {property_id}")
                    return []

                # Get active leads for the same tenant
                leads_stmt = select(Lead).where(
                    and_(
                        Lead.tenant_id == property.tenant_id,
                        Lead.status.in_(["new", "contacted", "qualified"])
                    )
                )
                leads_result = await session.execute(leads_stmt)
                leads = leads_result.scalars().all()

                # Calculate match scores
                matches = []
                for lead in leads:
                    score, breakdown = self._calculate_match_score(lead, property)

                    if score >= min_score:
                        matches.append({
                            "lead": lead,
                            "score": score,
                            "breakdown": breakdown
                        })

                # Sort by score descending
                matches.sort(key=lambda x: x["score"], reverse=True)

                # Return top matches
                return matches[:limit]

        except Exception as e:
            logger.error("Error finding leads for property", error=str(e))
            return []
