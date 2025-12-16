"""
Tests for authentication guard functions.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestRequireAuth:
    """Tests for require_auth function."""
    
    def test_raises_401_when_no_token(self):
        """Should raise AuthenticationError with 401 when no token."""
        from auth.clerk_auth import require_auth, AuthenticationError
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': '', 'Cookie': ''}
        mock_request.path = '/api/check-auth'
        
        with pytest.raises(AuthenticationError) as exc_info:
            require_auth(mock_request)
        
        assert exc_info.value.status_code == 401
        assert "Authentication required" in str(exc_info.value)
    
    def test_raises_401_when_token_invalid(self):
        """Should raise AuthenticationError when token verification fails."""
        from auth.clerk_auth import require_auth, AuthenticationError, AuthFailureReason
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': 'Bearer invalid.token', 'Cookie': ''}
        mock_request.path = '/api/check-auth'
        
        with patch('auth.clerk_auth.verify_clerk_token', return_value=(None, AuthFailureReason.INVALID_SIGNATURE)):
            with pytest.raises(AuthenticationError) as exc_info:
                require_auth(mock_request)
            
            assert exc_info.value.status_code == 401
    
    def test_returns_user_when_authenticated(self):
        """Should return user dict when properly authenticated."""
        from auth.clerk_auth import require_auth
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': 'Bearer valid.token', 'Cookie': ''}
        mock_request.path = '/api/check-auth'
        
        mock_user = {
            'clerk_user_id': 'user_123',
            'email': 'test@example.com',
            'name': 'Test User',
            'avatar_url': None
        }
        
        with patch('auth.clerk_auth.verify_clerk_token', return_value=(mock_user, None)):
            result = require_auth(mock_request)
            
            assert result['clerk_user_id'] == 'user_123'
            assert result['email'] == 'test@example.com'


class TestRequireAdmin:
    """Tests for require_admin function."""
    
    def test_raises_401_when_not_authenticated(self):
        """Should raise 401 when not authenticated."""
        from auth.clerk_auth import require_admin, AuthenticationError
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': '', 'Cookie': ''}
        mock_request.path = '/api/admin/tenants'
        
        with pytest.raises(AuthenticationError) as exc_info:
            require_admin(mock_request)
        
        assert exc_info.value.status_code == 401
    
    def test_raises_403_when_not_admin(self):
        """Should raise 403 when user is not admin."""
        from auth.clerk_auth import require_admin, AuthorizationError
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': 'Bearer valid.token', 'Cookie': ''}
        mock_request.path = '/api/admin/tenants'
        
        mock_user = {
            'clerk_user_id': 'user_123',
            'email': 'test@example.com',
            'name': 'Test User',
            'avatar_url': None
        }
        
        mock_db_user = {
            'clerk_user_id': 'user_123',
            'role': 'client',
            'tenant_id': 'testuser'
        }
        
        with patch('auth.clerk_auth.verify_clerk_token', return_value=(mock_user, None)):
            with patch('db.get_user_by_clerk_id', return_value=mock_db_user):
                with pytest.raises(AuthorizationError) as exc_info:
                    require_admin(mock_request)
                
                assert exc_info.value.status_code == 403
                assert "Admin access required" in str(exc_info.value)
    
    def test_returns_user_when_admin(self):
        """Should return user when admin role."""
        import os
        from auth.clerk_auth import require_admin
        
        mock_request = MagicMock()
        mock_request.headers = {'Authorization': 'Bearer valid.token', 'Cookie': ''}
        mock_request.path = '/api/admin/tenants'
        
        mock_user = {
            'clerk_user_id': 'admin_123',
            'email': 'admin@company.com',
            'name': 'Admin User',
            'avatar_url': None
        }
        
        mock_db_user = {
            'clerk_user_id': 'admin_123',
            'role': 'admin',
            'tenant_id': None
        }
        
        with patch.dict(os.environ, {'ADMIN_EMAILS': 'admin@company.com'}):
            with patch('auth.clerk_auth.verify_clerk_token', return_value=(mock_user, None)):
                with patch('db.get_user_by_clerk_id', return_value=mock_db_user):
                    result = require_admin(mock_request)
                    
                    assert result['clerk_user_id'] == 'admin_123'
                    assert result['role'] == 'admin'


class TestGetEffectiveTenantId:
    """Tests for get_effective_tenant_id function."""
    
    def test_returns_tenant_id_for_client(self):
        """Should return tenant_id for client users."""
        from auth.clerk_auth import get_effective_tenant_id
        
        mock_user = {'clerk_user_id': 'user_123'}
        mock_db_user = {'role': 'client', 'tenant_id': 'clienttenant'}
        
        with patch('db.get_user_by_clerk_id', return_value=mock_db_user):
            result = get_effective_tenant_id(mock_user)
            assert result == 'clienttenant'
    
    def test_returns_none_for_admin(self):
        """Should return None for admin users (can access all tenants)."""
        from auth.clerk_auth import get_effective_tenant_id
        
        mock_user = {'clerk_user_id': 'admin_123'}
        mock_db_user = {'role': 'admin', 'tenant_id': None}
        
        with patch('db.get_user_by_clerk_id', return_value=mock_db_user):
            result = get_effective_tenant_id(mock_user)
            assert result is None
    
    def test_returns_none_when_user_not_found(self):
        """Should return None when user not found in DB."""
        from auth.clerk_auth import get_effective_tenant_id
        
        mock_user = {'clerk_user_id': 'unknown_user'}
        
        with patch('db.get_user_by_clerk_id', return_value=None):
            result = get_effective_tenant_id(mock_user)
            assert result is None
