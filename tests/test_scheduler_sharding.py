"""
Tests for scheduler sharding and multi-tenant mode functionality.
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from forex_scheduler import parse_shard, tenant_in_shard


class TestParseShardFunction:
    """Tests for parse_shard function."""
    
    def test_valid_shard_0_of_3(self):
        """Test parsing valid shard string 0/3."""
        shard_index, total_shards = parse_shard("0/3")
        assert shard_index == 0
        assert total_shards == 3
    
    def test_valid_shard_2_of_3(self):
        """Test parsing valid shard string 2/3."""
        shard_index, total_shards = parse_shard("2/3")
        assert shard_index == 2
        assert total_shards == 3
    
    def test_valid_shard_0_of_1(self):
        """Test parsing single shard 0/1."""
        shard_index, total_shards = parse_shard("0/1")
        assert shard_index == 0
        assert total_shards == 1
    
    def test_invalid_shard_out_of_range(self):
        """Test that shard index >= total returns None."""
        shard_index, total_shards = parse_shard("3/3")
        assert shard_index is None
        assert total_shards is None
    
    def test_invalid_shard_negative(self):
        """Test that negative shard index returns None."""
        shard_index, total_shards = parse_shard("-1/3")
        assert shard_index is None
        assert total_shards is None
    
    def test_invalid_shard_zero_total(self):
        """Test that zero total shards returns None."""
        shard_index, total_shards = parse_shard("0/0")
        assert shard_index is None
        assert total_shards is None
    
    def test_invalid_shard_no_slash(self):
        """Test that missing slash returns None."""
        shard_index, total_shards = parse_shard("03")
        assert shard_index is None
        assert total_shards is None
    
    def test_invalid_shard_empty_string(self):
        """Test that empty string returns None."""
        shard_index, total_shards = parse_shard("")
        assert shard_index is None
        assert total_shards is None
    
    def test_invalid_shard_none(self):
        """Test that None input returns None."""
        shard_index, total_shards = parse_shard(None)
        assert shard_index is None
        assert total_shards is None
    
    def test_invalid_shard_non_numeric(self):
        """Test that non-numeric values return None."""
        shard_index, total_shards = parse_shard("a/b")
        assert shard_index is None
        assert total_shards is None


class TestTenantInShardFunction:
    """Tests for tenant_in_shard function and sharding stability."""
    
    def test_shard_assignment_stability(self):
        """Test that the same tenant always gets the same shard."""
        tenant_id = "entrylab"
        total_shards = 3
        
        first_assignment = None
        for i in range(total_shards):
            if tenant_in_shard(tenant_id, i, total_shards):
                first_assignment = i
                break
        
        for _ in range(100):
            for i in range(total_shards):
                result = tenant_in_shard(tenant_id, i, total_shards)
                if i == first_assignment:
                    assert result is True
                else:
                    assert result is False
    
    def test_tenant_assigned_to_exactly_one_shard(self):
        """Test that each tenant is assigned to exactly one shard."""
        test_tenants = ["tenant_a", "tenant_b", "tenant_c", "entrylab", "acme_corp"]
        total_shards = 4
        
        for tenant_id in test_tenants:
            shard_count = sum(
                1 for i in range(total_shards)
                if tenant_in_shard(tenant_id, i, total_shards)
            )
            assert shard_count == 1, f"Tenant {tenant_id} assigned to {shard_count} shards"
    
    def test_sharding_distributes_tenants(self):
        """Test that sharding distributes tenants somewhat evenly."""
        tenants = [f"tenant_{i}" for i in range(100)]
        total_shards = 4
        
        shard_counts = [0] * total_shards
        for tenant_id in tenants:
            for i in range(total_shards):
                if tenant_in_shard(tenant_id, i, total_shards):
                    shard_counts[i] += 1
                    break
        
        min_count = min(shard_counts)
        max_count = max(shard_counts)
        assert max_count - min_count <= 30, f"Uneven distribution: {shard_counts}"
    
    def test_single_shard_gets_all(self):
        """Test that with 1 shard, all tenants are assigned to shard 0."""
        tenants = ["a", "b", "c", "d", "e"]
        
        for tenant_id in tenants:
            assert tenant_in_shard(tenant_id, 0, 1) is True


class TestAllTenantsMode:
    """Tests for --all-tenants mode behavior."""
    
    def test_shard_filtering_reduces_count(self):
        """Test that shard filtering reduces the tenant count."""
        all_tenants = [f"tenant_{i}" for i in range(10)]
        total_shards = 3
        shard_index = 0
        
        filtered = [t for t in all_tenants if tenant_in_shard(t, shard_index, total_shards)]
        
        assert len(filtered) < len(all_tenants)
        assert len(filtered) > 0
    
    def test_all_shards_cover_all_tenants(self):
        """Test that combining all shards covers all tenants."""
        all_tenants = [f"tenant_{i}" for i in range(50)]
        total_shards = 5
        
        covered = set()
        for shard_index in range(total_shards):
            for tenant_id in all_tenants:
                if tenant_in_shard(tenant_id, shard_index, total_shards):
                    covered.add(tenant_id)
        
        assert covered == set(all_tenants)
