"""
Tests for property matching service
"""
import pytest
from unittest.mock import AsyncMock, patch
from src.services.property_matcher import PropertyMatcher
from src.database.models import Lead, Property, Tenant, PropertyType, PropertyStatus


class TestPropertyMatcher:
    """Test property matching functionality"""
    
    @pytest.fixture
    def matcher(self):
        """Create matcher instance"""
        return PropertyMatcher()
    
    @pytest.fixture
    async def test_data(self, async_session):
        """Create test data for matching"""
        from src.database.models import Tenant, Lead, Property
        
        # Create tenant
        tenant = Tenant(
            name="Test Agent",
            email="test@example.com",
            phone="+5511999999999"
        )
        async_session.add(tenant)
        
        # Create leads with different preferences
        lead1 = Lead(
            tenant_id=tenant.id,
            name="Budget Conscious",
            phone="+5511111111111",
            budget_min=150000,
            budget_max=250000,
            preferred_locations=["Palermo", "Recoleta"],
            property_type_interest=[PropertyType.APARTMENT],
            preferences={"bedrooms": 2}
        )
        async_session.add(lead1)
        
        lead2 = Lead(
            tenant_id=tenant.id,
            name="Family Buyer",
            phone="+5511222222222",
            budget_min=300000,
            budget_max=500000,
            preferred_locations=["Belgrano"],
            property_type_interest=[PropertyType.HOUSE],
            preferences={"bedrooms": 4, "desired_features": ["garden", "garage"]}
        )
        async_session.add(lead2)
        
        # Create properties with different characteristics
        property1 = Property(
            tenant_id=tenant.id,
            title="Cozy Apartment in Palermo",
            price=200000,
            property_type=PropertyType.APARTMENT,
            bedrooms=2,
            bathrooms=1,
            area=80,
            neighborhood="Palermo",
            city="Buenos Aires",
            address="Av. Santa Fe 1234",
            features=["balcony", "gym"],
            status=PropertyStatus.AVAILABLE
        )
        async_session.add(property1)
        
        property2 = Property(
            tenant_id=tenant.id,
            title="Family House in Belgrano",
            price=450000,
            property_type=PropertyType.HOUSE,
            bedrooms=4,
            bathrooms=3,
            area=250,
            neighborhood="Belgrano",
            city="Buenos Aires",
            address="Cabildo 5678",
            features=["garden", "garage", "pool"],
            status=PropertyStatus.AVAILABLE
        )
        async_session.add(property2)
        
        property3 = Property(
            tenant_id=tenant.id,
            title="Studio in Recoleta",
            price=180000,
            property_type=PropertyType.STUDIO,
            bedrooms=1,
            bathrooms=1,
            area=45,
            neighborhood="Recoleta",
            city="Buenos Aires",
            address="Av. Callao 910",
            features=["furnished"],
            status=PropertyStatus.AVAILABLE
        )
        async_session.add(property3)
        
        await async_session.commit()
        
        return {
            "tenant": tenant,
            "leads": [lead1, lead2],
            "properties": [property1, property2, property3]
        }
    
    def test_calculate_price_match(self, matcher):
        """Test price matching calculation"""
        lead = Lead(budget_min=200000, budget_max=300000)
        
        # Perfect match
        property1 = Property(price=250000)
        score1 = matcher._calculate_price_match(lead, property1)
        assert score1 == 1.0
        
        # Under budget
        property2 = Property(price=150000)
        score2 = matcher._calculate_price_match(lead, property2)
        assert 0.5 < score2 < 1.0  # Should be 0.75
        
        # Over budget
        property3 = Property(price=400000)
        score3 = matcher._calculate_price_match(lead, property3)
        assert 0.5 < score3 < 1.0  # Should be 0.75
        
        # No budget preference
        lead_no_budget = Lead()
        property4 = Property(price=500000)
        score4 = matcher._calculate_price_match(lead_no_budget, property4)
        assert score4 == 0.7  # Neutral score
    
    def test_calculate_location_match(self, matcher):
        """Test location matching calculation"""
        lead = Lead(preferred_locations=["Palermo", "Recoleta"])
        
        # Exact match
        property1 = Property(neighborhood="Palermo", city="Buenos Aires")
        score1 = matcher._calculate_location_match(lead, property1)
        assert score1 == 1.0
        
        # No match
        property2 = Property(neighborhood="Belgrano", city="Buenos Aires")
        score2 = matcher._calculate_location_match(lead, property2)
        assert score2 == 0.0
        
        # Partial match (location in address)
        property3 = Property(address="Av. Santa Fe 1234, Recoleta", city="Buenos Aires")
        score3 = matcher._calculate_location_match(lead, property3)
        assert score3 == 1.0
        
        # No location preference
        lead_no_pref = Lead()
        score4 = matcher._calculate_location_match(lead_no_pref, property1)
        assert score4 == 0.7  # Neutral score
    
    def test_calculate_type_match(self, matcher):
        """Test property type matching calculation"""
        lead = Lead(property_type_interest=[PropertyType.APARTMENT, PropertyType.STUDIO])
        
        # Direct match
        property1 = Property(property_type=PropertyType.APARTMENT)
        score1 = matcher._calculate_type_match(lead, property1)
        assert score1 == 1.0
        
        # Similar type
        property2 = Property(property_type=PropertyType.LOFT)
        score2 = matcher._calculate_type_match(lead, property2)
        assert score2 == 0.7  # Similar to apartment/studio
        
        # No match
        property3 = Property(property_type=PropertyType.HOUSE)
        score3 = matcher._calculate_type_match(lead, property3)
        assert score3 == 0.0
    
    def test_calculate_size_match(self, matcher):
        """Test size matching calculation"""
        lead = Lead(preferences={"bedrooms": 3, "min_area": 100, "max_area": 150})
        
        # Perfect match
        property1 = Property(bedrooms=3, area=120)
        score1 = matcher._calculate_size_match(lead, property1)
        assert score1 == 1.0
        
        # One bedroom difference
        property2 = Property(bedrooms=2, area=110)
        score2 = matcher._calculate_size_match(lead, property2)
        assert 0.7 < score2 < 1.0
        
        # Area too small
        property3 = Property(bedrooms=3, area=80)
        score3 = matcher._calculate_size_match(lead, property3)
        assert 0.5 < score3 < 1.0
    
    def test_calculate_features_match(self, matcher):
        """Test features matching calculation"""
        lead = Lead(preferences={"desired_features": ["pool", "garage", "gym"]})
        
        # All features match
        property1 = Property(features=["pool", "garage", "gym", "garden"])
        score1 = matcher._calculate_features_match(lead, property1)
        assert score1 == 1.0
        
        # Partial match
        property2 = Property(features=["garage", "garden"])
        score2 = matcher._calculate_features_match(lead, property2)
        assert score2 == pytest.approx(0.33, 0.01)  # 1/3 features
        
        # No match
        property3 = Property(features=["balcony", "furnished"])
        score3 = matcher._calculate_features_match(lead, property3)
        assert score3 == 0.0
    
    @pytest.mark.asyncio
    async def test_find_matching_properties(self, matcher, test_data):
        """Test finding matching properties for a lead"""
        data = await test_data
        lead1 = data["leads"][0]  # Budget conscious lead
        
        matches = await matcher.find_matching_properties(
            str(lead1.id),
            limit=10,
            min_score=0.5
        )
        
        # Should find at least one match
        assert len(matches) > 0
        
        # Check match structure
        first_match = matches[0]
        assert "property" in first_match
        assert "score" in first_match
        assert "breakdown" in first_match
        
        # Score should be between 0 and 1
        assert 0 <= first_match["score"] <= 1
        
        # Breakdown should have all factors
        assert all(factor in first_match["breakdown"] for factor in matcher.WEIGHT_FACTORS)
    
    @pytest.mark.asyncio
    async def test_find_leads_for_property(self, matcher, test_data):
        """Test finding leads interested in a property"""
        data = await test_data
        property2 = data["properties"][1]  # Family house
        
        matches = await matcher.find_leads_for_property(
            str(property2.id),
            limit=10,
            min_score=0.5
        )
        
        # Should find at least one interested lead
        assert len(matches) > 0
        
        # Family buyer should be interested
        lead_names = [match["lead"].name for match in matches]
        assert "Family Buyer" in lead_names
    
    @pytest.mark.asyncio
    async def test_run_weekly_matching(self, matcher, test_data, mock_evo_api):
        """Test weekly matching process"""
        data = await test_data
        tenant = data["tenant"]
        
        # Mock notification service
        with patch('src.services.property_matcher.NotificationService') as mock_notif:
            mock_notif_instance = AsyncMock()
            mock_notif.return_value = mock_notif_instance
            
            # Run matching
            result = await matcher.run_weekly_matching(str(tenant.id))
            
            assert result["success"] is True
            assert result["leads_analyzed"] == 2
            assert result["properties_analyzed"] >= 3
            assert result["total_matches"] >= 0
    
    def test_format_budget_range(self, matcher):
        """Test budget range formatting"""
        lead1 = Lead(budget_min=200000, budget_max=300000)
        assert matcher._format_budget_range(lead1) == "R$ 200,000 - R$ 300,000"
        
        lead2 = Lead(budget_min=150000)
        assert matcher._format_budget_range(lead2) == "A partir de R$ 150,000"
        
        lead3 = Lead(budget_max=500000)
        assert matcher._format_budget_range(lead3) == "Até R$ 500,000"
        
        lead4 = Lead()
        assert matcher._format_budget_range(lead4) is None
    
    def test_format_property_types(self, matcher):
        """Test property type formatting"""
        lead1 = Lead(property_type_interest=[PropertyType.HOUSE, PropertyType.APARTMENT])
        formatted = matcher._format_property_types(lead1)
        assert "Casa" in formatted
        assert "Apartamento" in formatted
        
        lead2 = Lead()
        assert matcher._format_property_types(lead2) is None
    
    def test_format_price(self, matcher):
        """Test price formatting"""
        assert matcher._format_price(1500000) == "R$ 1.5M"
        assert matcher._format_price(250000) == "R$ 250K"
        assert matcher._format_price(999) == "R$ 999"
        assert matcher._format_price(1200000) == "R$ 1.2M"
    
    @pytest.mark.asyncio
    async def test_match_scoring_weights(self, matcher, test_data):
        """Test that match scoring weights sum to 1.0"""
        total_weight = sum(matcher.WEIGHT_FACTORS.values())
        assert total_weight == pytest.approx(1.0, 0.001)
        
        # Test actual scoring
        data = await test_data
        lead = data["leads"][0]
        property = data["properties"][0]
        
        score, breakdown = matcher._calculate_match_score(lead, property)
        
        # Verify score is weighted sum
        weighted_sum = sum(
            breakdown[factor] * matcher.WEIGHT_FACTORS[factor]
            for factor in matcher.WEIGHT_FACTORS
        )
        assert score == pytest.approx(weighted_sum, 0.001)